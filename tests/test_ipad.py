"""Draw on iPad (wm/ipad_server.cc, wm/ipad_link.cc, scripts/modules/oanim/ipad.py, the page in scripts/ipad): a web
server on the network serving the drawing page and talking to it over a WebSocket that must bring the QR code's
one-time key; the Pencil's strokes drawn by Open Animate's own Stroke Pen as the viewport draws them (the same line,
the same undo step), the line sent back as it grows with only what changed; the header's settings both ways; the
canvas as the viewport shows it (guides too), with onion skins.

The page itself needs an iPad (or a browser): checked live.

Run with:  OpenAnimate --background --python tests/test_ipad.py
"""

import base64
import json
import math
import os
import socket
import struct
import time
import urllib.error
import urllib.request

import oanim
from oanim import ipad

ops = oanim.ops
_oanim = oanim._oanim

# --- The WebSocket's handshake and frames (RFC 6455's own example) ------------------------------------------------------
assert _oanim.websocket_accept("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
assert _oanim.websocket_frame(b"hi", 1) == b"\x81\x02hi"
assert _oanim.websocket_frame(b"x" * 126, 1)[:4] == b"\x81\x7e\x00\x7e"
assert _oanim.websocket_frame(b"x" * 70000, 1)[:10] == b"\x81\x7f" + struct.pack(">Q", 70000)


# --- The server: the page's files for anyone, the socket only with the key --------------------------------------------
def ws_open(port, key):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(("GET /ws?k=%s HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
               % (key, base64.b64encode(os.urandom(16)).decode())).encode())
    head = b""
    while b"\r\n\r\n" not in head:
        c = s.recv(1)
        if not c:
            break
        head += c
    return s, head.split(b"\r\n")[0]


def ws_send(s, obj):
    data = json.dumps(obj).encode()
    mask = os.urandom(4)
    n = len(data)
    head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n))
    s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def ws_recv(s):
    def exact(n):
        b = b""
        while len(b) < n:
            c = s.recv(n - len(b))
            assert c, "closed"
            b += c
        return b
    h = exact(2)
    n = h[1] & 127
    if n == 126:
        n = struct.unpack(">H", exact(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", exact(8))[0]
    return json.loads(exact(n))


def take_messages(wait=2.0):
    """The server's messages come in on its threads: wait for them."""
    end = time.monotonic() + wait
    got = []
    while time.monotonic() < end:
        got += _oanim.ipad_take()
        if got:
            time.sleep(0.05)
            got += _oanim.ipad_take()
            return got
        time.sleep(0.02)
    return got


port = ipad.start(0)
assert port > 0 and ipad.running()
url = ipad.url()
key = url.split("k=")[1]
assert url.startswith("http://") and (":%d/?k=" % port) in url and len(key) == 32, url
page = urllib.request.urlopen("http://127.0.0.1:%d/" % port).read()
assert b"app.js" in page, "the page"
assert b"Pencil" in urllib.request.urlopen("http://127.0.0.1:%d/app.js" % port).read()
try:
    urllib.request.urlopen("http://127.0.0.1:%d/..%%2fCMakeLists.txt" % port)
    assert False, "nothing outside the page's folder"
except urllib.error.HTTPError as e:
    assert e.code == 404

s, status = ws_open(port, "0" * 32)
assert b"403" in status, ("a wrong key is refused", status)
s.close()
s, status = ws_open(port, key)
assert b"101" in status, status
got = take_messages()
assert len(got) == 1 and json.loads(got[0][1]) == {"t": "_open"}, got
client = got[0][0]
ws_send(s, {"t": "hello", "x": "é" * 200})
got = take_messages()
assert got and json.loads(got[0][1])["x"] == "é" * 200, "a message as sent (longer than 125 bytes, UTF-8)"
_oanim.ipad_send(client, json.dumps({"t": "test", "big": "y" * 100000}))
assert ws_recv(s)["big"] == "y" * 100000
assert ipad.clients() == 1
s.close()
got = take_messages()
assert got and json.loads(got[-1][1]) == {"t": "_close"}, got
ipad.stop()
assert not ipad.running() and ipad.url() == ""
# A new start, a new key: the old one no longer works.
port2 = ipad.start(0)
assert ipad.url().split("k=")[1] != key
ipad.stop()


# --- The page's messages, handled without the network: what is sent is caught ----------------------------------------------
sent = []
ipad._send = lambda client, text: sent.append((client, json.loads(text if isinstance(text, str) else text.decode())))
CLIENT = 7


# The canvas as the page puts it together from the pieces each canvas sends (app.js canvasApply).
page = {"seq": 0, "head": "", "defs": [], "body": [], "svg": ""}


def page_canvas(m):
    assert m["base"] == 0 or m["base"] == page["seq"], ("sent against a canvas the page has", m["base"], page["seq"])
    if m["base"] == 0:
        page.update(head=m["head"], defs=[], body=[])
    for key in ("defs", "body"):
        page[key] = [v if isinstance(v, str) else page[key][v] for v in m[key]]
    page["seq"] = m["seq"]
    page["svg"] = page["head"] + "<defs>" + "".join(page["defs"]) + "</defs>" + "".join(page["body"]) + "</svg>"


def whole(svg):
    """An SVG as the page's pieces put back together, to compare with one the page made."""
    head, defs, body = ipad.svg_pieces(svg)
    return head + "<defs>" + "".join(defs) + "</defs>" + "".join(body) + "</svg>"


def messages(*items):
    sent.clear()
    changed = ipad._tick([(CLIENT, json.dumps(m)) for m in items])
    ipad._flush(changed)
    for _, m in sent:
        if m["t"] == "canvas":
            page_canvas(m)
    return [m for _, m in sent]


def of(kind, got):
    return [m for m in got if m["t"] == kind]


def fresh():
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    doc = oanim.data.document
    doc.frame_current = 0
    ops.draw.preset_load(name="Ink")
    # The Draw tool's settings outlive the document: as a new session's.
    oanim.wm.set_draw(size_view=False)
    _oanim.ipad_brush_shape_set("")
    ipad._reset()
    got = messages({"t": "_open"})
    return doc, got


doc, got = fresh()
assert [m["t"] for m in got] == ["state", "tiles", "brush", "canvas"], [m["t"] for m in got]
st = of("state", got)[0]
assert st["refused"] == "" and st["tool"] == "DRAW" and st["mode"] == "FREEHAND" and st["preset"] == "Ink"
assert {p["name"] for p in st["presets"]} >= {"Ink", "Pencil", "Marker", "Tapered", "Mouse"}
tiles = {t["name"]: t for t in of("tiles", got)[0]["tiles"]}
assert set(tiles) == {p["name"] for p in st["presets"]}
assert len(tiles["Ink"]["strokes"]) == 1 and len(tiles["Ink"]["strokes"][0]["p"]) > 20, "Ink's sample line"
canvas = of("canvas", got)[0]
W, H = ipad.canvas_size()
assert (canvas["w"], canvas["h"]) == (W, H) and "<svg" in canvas["head"] and canvas["onion"] == []
assert canvas["base"] == 0 and page["svg"] == whole(json.loads(_oanim.ipad_canvas(W, H))["svg"]), "a new page's canvas whole"
assert messages() == [], "nothing again until something changes"


def wave(n=60):
    return [[W * 0.25 + i * W * 0.008, H * 0.5 + H * 0.1 * math.sin(i / 6), 0.3 + 0.6 * math.sin(i / n * math.pi), 0, 0,
             i / 120] for i in range(n)]


def stroke(rows, zoom=1.0, eraser=False):
    got = messages({"t": "down", "zoom": zoom, "eraser": eraser, "s": rows[:5]})
    got += messages({"t": "move", "s": rows[5:30]})
    got += messages({"t": "move", "s": rows[30:]})
    return got + messages({"t": "up", "s": []})


def shapes():
    return len(oanim.data.layers.active.shapes)


def points():
    return [tuple(round(c, 6) for c in p) for p in oanim.data.layers.active.points]


# --- A stroke is the viewport's: the same line as draw.stroke makes of the same hand, one "Draw" step ------------------
undo_before = oanim.wm.undo_history()[1]
got = stroke(wave())
live = of("live", got)
assert len(live) == 3 and [m["n"] for m in live] == [5, 30, 60], [m.get("n") for m in live]
assert all(m["kind"] == "line" for m in live)
assert live[1]["keep"] > 0 and live[2]["keep"] > 0, "only what changed is sent again"
line = []
for m in live:
    del line[m["keep"]:]
    line += m["add"]
assert of("done", got)[0]["undo"] == "Draw"
assert oanim.wm.undo_history()[0][-1] == "Draw" and oanim.wm.undo_history()[1] == undo_before + 1
assert shapes() == 1
drawn = points()
# The line shown ends where the line made does (canvas pixels to the document: the camera's frame, 2 units tall).
end_px = line[-4:-2]
to_doc = lambda x, y: ((x - W / 2) / (H / 2), (H / 2 - y) / (H / 2))
last = to_doc(*end_px)
assert min(math.hypot(last[0] - p[0], last[1] - p[1]) for p in drawn) < 2.0 / H, (last, drawn[-3:])
assert of("canvas", got) and any(isinstance(v, str) and "<path" in v for v in of("canvas", got)[-1]["body"]), \
    "the canvas sent again with the line in it"

# The same samples through draw.stroke, in the layer's space with the iPad's pixel: the same points. With Size Unit
# View the width follows the iPad's zoom, so a pen sized on screen is that size on the iPad.
for view in (False, True):
    doc, _ = fresh()
    oanim.wm.set_draw(size_view=view, view_size=9.0)
    zoom = 0.37
    stroke(wave(), zoom=zoom)
    by_ipad = points()
    width_ipad = oanim.data.layers.active.shape_style(0)["line_width"]
    doc, _ = fresh()
    oanim.wm.set_draw(size_view=view, view_size=9.0)
    rows = [(to_doc(r[0], r[1]) + (r[2], r[5])) for r in wave()]
    pixel = (2.0 / H) / zoom
    ops.draw.stroke(samples=";".join("%.9f,%.9f,%.9f,%.9f" % r for r in rows), pixel=pixel)
    by_op = points()
    assert len(by_ipad) == len(by_op) and all(math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-4 for a, b in zip(by_ipad, by_op)), \
        (view, by_ipad[:3], by_op[:3])
    width_op = oanim.data.layers.active.shape_style(0)["line_width"]
    assert abs(width_ipad - width_op) < 1e-7, (view, width_ipad, width_op)
    if view:
        assert abs(width_op - 9.0 * pixel) < 1e-6, "9 of the iPad's screen pixels wide"

# --- What refuses a stroke, as the viewport --------------------------------------------------------------------------------
doc, _ = fresh()
ops.wm.tool_select()
got = messages({"t": "down", "zoom": 1, "s": wave()[:3]})
assert of("refused", got)[0]["why"] == "Switch to Draw in Open Animate"
assert of("state", got)[0]["refused"] == "Switch to Draw in Open Animate"
messages({"t": "up", "s": []})
assert shapes() == 0
ops.wm.tool_draw(mode="FREEHAND")
doc.frame_current = 3
assert of("refused", messages({"t": "down", "zoom": 1, "s": wave()[:3]}))[0]["why"] == "Switch to Setup (frame 0) to draw"
doc.frame_current = 0

# --- The eraser end erases; the Fill Pen paints ------------------------------------------------------------------------------
doc, _ = fresh()
stroke(wave())
assert shapes() == 1
cross = [[W * 0.45, H * 0.2 + i * H * 0.02, 0.8, 0, 0, i / 100] for i in range(40)]
got = stroke(cross, eraser=True)
assert of("done", got)[0]["undo"] == "Erase Line", of("done", got)
assert of("live", got)[0]["color"] == [0.9, 0.3, 0.3, 0.4], "an eraser's path shows as the viewport's"
ops.wm.tool_draw(mode="FILL_PEN")
got = stroke([[W * 0.6 + 40 * math.cos(i / 6), H * 0.3 + 40 * math.sin(i / 6), 1, 0, 0, i / 100] for i in range(40)])
assert of("done", got)[0]["undo"] == "Paint Fill"

# --- A stroke being drawn: the header and the gestures wait; a page going drops it ---------------------------------------------
doc, _ = fresh()
history = oanim.wm.undo_history()[1]
messages({"t": "down", "zoom": 1, "s": wave()[:5]})
messages({"t": "undo"})
assert oanim.wm.undo_history()[1] == history, "no undo mid-stroke"
messages({"t": "_close"})
assert not _oanim.ipad_stroke_active() and shapes() == 0
messages({"t": "_open"})

# --- Undo and redo (two and three fingers) ------------------------------------------------------------------------------------
stroke(wave())
assert shapes() == 1
got = messages({"t": "undo"})
assert shapes() == 0 and of("canvas", got), "undone, and the canvas sent again"
messages({"t": "redo"})
assert shapes() == 1

# --- The header's settings, as the PC's fields make them ----------------------------------------------------------------------
doc, _ = fresh()
got = messages({"t": "set", "values": {"size_px": 12.0}})
assert abs(oanim.wm.draw_settings()["line_width"] - 12.0 / (doc.height / 2)) < 1e-6
assert abs(of("state", got)[0]["size_px"] - 12.0) < 1e-4, "and the state sent back says so"
messages({"t": "set", "values": {"opacity": 0.4, "taper_start": 30, "stabilizer": "PULLED_STRING", "use_pressure": False}})
s = oanim.wm.draw_settings()
assert abs(s["line_color"][3] - 0.4) < 1e-6 and s["taper_start"] == 30 and s["stabilizer"] == "PULLED_STRING"
assert not s["use_pressure"]
messages({"t": "set", "values": {"size_view": True}})
messages({"t": "set", "values": {"size_px": 20}})
assert abs(oanim.wm.draw_settings()["view_size"] - 20) < 1e-6, "with Size Unit View the size is on screen"
ops.wm.tool_draw(mode="FILL_PEN")
messages({"t": "set", "values": {"opacity": 0.25}})
assert abs(oanim.wm.draw_settings()["fill_color"][3] - 0.25) < 1e-6, "the Fill Pen's opacity is its fill's"
got = messages({"t": "set", "values": {"line_color": [1, 0, 0, 1]}})
assert of("state", got)[0]["settings"]["line_color"] == [1.0, 0.0, 0.0, 1.0]
got = messages({"t": "preset", "name": "Marker"})
assert oanim.wm.draw_settings()["preset"] == "Marker" and of("state", got)[0]["preset"] == "Marker"
assert of("tiles", got), "the tiles follow the settings"

# --- A brushed line: its stamps, the brush's pictures sent once -----------------------------------------------------------------
doc, _ = fresh()
preview = of("brush", messages({"t": "brush", "name": "Round"}))[0]["preview"]
assert preview["kind"] == "dabs" and preview["pngs"], "the brush button's picture, stamped with the brush"
# With how the brush lays its stamps: the page stamps the tip it draws ahead of the line sent back (app.js stampsTip).
tip = preview["tip"]
assert tip["spacing"] == 0.25 and tip["roundness"] == 1 and tip["align"] is False and tip["aspects"] == [1], tip
got = messages({"t": "down", "zoom": 1, "s": wave()[:20]})
got += messages({"t": "move", "s": wave()[20:40]})
dabs = of("live", got)
assert [m["kind"] for m in dabs] == ["dabs", "dabs"], [m["kind"] for m in dabs]
first, second = dabs
image = str(first["images"][0]["id"])
assert image in preview["pngs"] and first["pngs"] == {} and second["pngs"] == {}, "the brush's picture sent once"
messages({"t": "_open"})
got = messages({"t": "move", "s": wave()[40:45]})
assert image in of("live", got)[0]["pngs"], "and again to a page that connects"
assert second["images"][0]["keep"] > 0 and second["images"][0]["keep"] % 6 == 0, "stamps already down stay"
assert len(first["images"][0]["add"]) % 48 == 0, "two triangles a stamp, eight numbers a corner"
assert of("done", messages({"t": "up", "s": []}))[0]["undo"] == "Draw"
# Every setting of the brush, for the tip's stamps to turn, size and scatter as the line's will.
assert tip["brush"]["count"] == 1 and tip["brush"]["jitter"] == 0 and tip["brush"]["randomOrder"] in (True, False), tip["brush"]
assert {"sizeJitter", "scatter", "hueDrift", "opacityJitter", "shapeDynamics", "sizeFadeIn"} <= set(tip["brush"]), tip["brush"]
# The line sent back says its seed, how many places it stamped and where the last is: the tip goes on from there.
add = first["images"][0]["add"]
# (A place may have no stamp: the line's first, where its start taper is nothing wide.)
assert isinstance(first["seed"], int) and 0 <= first["places"] - len(add) // 48 <= 1, (first["places"], len(add) // 48)
centre = [(add[-48] + add[-32]) / 2, (add[-47] + add[-31]) / 2]
assert math.hypot(centre[0] - first["last"][0], centre[1] - first["last"][1]) < 0.02, (centre, first["last"])


# While it's drawn, the line's end neither tapers nor fades out: the page draws the line on past it (its tip), so a
# narrowed end would pinch where the two meet. The end tapers once it's done.
def line_end(taper, brushed):
    fresh()
    if brushed:
        messages({"t": "brush", "name": "Round"})
        ops.brush.setting_set(setting="sizeFadeOut", value="8" if taper else "0", target="TOOL")
    oanim.wm.set_draw(taper_end=200.0 if taper else 0.0)
    got = messages({"t": "down", "zoom": 1, "s": wave()[:40]})
    m = of("live", got)[-1]
    messages({"t": "up", "s": []})
    if brushed:
        add = m["images"][0]["add"]
        return math.hypot(add[-40] - add[-48], add[-39] - add[-47])
    return m["add"][-2]


for brushed in (False, True):
    open_end, tapered = line_end(False, brushed), line_end(True, brushed)
    assert open_end > 1 and abs(tapered - open_end) < 1e-3 * open_end, (brushed, open_end, tapered)

# --- The canvas: guides show (a reference picture often is one), and the onion skins -------------------------------------------
doc, _ = fresh()
layer = oanim.data.layers.active
layer.add_curve([(-0.5, 0.0), (0.5, 0.0)])
messages({"t": "_open"})
with_line = of("canvas", messages())
svg = json.loads(_oanim.ipad_canvas(W, H))["svg"]
layer.render_visible = False
guide_svg = json.loads(_oanim.ipad_canvas(W, H))["svg"]
assert guide_svg == svg, "a guide is on the iPad's canvas as on the viewport"
layer.render_visible = True
ops.layer.new()
moving = oanim.data.layers.active
moving.add_curve([(0.0, 0.0), (0.0, 0.5)])
for frame, x in ((10, 0.2), (20, 0.4)):
    doc.frame_current = frame
    moving.location_x = x
doc.frame_current = 20
doc.onion_skin = True
canvas = json.loads(_oanim.ipad_canvas(W, H))
assert canvas["frame"] == 20 and len(canvas["onion"]) == 1 and canvas["onion"][0]["lines"], canvas["onion"]
ghost_x = canvas["onion"][0]["lines"][0][0]
assert abs(ghost_x - (W / 2 + 0.2 * H / 2)) < 1.0, ("the ghost where frame 10 has it", ghost_x)
st = of("state", messages())
doc.onion_skin = False
assert json.loads(_oanim.ipad_canvas(W, H))["onion"] == []


# --- Lines drawn fast one after another: each answered by its id, the canvas saying how many strokes it shows -----------
# (The page keeps a lifted line drawn until a canvas shows it; none is sent while another line is being drawn.)
doc, got = fresh()
made = of("canvas", got)[0]["strokes"]
rows = wave()
got = messages({"t": "down", "id": 11, "zoom": 1, "s": rows[:20]}, {"t": "move", "s": rows[20:]},
               {"t": "up", "s": []}, {"t": "down", "id": 12, "zoom": 1, "s": rows[:20]})
assert [(m["t"], m.get("id")) for m in got] == [("live", 11), ("live", 11), ("done", 11), ("live", 12)], \
    [(m["t"], m.get("id")) for m in got]
assert of("done", got)[0]["count"] == made + 1
got = messages({"t": "move", "s": rows[20:]}, {"t": "up", "s": []})
assert of("live", got)[0]["id"] == 12 and of("done", got)[0]["id"] == 12 and of("done", got)[0]["count"] == made + 2
canvas = of("canvas", got)
assert len(canvas) == 1 and canvas[0]["strokes"] == made + 2 and shapes() == 2, "the canvas shows both lines"
# A refused stroke says which.
ops.wm.tool_select()
assert of("refused", messages({"t": "down", "id": 13, "zoom": 1, "s": rows[:3]}))[0]["id"] == 13
ops.wm.tool_draw(mode="FREEHAND")


# --- An undo sends only what it changed: the canvas in pieces, those the last canvas had sent as their places ---------------
doc, got = fresh()
for k in range(6):
    stroke([[x, y + (k + 1) * H * 0.06, p, a, b, t] for x, y, p, a, b, t in wave()])
assert shapes() == 6
stroke(wave())
assert page["svg"] == whole(json.loads(_oanim.ipad_canvas(W, H))["svg"])
full_size = len(json.dumps(json.loads(_oanim.ipad_canvas(W, H))))
got = messages({"t": "undo"})
undo_canvas = of("canvas", got)[0]
assert undo_canvas["base"] != 0 and not any(isinstance(v, str) for v in undo_canvas["body"] + undo_canvas["defs"]),     ("an undo sends the shapes left as their places", undo_canvas["body"])
assert len(json.dumps(undo_canvas)) < full_size / 4, (len(json.dumps(undo_canvas)), full_size)
assert page["svg"] == whole(json.loads(_oanim.ipad_canvas(W, H))["svg"]), "the page's canvas is the frame's"
got = messages({"t": "redo"})
assert sum(isinstance(v, str) for v in of("canvas", got)[0]["body"]) == 1, "the line drawn again, alone"
assert page["svg"] == whole(json.loads(_oanim.ipad_canvas(W, H))["svg"])
# A page that lost track asks for the canvas whole.
got = messages({"t": "canvas_full"})
assert of("canvas", got)[0]["base"] == 0 and page["svg"] == whole(json.loads(_oanim.ipad_canvas(W, H))["svg"])
# Pieces that are alike are each kept (the page clones a node used twice).
head, defs, body = ipad.svg_pieces('<?xml version="1.0"?>\n<svg a="1"><defs><mask id="m0"><path d="M0 0"/></mask></defs>'
                                   '<path d="M1 1"/><g mask="url(#m0)"><path d="M2 2"/></g><path d="M1 1"/></svg>')
assert head.endswith('<svg a="1">') and defs == ['<mask id="m0"><path d="M0 0"/></mask>'], (head, defs)
assert body == ['<path d="M1 1"/>', '<g mask="url(#m0)"><path d="M2 2"/></g>', '<path d="M1 1"/>'], body


# --- The canvas keeps each layer's shapes for the next: what it takes from it is what working them out again gives ------
doc, got = fresh()
layers = oanim.data.layers
art = layers.active
art.add_curve([(0.1, 0.0), (0.3, 0.1), (0.7, 0.0), (0.9, 0.1)])
art.add_curve([(0.2, -0.4), (0.8, -0.4), (0.8, -0.1), (0.2, -0.1)], closed=True, fill=True)
ops.layer.new_bone()
rig = layers.active
layers.active = art
ops.layer.move_to_group(group=str(rig.id))
layers.active = rig
ops.armature.bone_add(name="upper_L", head_x="0", head_y="0", tail_x="0.5", tail_y="0")
ops.armature.bone_add(name="lower_L", head_x="0.5", head_y="0", tail_x="1", tail_y="0")
layers.active = art
assert ops.weight.automatic() == {'FINISHED'}
ops.layer.new()
other = layers.active
other.add_curve([(-0.8, -0.5), (-0.2, -0.5), (-0.2, 0.1), (-0.8, 0.1)], closed=True, fill=True)
ops.layer.new()
cut = layers.active
cut.name = "cut"
cut.add_curve([(-0.5, -0.8), (0.0, -0.8), (0.0, 0.0), (-0.5, 0.0)], closed=True, fill=True)
cut.visible = False
layers.active = other
assert ops.mask.add(sources="cut", mode="SUBTRACT") == {'FINISHED'}
layers.active = art


def canvas_same(what):
    cached = json.loads(_oanim.ipad_canvas(W, H))["svg"]
    counts = _oanim.ipad_canvas_cache()
    fresh_svg = json.loads(_oanim.ipad_canvas(W, H, cached=False))["svg"]
    assert cached == fresh_svg, ("the canvas as worked out afresh", what, counts)
    return counts


canvas_same("first")
reused, made = canvas_same("nothing changed")
assert reused >= 3 and made == 0, (reused, made)
doc.frame_current = 5
canvas_same("frame 5")
rig.bone_set("lower_L", angle=0.8)
assert canvas_same("a bone bends the drawing")[1] >= 1
doc.frame_current = 0
canvas_same("back to the setup frame")
art.set_shape_style(1, fill=(0.2, 0.6, 0.9, 1.0))
assert canvas_same("a shape's colour")[1] >= 1
other.opacity = 0.5
canvas_same("a layer's opacity")
cut.add_curve([(0.3, 0.3), (0.5, 0.3), (0.5, 0.5)], closed=True, fill=True)
canvas_same("the mask's shapes")
doc.render_quality = 8
canvas_same("the render quality")
doc.render_quality = 32
oanim.data.camera.zoom = 1.5
canvas_same("the camera")
oanim.data.camera.zoom = 1.0
for frame, x in ((10, 0.3), (20, -0.2)):
    doc.frame_current = frame
    other.location_x = x
canvas_same("keyed motion, frame 20")
doc.frame_current = 10
canvas_same("frame 10")
doc.frame_current = 0
canvas_same("the setup frame")
stroke(wave())
canvas_same("a line drawn on the iPad")
messages({"t": "undo"})
canvas_same("undone")
messages({"t": "redo"})
canvas_same("redone")
ops.layer.delete()
canvas_same("a layer deleted")

# Every line on one layer: an undo works out no line again, only the canvas without the line taken back, and a line
# drawn works out only itself, also after the layer was taken whole from the last canvas.
def lines_after(got):
    """(lines' outlines found again, made) in the canvas that came with what the page sent, or the next."""
    if not any(m["t"] == "canvas" for m in got):
        _oanim.ipad_canvas(W, H)
    return _oanim.ipad_canvas_lines()


ops.layer.new()
one = layers.active
for k in range(6):
    stroke([[x + W * 0.05 * k, y + H * 0.04 * k, p, a, b, t] for x, y, p, a, b, t in wave()])
canvas_same("six lines on one layer")
time.sleep(0.11)
lines_reused, lines_made = lines_after(messages({"t": "undo"}))
canvas_same("one of the six undone")
assert lines_made == 0 and lines_reused >= 5, (lines_reused, lines_made)
messages({"t": "redo"})
canvas_same("redone, the six again")
ops.layer.new()
time.sleep(0.11)
assert lines_after(stroke([[x, y - H * 0.2, p, a, b, t] for x, y, p, a, b, t in wave()]))[1] >= 1
canvas_same("a line on another layer")
layers.active = one
time.sleep(0.11)
lines_reused, lines_made = lines_after(stroke([[x, y + H * 0.3, p, a, b, t] for x, y, p, a, b, t in wave()]))
canvas_same("a seventh line")
assert lines_reused >= 6 and 1 <= lines_made <= 2, (lines_reused, lines_made)

# The page's input log (Options > Send Input Log) is saved where input_log_path() says, the last 2000 rows.
log_path = ipad.input_log_path()
assert os.path.basename(log_path) == "ipad_input_log_background.json", "never the one an iPad sent"
if os.path.exists(log_path):
    os.remove(log_path)
got = messages({"t": "input_log", "agent": "test", "page": {"mode": "FREEHAND", "holds": 1},
                "events": [[k, "touchstart", "direct", 1, 10, 10, 20, 0, 1] for k in range(2500)]})
with open(log_path, encoding="utf-8") as f:
    saved = json.load(f)
assert saved["agent"] == "test" and len(saved["events"]) == 2000 and saved["events"][0][0] == 500, len(saved["events"])
assert saved["page"] == {"mode": "FREEHAND", "holds": 1} and saved["drawing"] is False, (saved["page"], saved["drawing"])
# The page is told it got here, so it can say so (or that it didn't).
assert of("input_log_saved", got) == [{"t": "input_log_saved", "path": log_path, "rows": 2000}], of("input_log_saved", got)
assert of("input_log_saved", messages({"t": "input_log", "events": "not a list"})) == [], "nothing saved, nothing said"
# Taken while the PC thinks a stroke is going too (the header's messages wait for its end): what the log is for is
# finding out what went wrong, a stroke stuck included.
os.remove(log_path)
messages({"t": "down", "zoom": 1, "s": wave()[:5]})
got = messages({"t": "input_log", "agent": "mid-stroke", "events": [[1, "touchstart"]]})
assert of("input_log_saved", got) and json.load(open(log_path, encoding="utf-8"))["drawing"] is True
messages({"t": "cancel"})
os.remove(log_path)

# --- What a page gone wrong (or anyone on the network) can't do ---------------------------------------------------------
# NaN, Infinity and numbers too big for a float never reach the settings: the message is dropped.
width = oanim.wm.draw_settings()["line_width"]
for bad in ('{"t":"set","values":{"line_width":NaN}}', '{"t":"set","values":{"line_width":Infinity}}',
            '{"t":"set","values":{"line_width":1e999}}', '{"t":"set","values":{"line_color":[NaN,0,0,1]}}'):
    ipad._tick([(CLIENT, bad)])
    s = oanim.wm.draw_settings()
    assert s["line_width"] == width and all(math.isfinite(c) for c in s["line_color"]), bad
for key_name, value in (("line_width", float("nan")), ("fill_color", (0, float("inf"), 0, 1)),
                        ("prediction", float("nan")), ("pressure_curve", (0.2, float("nan"), 0.8, 0.8))):
    try:
        oanim.wm.set_draw(**{key_name: value})
        raise AssertionError("set_draw took a non-finite " + key_name)
    except ValueError:
        pass
oanim.wm.set_draw(line_width=1e30)
assert oanim.wm.draw_settings()["line_width"] <= 100.0
oanim.wm.set_draw(line_width=width)
# A message that makes no sense is dropped alone: those after it are handled, a stroke it broke is let go.
weld = oanim.wm.draw_settings()["weld"]
ipad._tick([(CLIENT, '{"t":"set","values":{"no_such_setting":1}}'),
            (CLIENT, json.dumps({"t": "down", "id": 99, "zoom": 1, "s": [["a", 1, 1, 0, 0, 0]]})),
            (CLIENT, json.dumps({"t": "set", "values": {"weld": not weld}}))])
assert oanim.wm.draw_settings()["weld"] == (not weld) and ipad._drawing is None
oanim.wm.set_draw(weld=weld)

# The server: a few pages at once, no message over 4 MB, a limit to connections (with or without the key).
port = ipad.start(0)
key = ipad.url().split("k=")[1]
pages = [ws_open(port, key) for _ in range(4)]
assert all(b"101" in status for _, status in pages), [status for _, status in pages]
extra, status = ws_open(port, key)
assert b"503" in status, status
extra.close()
for p, _ in pages:
    p.close()
take_messages()
time.sleep(0.3)
big, status = ws_open(port, key)
assert b"101" in status
data = b'{"t":"x","pad":"' + b"y" * (5 << 20) + b'"}'
mask = os.urandom(4)
try:
    big.sendall(bytes([0x81, 0x80 | 127]) + struct.pack(">Q", len(data)) + mask)
    big.settimeout(5)
    assert big.recv(1) == b"", "a message over 4 MB closes the connection"
except (ConnectionResetError, ConnectionAbortedError):
    pass
big.close()
idle = []
for _ in range(40):
    c = socket.create_connection(("127.0.0.1", port), timeout=5)
    idle.append(c)
time.sleep(0.5)
closed = 0
for c in idle:
    c.settimeout(0.2)
    try:
        closed += c.recv(1) == b""
    except socket.timeout:
        pass
    except (ConnectionResetError, ConnectionAbortedError):
        closed += 1
assert closed >= 8, closed
for c in idle:
    c.close()
ipad.stop()
take_messages(0.3)

print("ipad: ok")
