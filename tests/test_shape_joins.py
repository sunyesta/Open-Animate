"""A shape is a set of connected points. The active point (the last clicked, drawn white) decides the look of a join:
Merge or F between two shapes' points makes them one shape in the look of the shape the active point is on (with none,
the fill of the lowest with a fill and the line of the lowest with a line), their sub shapes going under it. A delete
that breaks a shape apart keeps its biggest part, the others becoming copies named .001 on; a hole stays with its shape.
Older files' shapes sharing points are merged on open. A Stroke Pen line welded to another stays its own shape.

Run with:  OpenAnimate --background --python tests/test_shape_joins.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, L, wm = oanim.ops, oanim.data.layers, oanim.wm
RED, BLUE, GREEN = (1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0), (0.0, 1.0, 0.0, 1.0)


def scene():
    ops.wm.read_homefile(confirmed="1")
    return L.active


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def point_at(layer, pos, eps=1e-3):
    found = [i for i, p in enumerate(layer.points) if close(p[:2], pos, eps)]
    return found[0] if found else -1


def picked_points(layer):
    return sorted(i for i, p in enumerate(layer.points) if p[2])


def shape_on(layer, point):
    """The shape whose outline runs through point index `point`."""
    return next(i for i in range(layer.shape_count)
                if any(point in layer.curve_points(c) for run in layer.shape_runs(i) for c, _ in run))


def shape_lists(node):
    if isinstance(node, dict):
        if isinstance(node.get("shapes"), list) and node["shapes"] and isinstance(node["shapes"][0], dict):
            yield node["shapes"]
        for v in node.values():
            yield from shape_lists(v)
    elif isinstance(node, list):
        for v in node:
            yield from shape_lists(v)


# --- The active point: the last clicked, drawn white ------------------------------------------------------------------
layer = scene()
layer.add_curve([(0.1, 0.1), (0.5, 0.1), (1.0, 0.1)])
layer.add_curve([(0.1, 1.0), (0.5, 1.0), (1.0, 1.0)])
ops.mesh.select_none()
a, b = point_at(layer, (0.1, 0.1)), point_at(layer, (1.0, 1.0))
wm.select_click(0.1, 0.1, 1000.0)
assert layer.active_point == a, layer.active_point
wm.select_click(1.0, 1.0, 1000.0, shift=True)
assert layer.active_point == b and picked_points(layer) == sorted([a, b]), (layer.active_point, picked_points(layer))
assert layer.active_shape == shape_on(layer, b), "the active shape is the one the active point is on"
marks = wm.overlay_colors(layer)["points"]
white = [m for m in marks if m["color"].upper() == "#FFFFFF"]
assert len(white) == 1 and close(white[0]["at"], (1.0, 1.0)), white
# A box select keeps it while it stays selected; deselected, there is none.
ops.mesh.select_all()
assert layer.active_point == b
wm.select_click(1.0, 1.0, 1000.0, shift=True)
assert layer.active_point == -1 and b not in picked_points(layer)
assert not [m for m in wm.overlay_colors(layer)["points"] if m["color"].upper() == "#FFFFFF"]
# Saved with the drawing.
wm.select_click(0.5, 1.0, 1000.0)
middle = point_at(layer, (0.5, 1.0))
assert layer.active_point == middle
path = os.path.join(tempfile.mkdtemp(), "active.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
assert L.active.active_point == point_at(L.active, (0.5, 1.0)), L.active.active_point

# --- Merge takes the look of the active point's shape ---------------------------------------------------------------
for active_on_second in (True, False):
    layer = scene()
    layer.add_curve([(0.0, 0.0), (1.0, 0.0)])
    layer.add_curve([(1.0, 0.5), (2.0, 0.5)])
    layer.set_shape_style(0, line=RED, line_width=0.01)
    layer.set_shape_style(1, line=BLUE, line_width=0.02)
    ops.mesh.select_none()
    first, second = (1.0, 0.0), (1.0, 0.5)
    if active_on_second:
        wm.select_click(*first, 1000.0)
        wm.select_click(*second, 1000.0, shift=True)
    else:
        wm.select_click(*second, 1000.0)
        wm.select_click(*first, 1000.0, shift=True)
    assert ops.mesh.merge() == {'FINISHED'}
    assert layer.shape_count == 1, layer.shape_count
    style = layer.shape_style(0)
    want, width = (BLUE, 0.02) if active_on_second else (RED, 0.01)
    assert close(style["line"], want) and abs(style["line_width"] - width) < 1e-6, (active_on_second, style)
    assert layer.active_point >= 0, "the point they became is the active one"
    assert layer.active_shape == 0
    ops.ed.undo()
    assert layer.shape_count == 2, "one undo step"

# F between two shapes' points, likewise.
layer = scene()
layer.add_curve([(0.0, 0.0), (1.0, 0.0)])
layer.add_curve([(0.0, 1.0), (1.0, 1.0)])
layer.set_shape_style(0, line=RED)
layer.set_shape_style(1, line=BLUE)
ops.mesh.select_none()
wm.select_click(1.0, 1.0, 1000.0)
wm.select_click(1.0, 0.0, 1000.0, shift=True)
assert wm.event_simulate("F", area="Viewport")
assert layer.shape_count == 1 and close(layer.shape_style(0)["line"], RED), layer.shape_style(0)

# --- No active point: the lowest's fill and the lowest's line ---------------------------------------------------------
layer = scene()
layer.add_curve([(0.0, 0.0), (1.0, 0.0)])
layer.set_shape_style(0, line=RED, has_fill=False)
layer.add_curve([(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)], closed=True, fill=True)
layer.set_shape_style(1, line=BLUE, fill=GREEN)
ops.mesh.select_none()
layer.active_point = -1
layer.select_points([1, 2])
assert ops.mesh.merge() == {'FINISHED'}
assert layer.shape_count == 1
style = layer.shape_style(0)
assert style["has_fill"] and close(style["fill"], GREEN) and close(style["line"], RED), style
assert layer.shape_contains(0, (1.5, 0.5)), "the box still fills, the line running on from it"

# --- The sub shapes of a shape joined into another go under it ------------------------------------------------------
layer = scene()
assert layer.add_primitive("BOX", [(0.0, 0.0), (1.0, 1.0)], fill=True)
assert layer.add_primitive("CIRCLE", [(0.3, 0.3), (0.7, 0.7)], fill=True)
box = [i for i in range(2) if layer.shape_contains(i, (0.9, 0.9))][0]
assert ops.mesh.shape_parent_set(shape=str(layer.shape_ids[1 - box]), parent=str(layer.shape_ids[box])) == {'FINISHED'}
assert layer.add_primitive("BOX", [(1.0, 1.0), (2.0, 2.0)], fill=True)
other = [i for i in range(3) if layer.shape_contains(i, (1.5, 1.5))][0]
layer.set_shape_style(other, fill=BLUE)
corner = [i for i, p in enumerate(layer.points) if close(p[:2], (1.0, 1.0))]
assert len(corner) == 2
ops.mesh.select_none()
layer.select_points(corner)
layer.active_point = max(corner)
assert ops.mesh.merge() == {'FINISHED'}
assert layer.shape_count == 2, layer.shape_count
sub = [i for i in range(2) if layer.shape_style(i)["parent"] >= 0]
assert len(sub) == 1, [layer.shape_style(i)["parent"] for i in range(2)]
owner = layer.shape_style(sub[0])["parent"]
assert close(layer.shape_style(owner)["fill"], BLUE), "the active point's shape's look"
assert layer.shape_contains(owner, (0.9, 0.9)) and layer.shape_contains(owner, (1.5, 1.5))

# --- A Stroke Pen line welded to another stays its own shape, through later joins elsewhere ---------------------------
layer = scene()
pixel = 2.0 / oanim.data.document.height
layer.add_curve([(0.0, 0.0), (0.5, 0.0)])
layer.add_curve([(0.0, 0.5), (0.5, 0.5)])
layer.add_curve([(0.5, 0.6), (1.0, 0.6)])
ops.wm.tool_draw(mode="FREEHAND")
wm.set_draw(weld=True)
rows = ";".join("%f,%f,1.0,%f" % (0.5 - 0.5 * (1 - i / 39.0), -0.4 * (1 - i / 39.0), i / 78.0) for i in range(40))
assert ops.draw.stroke(samples=rows, pixel=pixel) == {'FINISHED'}
wm.set_draw(weld=False)
assert layer.shape_count == 4, layer.shape_count
welded = point_at(layer, (0.5, 0.0))
assert sum(welded in layer.curve_points(c) for c in range(layer.curve_count)) == 2, "welded: one point on both"
ops.mesh.select_none()
layer.select_points([point_at(layer, (0.5, 0.5)), point_at(layer, (0.5, 0.6))])
assert ops.mesh.merge() == {'FINISHED'}
assert layer.shape_count == 3, ("the two merged, the welded line still its own", layer.shape_count)

# --- A delete that breaks a shape apart: its biggest part keeps it, the other is a copy -------------------------------
layer = scene()
layer.add_curve([(float(x), 0.0) for x in range(6)])
layer.set_shape_style(0, line=RED, line_width=0.03)
name, sid = layer.shapes[0][0], layer.shape_ids[0]
ops.mesh.select_none()
layer.select_points([1, 2])
assert ops.mesh.delete_edges() == {'FINISHED'}
assert layer.shape_count == 2, layer.shape_count
names = [s[0] for s in layer.shapes]
kept = names.index(name)
assert layer.shape_ids[kept] == sid, "the biggest part keeps the shape"
assert names[1 - kept] == name + ".001", names
copy = layer.shape_style(1 - kept)
assert close(copy["line"], RED) and abs(copy["line_width"] - 0.03) < 1e-6, "the copy has its look"
assert all(p[0] <= 1.0 + 1e-6 for p in layer.shape_outline(1 - kept)[0]), "the copy is the short part"
assert kept < 1 - kept, "just above it"

# A hole stays with the shape round it.
layer = scene()
assert layer.add_primitive("BOX", [(0.0, 0.0), (1.0, 1.0)], fill=True)
assert layer.add_primitive("BOX", [(0.3, 0.3), (0.7, 0.7)], fill=True)
ops.mesh.select_all()
assert ops.mesh.join_fills() == {'FINISHED'}
assert layer.shape_count == 1 and not layer.shape_contains(0, (0.5, 0.5))
ops.mesh.select_none()
layer.select_points([point_at(layer, (0.0, 0.0))])
assert ops.mesh.delete_points() == {'FINISHED'}
assert layer.shape_count == 1, ("the hole not split off", layer.shape_count)
assert not layer.shape_contains(0, (0.5, 0.5)) and layer.shape_contains(0, (0.8, 0.8))

# --- Older files: shapes sharing points become one on open -----------------------------------------------------------
for version, merged in ((12, True), (13, False)):
    layer = scene()
    layer.add_curve([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], closed=True, fill=True)
    path = os.path.join(tempfile.mkdtemp(), "old.oanim")
    assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
    with zipfile.ZipFile(path) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    doc_json = json.loads(entries["document.json"])
    doc_json["version"] = version
    shapes = next(shape_lists(doc_json))
    # Moho's way: the fill and its outline as two shapes on the one curve.
    line = json.loads(json.dumps(shapes[0]))
    line.pop("id", None)
    line["fill"] = False
    shapes[0]["outline"] = False
    shapes.append(line)
    entries["document.json"] = json.dumps(doc_json).encode()
    with zipfile.ZipFile(path, "w") as z:
        for n, data in entries.items():
            z.writestr(n, data)
    assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    layer = L.active
    if merged:
        assert layer.shape_count == 1, layer.shape_count
        assert layer.shape_style(0)["has_fill"] and layer.shape_style(0)["has_outline"], layer.shape_style(0)
    else:
        assert layer.shape_count == 2, "a file of this format is read as it is"

print("test_shape_joins: OK")
