"""The Fill Pen and Fill Eraser (data/fill_paint): each works on the shape its stroke starts on (inside its fill, or on
its line). The Fill Pen grows that shape (its points kept where its outline doesn't change, its line following, a fill
in the pen's colour if it had none; started on nothing, a new shape); the Fill Eraser cuts from it.

The live preview and Ctrl with a real press need the window: checked live on a private copy.

Run with:  OpenAnimate --background --python tests/test_fill_paint.py
"""

import math

import oanim

wm = oanim.wm
ops = oanim.ops
doc = oanim.data.document
pixel = 2.0 / doc.height


def samples(path, count=80, seconds=0.5, pressure=1.0):
    rows = []
    for i in range(count):
        u = i / (count - 1)
        x, y = path(u)
        rows.append("%f,%f,%f,%f" % (x, y, pressure, u * seconds))
    return ";".join(rows)


def stroke(path, **kwargs):
    extra = {k: kwargs.pop(k) for k in list(kwargs) if k == "erase"}
    return ops.draw.stroke(samples=samples(path, **kwargs), pixel=pixel, **extra)


def line(ax, ay, bx, by):
    return lambda u: (ax + (bx - ax) * u, ay + (by - ay) * u)


def covers(layer, shape, x, y):
    return layer.shape_contains(shape, (x, y))


def fresh():
    ops.layer.new()
    return oanim.data.layers.active


# --- The kinds of pen, and each remembering its own -------------------------------------------------------------------
presets = {p["name"]: p for p in wm.draw_presets()}
assert presets["Fill Pen"]["mode"] == "FILL_PEN" and presets["Fill Pen"]["category"] == "Pens"
assert presets["Fill Eraser"]["mode"] == "FILL_ERASER" and presets["Fill Eraser"]["category"] == "Erasers"

ops.wm.tool_draw(mode="FILL_PEN")
assert wm.draw_settings()["mode"] == "FILL_PEN" and wm.draw_settings()["preset"] == "Fill Pen"
line_width = wm.draw_settings()["line_width"]
ops.draw.preset_load(name="Fill Marker")
assert wm.draw_settings()["preset"] == "Fill Marker" and wm.draw_settings()["line_width"] == line_width, "not the lines' width"
ops.wm.tool_draw(mode="FREEHAND")
assert wm.draw_settings()["preset"] == "Ink"
ops.wm.tool_draw(mode="FILL_ERASER")
assert wm.draw_settings()["preset"] == "Fill Eraser"
ops.wm.tool_draw(mode="FILL_PEN")
assert wm.draw_settings()["preset"] == "Fill Marker", "it comes back to the one it last used"
ops.draw.preset_load(name="Fill Pen")

# --- The Fill Pen paints a filled area, with no outline ---------------------------------------------------------------
layer = fresh()
wm.set_draw(fill_size=0.1)
assert stroke(line(-0.5, 0.0, 0.5, 0.0), pressure=1.0) == {"FINISHED"}
assert layer.shape_count == 1 and layer.curve_count == 1
look = layer.shape_style(0)
assert look["has_fill"] and not look["has_outline"], look
assert covers(layer, 0, 0.0, 0.0) and covers(layer, 0, 0.0, 0.045)
assert not covers(layer, 0, 0.0, 0.07), "as wide as the brush"
assert covers(layer, 0, 0.53, 0.0), "round at its end"
assert 3 <= layer.point_count <= 16, ("few points", layer.point_count)
ops.ed.undo()
assert layer.shape_count == 0, "one undo step"
ops.ed.redo()
assert layer.shape_count == 1

# A loop stays one area, a hole in it staying a hole.
layer = fresh()
wm.set_draw(fill_size=0.06)
circle = lambda u: (0.3 * math.cos(u * 2.0 * math.pi), 0.3 * math.sin(u * 2.0 * math.pi))
stroke(circle, count=200, seconds=1.0)
assert layer.shape_count == 1 and layer.curve_count == 2, (layer.shape_count, layer.curve_count)
assert covers(layer, 0, 0.3, 0.0) and covers(layer, 0, -0.3, 0.0)
assert not covers(layer, 0, 0.0, 0.0), "the hole"



def ids_of(layer):
    return set(layer.point_ids)


def through(x, top=0.4):
    """Down and up across y = 0 at `x`, starting there (so it starts on what is there)."""
    return lambda u: (x, top * math.sin(u * 2.0 * math.pi))


# --- The Fill Pen grows the shape it starts on ---------------------------------------------------------------------
layer = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.1)
stroke(line(-0.5, 0.0, 0.0, 0.0))
stroke(line(0.5, 0.5, 0.8, 0.5))
assert layer.shape_count == 2
first = [i for i in range(2) if covers(layer, i, -0.4, 0.0)][0]
kept = ids_of(layer)
assert stroke(line(-0.1, 0.0, 0.4, 0.0)) == {"FINISHED"}
assert layer.shape_count == 2, ("grown, not a new one", layer.shape_count)
assert covers(layer, first, -0.4, 0.0) and covers(layer, first, 0.35, 0.0), "one area"
left_end = [i for i, p in enumerate(layer.points) if p[0] < -0.45]
assert left_end and all(layer.point_ids[i] in kept for i in left_end), "its points where its outline didn't change"
assert not layer.shape_style(first)["has_outline"]
# Over another shape on the way, that one stays as it is: only the shape it starts on grows.
other = 1 - first
before_other = layer.shape_runs(other)
stroke(line(0.35, 0.0, 0.6, 0.5))
assert layer.shape_count == 2, layer.shape_count
assert covers(layer, first, 0.55, 0.45), "grown over it"
assert layer.shape_runs(other) == before_other, "the other shape untouched"
ops.ed.undo()
assert covers(layer, first, 0.35, 0.0) and not covers(layer, first, 0.55, 0.45), "one undo step"

# Started on nothing it makes a new shape on top, in the pen's colour; started on a shape, that shape keeps its colour.
layer = fresh()
stroke(line(-0.5, 0.0, 0.5, 0.0))
colour = layer.shape_style(0)["fill"]
wm.set_draw(fill_color=(0.2, 0.4, 0.8, 1.0))
stroke(line(0.0, 0.0, 0.0, 0.3))
assert layer.shape_count == 1 and layer.shape_style(0)["fill"] == colour, "grown in its own colour"
assert covers(layer, 0, 0.0, 0.28)
stroke(line(0.0, -0.6, 0.0, -0.4))
assert layer.shape_count == 2 and layer.shape_style(1)["fill"] != colour, "a new one on top"
wm.set_draw(fill_color=(0.95, 0.85, 0.7, 1.0))

# Started on a line (just outside the fill): the shape grows, its line going round the new outline.
layer = fresh()
ops.mesh.primitive_box_add(x=0.0, y=0.0, width=0.8, height=0.8, fill="1")
corners = ids_of(layer)
assert not covers(layer, 0, 0.403, 0.0)
assert stroke(line(0.403, 0.0, 0.7, 0.0)) == {"FINISHED"}
assert layer.shape_count == 1, layer.shape_count
look = layer.shape_style(0)
assert look["has_fill"] and look["has_outline"]
assert covers(layer, 0, 0.6, 0.0) and covers(layer, 0, -0.3, 0.0)
assert len(corners & ids_of(layer)) >= 3, "the corners the outline still runs through"
assert layer.shape_outline(0)[1], "still going all the way round"

# A line round with no fill gains one, in the pen's colour.
layer = fresh()
layer.add_curve([(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)], closed=True)
layer.set_shape_style(0, has_fill=False)
ops.mesh.select_none()
wm.set_draw(fill_color=(0.2, 0.4, 0.8, 1.0))
assert stroke(line(0.0, 0.0, 0.2, 0.0)) == {"FINISHED"}
assert layer.shape_count == 1 and layer.shape_style(0)["has_fill"] and layer.shape_style(0)["has_outline"]
assert layer.shape_style(0)["fill"][2] > 0.7, layer.shape_style(0)["fill"]
wm.set_draw(fill_color=(0.95, 0.85, 0.7, 1.0))

# A sub shape grows itself, its parent's points staying.
layer = fresh()
assert layer.add_primitive("BOX", [(-0.5, -0.5), (0.5, 0.5)], fill=True)
assert layer.add_primitive("CIRCLE", [(-0.2, -0.2), (0.2, 0.2)], fill=True)
box = [i for i in range(2) if covers(layer, i, 0.4, 0.4)][0]
circle = 1 - box
ops.mesh.select_none()
assert ops.mesh.shape_parent_set(shape=str(layer.shape_ids[circle]), parent=str(layer.shape_ids[box])) == {"FINISHED"}
circle = [i for i in range(2) if layer.shape_style(i)["parent"] >= 0][0]
box = 1 - circle
box_curves = layer.shape_runs(box)
assert stroke(line(0.0, 0.0, 0.0, 0.35)) == {"FINISHED"}
assert layer.shape_count == 2
circle = [i for i in range(2) if layer.shape_style(i)["parent"] >= 0][0]
assert covers(layer, circle, 0.0, 0.33), "the sub shape grew"
assert layer.shape_runs(1 - circle) == box_curves, "its parent as it was"

# --- The Fill Eraser cuts from the shape it starts on ---------------------------------------------------------------
layer = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.2)
stroke(line(-0.5, 0.0, 0.5, 0.0))
ops.wm.tool_draw(mode="FILL_ERASER")
wm.set_draw(fill_size=0.1)
assert stroke(through(0.0)) == {"FINISHED"}
assert layer.shape_count == 1, ("one shape, in two loops", layer.shape_count)
assert not covers(layer, 0, 0.0, 0.0), "the cut"
assert covers(layer, 0, -0.3, 0.0) and covers(layer, 0, 0.3, 0.0)
ops.ed.undo()
assert layer.shape_count == 1 and covers(layer, 0, 0.0, 0.0)
ops.ed.redo()
# Started on nothing, it cuts nothing: no step at all.
assert stroke(line(0.0, 0.6, 0.0, -0.6)) == {"CANCELLED"}

# Cutting a hole, and cutting it all away.
layer = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.3)
stroke(line(-0.5, 0.0, 0.5, 0.0))
ops.wm.tool_draw(mode="FILL_ERASER")
wm.set_draw(fill_size=0.05)
stroke(line(0.0, 0.0, 0.05, 0.0))
assert layer.shape_count == 1 and layer.curve_count == 2
assert not covers(layer, 0, 0.02, 0.0) and covers(layer, 0, 0.3, 0.0)
wm.set_draw(fill_size=0.9)
stroke(line(0.3, 0.0, -0.7, 0.0))
assert layer.shape_count == 0 and layer.point_count == 0, (layer.shape_count, layer.point_count)

# The shape's line follows the cut: one shape, the corners it doesn't reach kept.
layer = fresh()
ops.mesh.primitive_box_add(x=0.0, y=0.0, width=0.8, height=0.8, fill="1")
corners = ids_of(layer)
right = [layer.point_ids[i] for i, p in enumerate(layer.points) if p[0] > 0.3]
ops.wm.tool_draw(mode="FILL_ERASER")
wm.set_draw(fill_size=0.2)
assert stroke(line(0.0, 0.0, -0.6, 0.0)) == {"FINISHED"}
assert layer.shape_count == 1, layer.shape_count
assert layer.shape_style(0)["has_outline"] and layer.shape_style(0)["has_fill"]
assert not covers(layer, 0, -0.2, 0.0) and covers(layer, 0, 0.2, 0.0)
assert right and all(i in ids_of(layer) for i in right), "the right corners stay"

# Ctrl with the Fill Pen cuts.
layer = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.2)
stroke(line(-0.5, 0.0, 0.5, 0.0))
assert stroke(through(0.0), erase="1") == {"FINISHED"}
assert layer.shape_count == 1 and not covers(layer, 0, 0.0, 0.0)

# Selected Only: the shape it starts on, if selected.
layer = fresh()
stroke(line(-0.5, 0.0, -0.2, 0.0))
stroke(line(0.2, 0.0, 0.5, 0.0))
assert layer.shape_count == 2
ops.wm.tool_draw(mode="FILL_ERASER")
wm.set_draw(erase_selected=True, fill_size=0.3)
assert stroke(line(-0.35, 0.0, 0.7, 0.0)) == {"CANCELLED"}, "nothing selected"
left = [i for i in range(2) if covers(layer, i, -0.4, 0.0)][0]
right_points = {layer.point_ids[i]: p for i, p in enumerate(layer.points) if p[0] > 0.0}
layer.select_points([p for p in range(layer.point_count) if layer.points[p][0] < 0.0], True)
assert stroke(line(-0.35, 0.0, 0.7, 0.0)) == {"FINISHED"}
assert layer.shape_count == 2 and not covers(layer, left, -0.3, 0.0), "the left one cut"
now = {layer.point_ids[i]: p[:2] for i, p in enumerate(layer.points)}
assert covers(layer, 1 - left, 0.3, 0.0) and all(now.get(i) == p[:2] for i, p in right_points.items()),     "the right one as it was"
wm.set_draw(erase_selected=False)

# All Layers: the same place on other drawings, through their own transforms.
below = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.2)
stroke(line(-0.5, 0.0, 0.5, 0.0))
above = fresh()
stroke(line(-0.5, 0.0, 0.5, 0.0))
below.selected = True
above.selected = True
oanim.data.layers.active = above
ops.wm.tool_draw(mode="FILL_ERASER")
wm.set_draw(fill_size=0.1)
stroke(through(0.0))
assert not covers(above, 0, 0.0, 0.0) and covers(below, 0, 0.0, 0.0), "the active one only, at first"
wm.set_draw(erase_all_layers=True)
stroke(through(0.2))
assert not covers(below, 0, 0.2, 0.0) and not covers(above, 0, 0.2, 0.0)
assert covers(below, 0, 0.0, 0.0), "below cut only where the second went"
wm.set_draw(erase_all_layers=False)
below.selected = False

# A shape with keys is cut too: the points it keeps keep their keys.
layer = fresh()
ops.wm.tool_draw(mode="FILL_PEN")
wm.set_draw(fill_size=0.2)
stroke(line(-0.5, 0.0, 0.5, 0.0))
doc.frame_current = 10
ops.sculpt.stroke(brush="GRAB", path="-0.5,0.0;-0.5,0.1", radius=0.3, strength=1.0, falloff="CONSTANT")
moved = {layer.point_ids[i]: p for i, p in enumerate(layer.points) if p[0] < -0.4}
doc.frame_current = 0
ops.wm.tool_draw(mode="FILL_ERASER")
assert stroke(through(0.3)) == {"FINISHED"}
assert layer.shape_count == 1 and not covers(layer, 0, 0.3, 0.0)
doc.frame_current = 10
now = {layer.point_ids[i]: p for i, p in enumerate(layer.points)}
assert moved and all(i in now and abs(now[i][1] - moved[i][1]) < 1e-4 for i in moved), "kept with their keys"
doc.frame_current = 0
# And painting from it grows it.
ops.wm.tool_draw(mode="FILL_PEN")
stroke(line(0.0, 0.0, 0.0, 0.4))
assert layer.shape_count == 1, layer.shape_count

print("fill paint: ok")
