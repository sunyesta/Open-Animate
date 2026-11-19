"""Gradient layers: a vector layer whose one curve is a path of colour stops, filling the camera frame. Its points are
its stops, never added or taken away but with the Gradient tab's + and - (gradient.stop_add, stop_remove); ticks slide
where each span's colours meet half way. Where a place is along the path is a smooth field (no crease inside a bend),
colours mix in OKLab, a Smooth span has no jump in how fast the colour changes at a stop, and it all saves.

Run with:  OpenAnimate --background --python tests/test_gradient_layer.py
"""

import os
import tempfile

import oanim

ops, L = oanim.ops, oanim.data.layers


def scene(**kw):
    """A new gradient from (-1, 0) to (1, 0), black to white unless told otherwise."""
    ops.wm.read_homefile(confirmed="1")
    args = dict(x1="-1", y1="0", x2="1", y2="0")
    args.update(kw)
    assert ops.layer.new_gradient(**args) == {'FINISHED'}
    g = L.active
    assert g.is_gradient
    return oanim.data.document, g


CREASE = 0.002


def color(g, x, y):
    return g.gradient_sample(x, y)["color"]


def close(a, b, eps=2e-3):
    return all(abs(p - q) < eps for p, q in zip(a, b))


def oklab_mid_grey():
    """Black and white mixed half way in OKLab: lightness 0.5, as sRGB."""
    lin = 0.5 ** 3
    return 1.055 * lin ** (1 / 2.4) - 0.055


# --- A new gradient: two stops, its colours along the path, the same across it --------------------------------------
doc, g = scene()
d = g.gradient
assert d["on"] and len(d["stops"]) == 2 and len(g.points) == 2, d
assert close(color(g, -1, 0), (0, 0, 0, 1)) and close(color(g, 1, 0), (1, 1, 1, 1)), (color(g, -1, 0), color(g, 1, 0))
assert close(color(g, -3, 0.5), (0, 0, 0, 1)) and close(color(g, 3, -0.5), (1, 1, 1, 1)), "the end colours carry on"
mid = color(g, 0, 0)
assert abs(mid[0] - oklab_mid_grey()) < 0.01, ("mixed in OKLab", mid, oklab_mid_grey())
for x in (-0.6, -0.2, 0.3, 0.7):
    assert close(color(g, x, 0.0), color(g, x, 0.4), 4e-3), ("a straight path is a linear gradient", x)
values = [color(g, -1 + 0.05 * i, 0)[0] for i in range(41)]
assert all(b >= a - 1e-5 for a, b in zip(values, values[1:])), ("never back and forth", values)
g.gradient_mix = 'RGB'
assert abs(color(g, 0, 0)[0] - 0.5) < 0.01, ("RGB mixes the plain values", color(g, 0, 0))

# --- Its points can't be added or taken away but through its stops ---------------------------------------------------
doc, g = scene()
ops.mesh.select_all()
before = g.points
shown = oanim.wm.banner_report()[0]
for op in (ops.mesh.delete_points, ops.mesh.dissolve_points, ops.mesh.subdivide, ops.mesh.extrude):
    op()
    assert g.points == before and len(g.gradient["stops"]) == 2, (op, g.points)
assert oanim.wm.banner_report()[0] > shown and "stops" in oanim.wm.banner_report()[3], oanim.wm.banner_report()
# On another frame than the last undo step's too, where the step's check could only make the new point a stop.
doc.frame_current = 5
ops.mesh.select_all()
ops.mesh.subdivide()
assert len(g.points) == 2 and len(g.gradient["stops"]) == 2, ("frame 5", g.points)
doc.frame_current = 0
# A script's data edit is put back at the next undo step.
g.split_segment(0, 0, 0.5)
assert len(g.points) == 3
assert ops.gradient.stop_set(stop="0", color="#102030") == {'FINISHED'}
assert len(g.points) == 2 and len(g.gradient["stops"]) == 2, g.points
assert close(g.gradient["stops"][0]["color"], (0x10 / 255, 0x20 / 255, 0x30 / 255, 1)), g.gradient["stops"][0]
# Moving them is fine.
ops.mesh.select_all()
assert ops.mesh.translate(move_x="0.5") == {'FINISHED'}
assert close([p[0] for p in g.points], [-0.5, 1.5]), g.points

# --- Adding a stop at a tick keeps the path and the colour there; removing one joins its spans -----------------------
doc, g = scene(color1="#2040a0", color2="#ffe080")
places = g.gradient_places()
tick = places["ticks"][0]
was = color(g, tick[1], tick[2])
was_off = color(g, 0.37, 0.3)
assert ops.gradient.stop_add() == {'FINISHED'}
d = g.gradient
assert len(d["stops"]) == 3 and len(g.points) == 3 and d["active_stop"] == 1, d
assert close(d["stops"][1]["color"], was, 3e-3), (d["stops"][1]["color"], was)
assert any(close(p[:2], tick[1:], 1e-3) for p in g.points), ("the new point is on the tick", g.points, tick)
assert abs(g.gradient_places()["length"] - places["length"]) < 1e-3, "the path kept its shape"
assert close(color(g, 0.37, 0.3), was_off, 0.06), ("much as it was", color(g, 0.37, 0.3), was_off)
assert ops.gradient.stop_remove() == {'FINISHED'}
assert len(g.gradient["stops"]) == 2 and len(g.points) == 2
assert ops.gradient.stop_remove() == {'CANCELLED'}, "two stay"
ops.ed.undo()
assert len(g.gradient["stops"]) == 3 and len(g.points) == 3, "undone"
# Taking away an end stop: the next one is the end.
assert ops.gradient.stop_remove(stop="0") == {'FINISHED'}
assert len(g.points) == 2 and close(color(g, -1, 0), was, 3e-3), ("the path starts at the tick now", color(g, -1, 0), was)

# --- A span's tick: where its colours meet half way; Linear, Hard -----------------------------------------------------
doc, g = scene()
assert ops.gradient.span_set(span="0", midpoint="0.25", falloff="LINEAR") == {'FINISHED'}
assert abs(color(g, -0.5, 0)[0] - oklab_mid_grey()) < 0.01, ("half way at a quarter along", color(g, -0.5, 0))
assert close(color(g, -1, 0), (0, 0, 0, 1)) and close(color(g, 1, 0), (1, 1, 1, 1))
assert ops.gradient.span_set(falloff="HARD") == {'FINISHED'}
assert close(color(g, -0.55, 0), (0, 0, 0, 1)) and close(color(g, -0.45, 0), (1, 1, 1, 1)), "at once at the tick"
assert ops.gradient.span_set(falloff="NONE") == {'CANCELLED'}
# Dragged as in the viewport: the place on the span nearest the mouse; one undo step.
doc, g = scene()
assert abs(g.gradient_handle_drag(0, 0.2, 0.7) - 0.6) < 2e-3, g.gradient
assert abs(g.gradient["stops"][0]["midpoint"] - 0.6) < 2e-3
ops.ed.undo()
assert abs(g.gradient["stops"][0]["midpoint"] - 0.5) < 1e-6, "undone"
assert abs(g.gradient_handle_drag(0, -5.0, 0.0) - 0.02) < 1e-6, "kept inside its span"

# --- Smooth: no jump in how fast the colour changes as it passes a stop ----------------------------------------------
doc, g = scene(color1="#000000", color2="#ffffff")
assert ops.gradient.stop_add() == {'FINISHED'}
assert ops.gradient.stop_set(stop="1", color="#b0b0b0") == {'FINISHED'}
h = 0.01
left = (color(g, 0, 0)[0] - color(g, -h, 0)[0]) / h
right = (color(g, h, 0)[0] - color(g, 0, 0)[0]) / h
assert left > 0.05 and abs(left - right) < 0.25 * left, ("no kink at the stop", left, right)
assert ops.gradient.span_set(span="0", falloff="LINEAR") == {'FINISHED'}
assert ops.gradient.span_set(span="1", falloff="LINEAR") == {'FINISHED'}
left = (color(g, 0, 0)[0] - color(g, -h, 0)[0]) / h
right = (color(g, h, 0)[0] - color(g, 0, 0)[0]) / h
assert abs(left - right) > 0.25 * left, ("Linear spans do kink there", left, right)

# --- Ends: Repeat and Reflect ------------------------------------------------------------------------------------------
doc, g = scene()
g.gradient_ends = 'REPEAT'
assert close(color(g, 1.5, 0), color(g, -0.5, 0), 3e-3), (color(g, 1.5, 0), color(g, -0.5, 0))
g.gradient_ends = 'REFLECT'
assert close(color(g, 1.5, 0), color(g, 0.5, 0), 3e-3), (color(g, 1.5, 0), color(g, 0.5, 0))

# --- Round a bend the bands bend smoothly: no crease on its inside ----------------------------------------------------
doc, g = scene()
# An arch: both handles pulled up, so the path runs up, across and down. Across its inside, how far along the path a
# place is goes smoothly from one leg to the other (the nearest place on the path would jump at the middle).
g.place_handle(0, 0, "OUT", (-1.0, 1.6))
g.place_handle(0, 1, "IN", (1.0, 1.6))
alongs = [g.gradient_sample(-0.8 + 0.01 * i, 0.3)["along"] for i in range(161)]
steps = [b - a for a, b in zip(alongs, alongs[1:])]
jumps = [abs(b - a) for a, b in zip(steps, steps[1:])]
assert all(s > 0 for s in steps), ("from one leg to the other", alongs)
assert max(jumps) < CREASE, ("smooth through the middle of the bend", max(jumps), max(steps))

# --- Radial: rings round the first stop, squashed across the path ------------------------------------------------------
doc, g = scene()
g.gradient_type = 'RADIAL'
assert close(color(g, -1, 1), color(g, 0, 0), 3e-3), ("as far round", color(g, -1, 1), color(g, 0, 0))
assert not close(color(g, -1, 0.5), color(g, 0, 0), 3e-3)
g.gradient_squash = 0.5
assert close(color(g, -1, 0.5), color(g, 0, 0), 3e-3), ("half as far across", color(g, -1, 0.5), color(g, 0, 0))
assert abs(g.gradient_handle_drag(-1, -1.0, 0.25) - 0.125) < 1e-3, g.gradient["squash"]
assert abs(g.gradient["squash"] - 0.125) < 1e-3
ops.ed.undo()
# (Set from Python, 0.5 was no undo step of its own: undo goes back to the step before.)
assert abs(g.gradient["squash"] - 1.0) < 1e-6, ("undone", g.gradient["squash"])

# --- It moves with its layer, and its picture is what renders sample -------------------------------------------------
doc, g = scene(color1="#2040a0", color2="#ffe080")
was = color(g, 0.2, 0.0)
g.location_x = 0.5
assert close(color(g, 0.7, 0.3), was, 3e-3), "the gradient moved with the layer"
w, h = 64, 36
img = g.gradient_image(w, h)
assert len(img) == w * h * 4
aspect = doc.width / doc.height
for (i, j) in ((5, 5), (32, 18), (60, 30)):
    o = (j * w + i) * 4
    px = [img[o + k] / 255 for k in range(3)]
    # The pixel's middle: the camera frame is [-aspect, aspect] x [-1, 1] about the origin, as is the document.
    x, y = (2 * (i + 0.5) / w - 1) * aspect, 1 - 2 * (j + 0.5) / h
    assert close(oanim.data.camera.to_frame((x, y)), (x, y), 1e-4)
    c = color(g, x, y)
    assert img[o + 3] == 255 and close(px, c[:3], 0.03), ((i, j), px, c)

# --- Saved and opened as it was -----------------------------------------------------------------------------------------
doc, g = scene(color1="#2040a0", color2="#ffe080aa")
ops.gradient.stop_add()
ops.gradient.span_set(span="1", midpoint="0.3", falloff="HARD")
g.gradient_type = 'RADIAL'
g.gradient_ends = 'REFLECT'
g.gradient_mix = 'RGB'
g.gradient_squash = 0.4
want = g.gradient
want_points = g.points
name = g.name
path = os.path.join(tempfile.mkdtemp(), "gradient.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
g = L[name]
got = g.gradient
for k in ("on", "type", "ends", "mix"):
    assert got[k] == want[k], (k, got[k], want[k])
assert abs(got["squash"] - want["squash"]) < 1e-6
for a, b in zip(got["stops"], want["stops"]):
    assert a["point"] == b["point"] and a["falloff"] == b["falloff"] and abs(a["midpoint"] - b["midpoint"]) < 1e-6
    assert close(a["color"], b["color"], 1e-6), (a, b)
assert close([c for p in g.points for c in p[:2]], [c for p in want_points for c in p[:2]], 1e-6)

print("gradient layer: ok")
