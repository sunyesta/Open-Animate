"""Draw on iPad: what the drawing page (scripts/ipad) and Open Animate say to each other.

Window > Draw on iPad... (oanim.ops.wm.ipad_draw_start) starts a web server on this computer's network and shows a QR
code; the iPad's camera opens the page, which connects back over a WebSocket. Each frame the main loop calls _tick,
which handles the page's messages and sends what changed.

The page sends (JSON, "t" naming each):
  down {eraser, zoom, s}   a Pencil stroke begins: its first samples s, [[x, y, pressure, tilt_x, tilt_y, seconds]]
                           in canvas pixels; zoom, the page's screen pixels per canvas pixel
  move {s}, up {s}         more samples; up ends the stroke, drawn as the viewport draws it (one undo step)
  cancel                   the stroke is dropped (a finger came down to pan)
  undo, redo               two and three finger taps
  set {values}             header changes, by draw_settings' names, plus size_px (the Size field's pixels) and
                           opacity (the line's, or the Fill Pen's fill)
  preset {name}            a shelf tile picked; preset_save {name} the + tile
  brush {name}             the line brush's shape ("" plain); brush_recent {index}

Open Animate sends:
  state                    the header's settings, the shelf's pens, why drawing is refused ("" when it isn't), the
                           frame and layer
  tiles {tiles}            the shelf's pictures; brush {preview} the brush button's
  canvas {w, h, svg, frame, onion}   the frame as Render Frame draws it, with the onion skins
  live {kind, ...}         the line being drawn, as it now stands (only what changed since the last)
  done {undo}              the stroke ended: the undo step it made ("" none)
  refused {why}            a stroke that couldn't begin
"""

import json
import time

import _oanim

# The longest side of the canvas sent (pixels): the document's own size, or less.
CANVAS_MAX = 2048
# The least time between two canvases sent while the document keeps changing (playback, a drag), seconds.
CANVAS_INTERVAL = 0.1
TILE_SIZE = 64
BRUSH_PREVIEW = (96, 28)

_last_state = {}
_last_tiles = {}
_last_brush = {}
_last_canvas_key = None
_last_canvas_time = 0.0
_clients = set()
# The connection whose stroke is being drawn.
_drawing = None


def _send(client, text):
    """Sends a message's text (str or bytes) to one page, or every page (0). Tests replace it to see what is sent."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    _oanim.ipad_send(client, text)


def _send_json(client, message):
    _send(client, json.dumps(message, separators=(",", ":")))


def start(port=8765):
    """Starts the server (no window): returns the port, 0 if it couldn't start."""
    return _oanim.ipad_start(port)


def stop():
    _oanim.ipad_stop()
    _reset()


def running():
    return _oanim.ipad_running()


def url():
    """What the QR code holds: http://<address>:<port>/?k=<one-time key>."""
    return _oanim.ipad_url()


def clients():
    """Pages connected now."""
    return _oanim.ipad_clients()


def _reset():
    global _last_canvas_key, _drawing
    _last_state.clear()
    _last_tiles.clear()
    _last_brush.clear()
    _clients.clear()
    _last_canvas_key = None
    _drawing = None


def canvas_size():
    """The canvas's size in pixels: the document's, scaled down to CANVAS_MAX on its longest side."""
    import oanim

    doc = oanim.data.document
    w, h = doc.width, doc.height
    scale = min(1.0, CANVAS_MAX / max(w, h, 1))
    return max(1, round(w * scale)), max(1, round(h * scale))


def _size_field(s, doc_height):
    """The header's Size: its pixels and how they read, as draw_size_field shows them."""
    if s["size_view"]:
        return s["view_size"], "Size %.1f px on screen"
    paints = s["mode"] in ("FILL_PEN", "FILL_ERASER", "STROKE_ERASER", "TRIMMER")
    width = s["fill_size"] if paints else s["line_width"]
    return width * doc_height * 0.5, "Size %.1f px"


def state():
    """The state message: everything the page's header, shelf and banner show."""
    import oanim

    s = oanim.wm.draw_settings()
    doc_height = oanim.data.document.height
    size, size_format = _size_field(s, doc_height)
    mode = s["mode"]
    layer = oanim.data.layers.active
    presets = [{"name": p["name"], "mode": p["mode"], "category": p["category"], "builtin": p["builtin"]}
               for p in oanim.wm.draw_presets()]
    return {
        "t": "state",
        "refused": _oanim.ipad_draw_refused(),
        "tool": oanim.wm.tool(),
        "mode": mode,
        "preset": s["preset"],
        "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in s.items() if k != "brush_recent"},
        "size_px": size,
        "size_format": size_format,
        "opacity": s["fill_color"][3] if mode == "FILL_PEN" else s["line_color"][3],
        "fill_shown": bool(s["fill"]) or mode == "FILL_PEN",
        "brush": _oanim.ipad_brush_name(),
        "brush_recent": [r["name"] for r in s["brush_recent"]],
        "brush_shapes": ["Round"] + [n for n in _oanim.ipad_brush_shapes()],
        "presets": presets,
        "frame": oanim.data.document.frame_current,
        "doc_height": doc_height,
        "layer": layer.name if layer else "",
    }


def _set(values):
    """The header's changes, as the PC's fields make them."""
    import oanim

    values = dict(values)
    s = oanim.wm.draw_settings()
    mode = s["mode"]
    if "size_px" in values:
        px = max(float(values.pop("size_px")), 0.0)
        if s["size_view"]:
            values["view_size"] = min(px, 500.0)
        else:
            width = px / (oanim.data.document.height * 0.5)
            paints = mode in ("FILL_PEN", "FILL_ERASER", "STROKE_ERASER", "TRIMMER")
            values["fill_size" if paints else "line_width"] = width
    if "opacity" in values:
        a = min(max(float(values.pop("opacity")), 0.0), 1.0)
        key = "fill_color" if mode == "FILL_PEN" else "line_color"
        r, g, b, _ = s[key]
        values[key] = (r, g, b, a)
    for key in ("line_color", "fill_color", "pressure_curve"):
        if key in values:
            values[key] = tuple(float(v) for v in values[key])
    if values:
        oanim.wm.set_draw(**values)


def _handle(client, message):
    """One message from a page. True when it changed something besides a stroke."""
    global _drawing
    import oanim

    t = message.get("t")
    if t == "_open":
        _clients.add(client)
        _oanim.ipad_images_reset()
        # Everything goes again, to every page (a new page has nothing).
        _last_state.clear()
        _last_tiles.clear()
        _last_brush.clear()
        global _last_canvas_key
        _last_canvas_key = None
        return False
    if t == "_close":
        _clients.discard(client)
        if _drawing == client:
            _oanim.ipad_stroke_cancel()
            _drawing = None
        return False
    if t == "down":
        w, h = canvas_size()
        why = _oanim.ipad_stroke_begin(w, h, float(message.get("zoom", 1.0)), bool(message.get("eraser", False)))
        if why:
            _drawing = None
            _send_json(client, {"t": "refused", "why": why})
            return False
        _drawing = client
        _live.count = 0
        _live(client, message.get("s", []))
        return False
    if t in ("move", "up"):
        if _drawing != client:
            return False
        _live(client, message.get("s", []))
        if t == "up":
            _drawing = None
            name = _oanim.ipad_stroke_end()
            _send_json(client, {"t": "done", "undo": name})
            return bool(name)
        return False
    if t == "cancel":
        if _drawing == client:
            _oanim.ipad_stroke_cancel()
            _drawing = None
        return False
    if _drawing is not None:
        # The header and the gestures wait for the stroke to end (the pen and a finger at once).
        return False
    if t == "undo":
        oanim.ops.ed.undo()
        return True
    if t == "redo":
        oanim.ops.ed.redo()
        return True
    if t == "set":
        _set(message.get("values", {}))
        return True
    if t == "preset":
        oanim.ops.draw.preset_load(name=str(message.get("name", "")))
        return True
    if t == "preset_reset":
        oanim.ops.draw.preset_reset(name=str(message.get("name", "")))
        return True
    if t == "preset_remove":
        oanim.ops.draw.preset_remove(name=str(message.get("name", "")))
        return True
    if t == "preset_save":
        name = str(message.get("name", "")).strip()
        if name:
            oanim.ops.draw.preset_save(name=name)
        return True
    if t == "brush":
        _oanim.ipad_brush_shape_set(str(message.get("name", "")))
        return True
    if t == "brush_recent":
        oanim.ops.brush.recent_pick(index=int(message.get("index", -1)))
        return True
    return False


def _samples(rows):
    out = []
    for r in rows:
        if len(r) >= 6:
            out.append((float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    return out


def _live(client, rows):
    """The samples added, and the line as it now stands sent, saying how many samples it is made of so far (the page
    draws the pen's tip past them itself)."""
    samples = _samples(rows)
    if not samples:
        return
    _live.count = getattr(_live, "count", 0) + len(samples)
    text = _oanim.ipad_stroke_add(samples)
    if text:
        text = text.decode("utf-8")
        _send(client, text[:-1] + ',"n":%d}' % _live.count)


def _send_changes(force_canvas=False):
    """What changed since last sent, to every page."""
    global _last_canvas_key, _last_canvas_time
    st = state()
    text = json.dumps(st, separators=(",", ":"), sort_keys=True)
    if _last_state.get("text") != text:
        _last_state["text"] = text
        _send(0, text)
    # The tiles and the brush button's picture follow the settings.
    key = (st["settings"].__repr__(), st["presets"].__repr__(), st["brush"], st["preset"])
    if _last_tiles.get("key") != key:
        _last_tiles["key"] = key
        _send(0, '{"t":"tiles","size":%d,"tiles":' % TILE_SIZE + _oanim.ipad_tiles(TILE_SIZE).decode("utf-8") + "}")
        _send(0, '{"t":"brush","preview":' + _oanim.ipad_brush_preview(*BRUSH_PREVIEW).decode("utf-8") + "}")
    canvas_key = _oanim.ipad_canvas_key()
    now = time.monotonic()
    if canvas_key != _last_canvas_key and (force_canvas or now - _last_canvas_time >= CANVAS_INTERVAL):
        _last_canvas_key = canvas_key
        _last_canvas_time = now
        w, h = canvas_size()
        _send(0, _oanim.ipad_canvas(w, h))


# When what changed was last looked for, seconds.
_last_flush = 0.0
# Looked for this often at most (a message handled looks at once).
FLUSH_INTERVAL = 0.05


def _tick(messages=None):
    """Each frame while the server runs (or with `messages`, [(client, text)], in tests): the pages' messages handled.
    True when something besides a stroke ran."""
    if messages is None:
        messages = _oanim.ipad_take()
    changed = False
    for client, text in messages:
        try:
            message = json.loads(text)
        except ValueError:
            continue
        if isinstance(message, dict):
            changed = _handle(client, message) or changed
    _tick.handled = bool(messages)
    return changed


def _flush(changed=False):
    """After _tick: what changed sent to the pages (while no stroke is being drawn)."""
    global _last_flush
    now = time.monotonic()
    handled = getattr(_tick, "handled", False)
    if not _clients or _drawing is not None or (not handled and now - _last_flush < FLUSH_INTERVAL):
        return
    _last_flush = now
    _send_changes(force_canvas=changed)
