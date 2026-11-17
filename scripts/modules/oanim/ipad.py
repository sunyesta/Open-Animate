"""Draw on iPad: what the drawing page (scripts/ipad) and Open Animate say to each other.

Window > Draw on iPad... (oanim.ops.wm.ipad_draw_start) starts a web server on this computer's network and shows a QR
code; the iPad's camera opens the page, which connects back over a WebSocket. Each frame the main loop calls _tick,
which handles the page's messages and sends what changed.

The page sends (JSON, "t" naming each):
  down {id, eraser, zoom, s}   a Pencil stroke begins (id, the page's for it): its first samples s, [[x, y, pressure, tilt_x, tilt_y, seconds]]
                           in canvas pixels; zoom, the page's screen pixels per canvas pixel
  move {s}, up {s}         more samples; up ends the stroke, drawn as the viewport draws it (one undo step)
  cancel                   the stroke is dropped (a finger came down to pan)
  undo, redo               two and three finger taps
  set {values}             header changes, by draw_settings' names, plus size_px (the Size field's pixels) and
                           opacity (the line's, or the Fill Pen's fill)
  preset {name}            a shelf tile picked; preset_save {name} the + tile
  brush {name}             the line brush's shape ("" plain); brush_recent {index}
  canvas_full              the page lost track of the canvases: the next comes whole
  input_log {agent, events}  the page's last touches and Pencil events, saved to input_log_path()

Open Animate sends:
  state                    the header's settings, the shelf's pens, why drawing is refused ("" when it isn't), the
                           frame and layer
  tiles {tiles}            the shelf's pictures; brush {preview} the brush button's
  canvas {w, h, head, defs, body, seq, base, frame, onion, strokes}   the frame as Render Frame draws it, with the
                           onion skins; strokes, how many strokes had been made when it was. Its SVG comes in pieces
                           (the root's tag, the elements in its defs and those after): a piece the last canvas (seq
                           base) had is sent as its place in that one, so an undo sends only what it changed; base 0,
                           every piece's text
  live {id, kind, ...}     the line being drawn, as it now stands (only what changed since the last)
  done {id, undo, count}   the stroke ended: the undo step it made ("" none), and the strokes made with it
  refused {id, why}        a stroke that couldn't begin
"""

import json
import re
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
# The last canvas's SVG in pieces, what the next is sent against (head None: send it whole).
_last_pieces = {"seq": 0, "head": None, "defs": [], "body": []}
_clients = set()
# The connection whose stroke is being drawn, and the page's id for that stroke (sent back with what is sent of it).
_drawing = None
_stroke_id = None
# Strokes made so far: each canvas says how many it shows, so the page keeps a line lifted until one does.
_strokes_done = 0


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
    global _last_canvas_key, _drawing, _stroke_id
    _last_state.clear()
    _last_tiles.clear()
    _last_brush.clear()
    _clients.clear()
    _last_canvas_key = None
    _last_pieces["head"] = None
    _drawing = None
    _stroke_id = None


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
    global _drawing, _stroke_id, _strokes_done, _last_canvas_key, _last_canvas_time
    import oanim

    t = message.get("t")
    if t == "_open":
        _clients.add(client)
        _oanim.ipad_images_reset()
        # Everything goes again, to every page (a new page has nothing).
        _last_state.clear()
        _last_tiles.clear()
        _last_brush.clear()
        _last_canvas_key = None
        _last_pieces["head"] = None
        # Sent at once, however lately the last was.
        _last_canvas_time = 0.0
        return False
    if t == "canvas_full":
        _last_canvas_key = None
        _last_pieces["head"] = None
        _last_canvas_time = 0.0
        return False
    if t == "_close":
        _clients.discard(client)
        if _drawing == client:
            _oanim.ipad_stroke_cancel()
            _drawing = None
        return False
    if t == "down":
        w, h = canvas_size()
        stroke_id = message.get("id")
        why = _oanim.ipad_stroke_begin(w, h, float(message.get("zoom", 1.0)), bool(message.get("eraser", False)))
        if why:
            _drawing = None
            _send_json(client, {"t": "refused", "id": stroke_id, "why": why})
            return False
        _drawing = client
        _stroke_id = stroke_id
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
            if name:
                _strokes_done += 1
            _send_json(client, {"t": "done", "id": _stroke_id, "undo": name, "count": _strokes_done})
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
    if t == "input_log":
        _input_log_save(message)
        return True
    if t == "brush_recent":
        oanim.ops.brush.recent_pick(index=int(message.get("index", -1)))
        return True
    return False


def input_log_path():
    """Where the page's input log goes (Options > Send Input Log on the iPad)."""
    import os
    import tempfile

    return os.path.join(tempfile.gettempdir(), "OpenAnimate", "ipad_input_log.json")


def _input_log_save(message):
    """The page's last touches and Pencil events, written to input_log_path() (a fixed file, at most 2000 rows)."""
    import os

    import oanim

    events = message.get("events")
    if not isinstance(events, list):
        return
    path = input_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"agent": str(message.get("agent", ""))[:300], "events": events[-2000:]}, f)
    oanim.wm.report("iPad input log saved to " + path)


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
        _send(client, text[:-1] + ',"n":%d,"id":%s}' % (_live.count, json.dumps(_stroke_id)))


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
        message = json.loads(_oanim.ipad_canvas(w, h))
        message["strokes"] = _strokes_done
        _send(0, json.dumps(_canvas_pieces(message), separators=(",", ":")))


_TAG = re.compile(r"<(/?)([A-Za-z][\w:.-]*)(?:[^>\"']|\"[^\"]*\"|'[^']*')*?(/?)>|<\?.*?\?>|<!--.*?-->|<!\[CDATA\[.*?\]\]>", re.S)


def svg_pieces(svg):
    """An SVG's text cut where the page swaps it: (the root's opening tag, the elements in its defs, the elements after
    them), each the exact text of one element. The text between them is left out (an SVG draws none)."""
    head = None
    defs, body = [], []
    depth = 0
    in_defs = False
    start = None
    piece_depth = 0
    piece_in_defs = False
    for m in _TAG.finditer(svg):
        name = m.group(2)
        if not name:
            continue
        if m.group(1):
            depth -= 1
            if start is not None and depth == piece_depth:
                (defs if piece_in_defs else body).append(svg[start:m.end()])
                start = None
            elif start is None and depth == 1 and name == "defs":
                in_defs = False
            continue
        closed = bool(m.group(3))
        if head is None:
            head = svg[:m.end()]
            depth = 1
            continue
        if start is None:
            if depth == 1 and name == "defs" and not in_defs:
                if not closed:
                    in_defs = True
                    depth = 2
                continue
            if depth == (2 if in_defs else 1):
                if closed:
                    (defs if in_defs else body).append(m.group(0))
                    continue
                start = m.start()
                piece_depth = depth
                piece_in_defs = in_defs
        if not closed:
            depth += 1
    return head or "", defs, body


def _canvas_pieces(message):
    """The canvas message with its SVG in pieces, those the last canvas had sent as their place in it."""
    head, defs, body = svg_pieces(message.pop("svg"))
    last = _last_pieces
    whole = last["head"] != head
    message["head"] = head
    for key, now in (("defs", defs), ("body", body)):
        before = {}
        if not whole:
            for i, text in enumerate(last[key]):
                before.setdefault(text, i)
        message[key] = [before.get(text, text) for text in now]
    message["base"] = 0 if whole else last["seq"]
    last["seq"] += 1
    message["seq"] = last["seq"]
    last.update(head=head, defs=defs, body=body)
    return message


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
