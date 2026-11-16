"""Hold to Shape (data/quick_shape.hh, draw.quick_shape): what a held line becomes (a straight line, or the ellipse
that fits a loop), the shape drawn as one undo step, Ellipse or Circle in Adjust Last Operation, Close and Fill.

The pause, the pen moving the shape while held and the handles after lifting need the window: checked live on a
private copy.

Run with:  OpenAnimate --background --python tests/test_hold_to_shape.py
"""

import math

import oanim

wm = oanim.wm
ops = oanim.ops


def fresh():
    ops.wm.read_homefile(confirmed="1")
    ops.layer.new()
    doc = oanim.data.document
    doc.frame_current = 0
    ops.wm.tool_draw(mode="FREEHAND")
    return oanim.data.layers.active, 2.0 / doc.height


def ellipse_points(cx, cy, rx, ry, angle_deg, count=90, turns=1.0, start=0.0):
    a = math.radians(angle_deg)
    out = []
    for i in range(count):
        t = start + 2.0 * math.pi * turns * i / (count - 1)
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return out


def run(args, **extra):
    merged = dict(args)
    merged.update(extra)
    return ops.draw.quick_shape(**merged)


# --- A line held at its end becomes a straight line from its start to the pen ----------------------------------------
layer, pixel = fresh()
wobbly = [(-0.5 + i / 59.0, 0.2 + 0.01 * math.sin(i * 0.7)) for i in range(60)]
fit = wm.quick_shape_fit(wobbly, (0.6, 0.25), pixel)
assert fit is not None and fit["shape"] == "LINE", fit
a = tuple(float(v) for v in fit["a"].split(","))
b = tuple(float(v) for v in fit["b"].split(","))
assert math.dist(a, wobbly[0]) < 1e-6 and math.dist(b, (0.6, 0.25)) < 1e-6, (a, b)
# Too short to be a shape: nothing.
assert wm.quick_shape_fit([(0.0, 0.0), (pixel * 3, 0.0)], (pixel * 3, 0.0), pixel) is None

# --- A loop becomes the ellipse that fits it ---------------------------------------------------------------------------
layer, pixel = fresh()
loop = ellipse_points(0.1, -0.05, 0.4, 0.2, 30.0, count=120, turns=0.97)
fit = wm.quick_shape_fit(loop, loop[-1], pixel)
assert fit is not None and fit["shape"] == "ELLIPSE", fit
cx, cy = (float(v) for v in fit["center"].split(","))
rx, ry = (float(v) for v in fit["radii"].split(","))
angle = float(fit["angle"]) % 180.0
assert math.dist((cx, cy), (0.1, -0.05)) < 0.02, (cx, cy)
assert abs(rx - 0.4) < 0.02 and abs(ry - 0.2) < 0.02, (rx, ry)
assert abs(angle - 30.0) < 3.0, angle
assert fit["circle"] == "0"
# Points bunched where the pen went slowly count no more than the rest.
slow = ellipse_points(0.0, 0.0, 0.3, 0.3, 0.0, count=40, turns=0.25) + ellipse_points(
    0.0, 0.0, 0.3, 0.3, 0.0, count=400, turns=0.72, start=0.5 * math.pi)
fit = wm.quick_shape_fit(slow, slow[-1], pixel)
cx, cy = (float(v) for v in fit["center"].split(","))
assert math.dist((cx, cy), (0.0, 0.0)) < 0.02, ("the mean is over the length, not the points", cx, cy)

# --- The shape is one undo step, an ellipse four smooth points round ---------------------------------------------------
layer, pixel = fresh()
loop = ellipse_points(0.0, 0.0, 0.4, 0.2, 0.0, count=120, turns=0.97)
fit = wm.quick_shape_fit(loop, loop[-1], pixel)
assert run(fit, pixel=pixel, line_width=0.01) == {"FINISHED"}
assert layer.curve_count == 1 and layer.point_count == 4 and layer.shape_count == 1, (layer.curve_count, layer.point_count)
pts = [p[:2] for p in layer.points]
assert all(abs(math.hypot(x / 0.4, y / 0.2) - 1.0) < 0.06 for x, y in pts), pts
outline, closed = layer.shape_outline(0, 8)
assert closed and all(abs(math.hypot(x / 0.4, y / 0.2) - 1.0) < 0.03 for x, y in outline), "a true ellipse between them"
assert all(t == "ALIGNED" for t, _, _ in layer.curve_handles(0))
assert abs(layer.shape_style(0)["line_width"] - 0.01) < 1e-6
assert not layer.shape_style(0)["has_fill"], "Close and Fill is off"
last = wm.last_operation()
assert last is not None and last[0] == "draw.quick_shape", last
ops.ed.undo()
assert layer.curve_count == 0, "one undo step"
ops.ed.redo()
assert layer.curve_count == 1

# --- Ellipse or Circle, changed afterward as Adjust Last Operation does -------------------------------------------------
layer, pixel = fresh()
loop = ellipse_points(0.0, 0.0, 0.4, 0.2, 0.0, count=120, turns=0.97)
fit = wm.quick_shape_fit(loop, loop[-1], pixel)
run(fit, pixel=pixel)
assert wm.redo_last(circle=True) == "FINISHED"
assert layer.curve_count == 1, "the ellipse's step undone first"
outline, closed = layer.shape_outline(0, 8)
radii = [math.hypot(x, y) for x, y in outline]
mean = sum(radii) / len(radii)
assert abs(mean - 0.3) < 0.01 and max(radii) - min(radii) < 0.01, ("a circle of their mean radius", min(radii), max(radii))
assert wm.redo_last(circle=False) == "FINISHED"
outline, _ = layer.shape_outline(0, 8)
assert max(math.hypot(x, y) for x, y in outline) > 0.39, "the ellipse back"

# --- A line: two corners, its width as drawn ---------------------------------------------------------------------------
layer, pixel = fresh()
assert ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0.25", pixel=pixel, radius="0.6") == {"FINISHED"}
assert layer.curve_count == 1 and layer.point_count == 2
pts = [p[:2] for p in layer.points]
assert math.dist(pts[0], (-0.5, 0.0)) < 1e-6 and math.dist(pts[1], (0.5, 0.25)) < 1e-6, pts
assert all(abs(r - 0.6) < 1e-6 for r in layer.radii), layer.radii
# Nothing to draw, or not on the setup frame: no step.
assert ops.draw.quick_shape(shape="LINE", a="0,0", b="0,0") == {"CANCELLED"}
assert ops.draw.quick_shape(shape="ELLIPSE", center="0,0", radii="0,0") == {"CANCELLED"}
assert ops.draw.quick_shape(shape="TRIANGLE") == {"CANCELLED"}
oanim.data.document.frame_current = 4
assert ops.draw.quick_shape(shape="LINE", a="0,0", b="1,0") == {"CANCELLED"}
oanim.data.document.frame_current = 0
assert layer.curve_count == 1

# --- Close and Fill fills an ellipse; welding joins a line's ends -------------------------------------------------------
layer, pixel = fresh()
wm.set_draw(fill=True)
assert ops.draw.quick_shape(shape="ELLIPSE", center="0,0", radii="0.3,0.2", angle="15", pixel=pixel) == {"FINISHED"}
assert layer.shape_style(0)["has_fill"]
wm.set_draw(fill=False)
layer, pixel = fresh()
ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0,0", pixel=pixel)
wm.set_draw(weld=True)
ops.draw.quick_shape(shape="LINE", a="0.001,0", b="0.4,0.4", pixel=pixel)
wm.set_draw(weld=False)
assert layer.point_count == 3, ("its start joined the line it began on", layer.point_count)

# --- The setting, and the brush counted as drawn with ------------------------------------------------------------------
layer, pixel = fresh()
assert wm.draw_settings()["hold_shape"], "on by default"
wm.set_draw(hold_shape=False)
assert not wm.draw_settings()["hold_shape"]
wm.set_draw(hold_shape=True)
before = len(wm.draw_settings()["brush_recent"])
ops.draw.quick_shape(shape="LINE", a="-0.5,0", b="0.5,0", pixel=pixel)
assert len(wm.draw_settings()["brush_recent"]) >= max(before, 1)

print("hold to shape: ok")
