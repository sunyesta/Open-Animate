"""The shape tree: a closed shape put under another (mesh.shape_parent_set) is its sub shape, its Operation (Union,
Subtract, Intersect, Exclude) acting on it, its Smoothing (keyable) rounding where their outlines cross. The result
keeps the drawing's curves: the parent's points it still runs through, with their handles; new places only where the
outlines cross. Sub shapes draw nothing of their own; an eye closed stops a shape drawing (and a sub shape acting).

Run with:  OpenAnimate --background --python tests/test_shape_tree.py
"""

import os
import tempfile

import oanim

ops, L = oanim.ops, oanim.data.layers


def scene():
    """A filled square (shape 0, curve 0) and over its right edge a filled circle round (1.05, 0.5), radius 0.4
    (shape 1, curve 1)."""
    ops.wm.read_homefile(confirmed="1")
    layer = L.active
    assert layer.add_primitive("BOX", [(0.0, 0.0), (1.0, 1.0)], fill=True)
    assert layer.add_primitive("CIRCLE", [(0.65, 0.1), (1.45, 0.9)], fill=True)
    assert layer.shape_count == 2, layer.shape_count
    # The Shape tool's new shape went in at the bottom: the square back to the bottom, as drawn first.
    if layer.shape_runs(0)[0][0][0] != 0:
        circle_id = layer.shape_ids[0]
        ops.mesh.shape_parent_set(shape=str(circle_id), parent=str(layer.shape_ids[1]))
        ops.mesh.shape_parent_set(shape=str(circle_id))
    assert layer.shape_runs(0)[0][0][0] == 0 and layer.shape_runs(1)[0][0][0] == 1, layer.shape_runs(0)
    # An undo step of their own (a script's edits join the next operator's).
    ops.mesh.select_none()
    return layer


def ids(layer):
    return layer.shape_ids


def under(layer, child, parent):
    return ops.mesh.shape_parent_set(shape=str(ids(layer)[child]), parent=str(ids(layer)[parent]))


def fills(layer, shape, point):
    return layer.evaluated_shape(shape, point)["contains"]


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


# --- Putting a shape under another: Union until changed ------------------------------------------------------------
layer = scene()
square, circle = ids(layer)
assert under(layer, 1, 0) == {'FINISHED'}
style = layer.shape_style(1)
assert style["parent"] == 0 and style["op"] == "UNION", style
assert fills(layer, 0, (1.3, 0.5)), "the circle's part outside the square is the square's now"
assert fills(layer, 0, (0.3, 0.5))
assert layer.evaluated_shape(1)["merged"], "the sub shape draws nothing of its own"
# Undone, the circle is a shape of its own again, the square only itself.
ops.ed.undo()
assert layer.shape_style(1)["parent"] == -1
assert not fills(layer, 0, (1.3, 0.5))

# --- The result keeps the drawing's curves -------------------------------------------------------------------------
layer = scene()
under(layer, 1, 0)
tree = layer.shape_tree(0)
assert not tree["empty"] and len(tree["loops"]) == 1, tree
nodes = tree["loops"][0]["nodes"]
kept = sorted(n["point"] for n in nodes if n["shape"] == 0 and n["point"] >= 0)
assert kept == [0, 1, 2, 3], ("the square's four corners stay, as the same points", kept, nodes)
crossings = [n["pos"] for n in nodes if n["point"] < 0]
assert len(crossings) == 2, ("new places only where the outlines cross", crossings)
# The circle meets x = 1 at y = 0.5 -+ 0.3969 (a four point circle is round to a few ten thousandths).
assert any(close(c, (1.0, 0.1031), 1e-3) for c in crossings) and any(close(c, (1.0, 0.8969), 1e-3) for c in crossings), crossings
# The circle's point on its far side, with the handles it has.
far = [n for n in nodes if n["shape"] == 1 and n["point"] >= 0 and close(n["pos"], (1.45, 0.5), 1e-3)]
assert len(far) == 1, nodes
# Its handles as drawn (the circle is curve 1, its points in order).
circle_points = layer.curve_points(1)
drawn = layer.curve_handles(1)[circle_points.index(far[0]["point"])]
assert close((far[0]["pos"][0] + far[0]["out"][0], far[0]["pos"][1] + far[0]["out"][1]), drawn[2]), (far[0], drawn)

# --- Each operation ---------------------------------------------------------------------------------------------------
for op, inside, middle, outside in (("UNION", True, True, True), ("SUBTRACT", True, False, False),
                                    ("INTERSECT", False, True, False), ("EXCLUDE", True, False, True)):
    layer = scene()
    under(layer, 1, 0)
    if op != "UNION":
        assert ops.mesh.shape_op_set(shape=str(ids(layer)[1]), op=op) == {'FINISHED'}
    assert layer.shape_style(1)["op"] == op
    got = (fills(layer, 0, (0.3, 0.5)), fills(layer, 0, (0.9, 0.5)), fills(layer, 0, (1.3, 0.5)))
    assert got == (inside, middle, outside), (op, got)
# The same operation again changes nothing.
assert ops.mesh.shape_op_set(shape=str(ids(layer)[1]), op="EXCLUDE") == {'CANCELLED'}
assert ops.mesh.shape_op_set(shape=str(ids(layer)[1]), op="SIDEWAYS") == {'CANCELLED'}

# --- Subtract cuts a hole through the middle: the result has two loops ---------------------------------------------
layer = scene()
assert layer.add_primitive("CIRCLE", [(0.4, 0.4), (0.6, 0.6)], fill=True)
def on_curve(layer, curve):
    return next(i for i in range(layer.shape_count) if layer.shape_runs(i)[0][0][0] == curve)


ops.mesh.shape_parent_set(shape=str(ids(layer)[on_curve(layer, 2)]), parent=str(ids(layer)[on_curve(layer, 0)]))
ops.mesh.shape_op_set(shape=str(ids(layer)[on_curve(layer, 2)]), op="SUBTRACT")
square = on_curve(layer, 0)
tree = layer.shape_tree(square)
assert sorted(l["hole"] for l in tree["loops"]) == [False, True], tree["loops"]
assert not fills(layer, square, (0.5, 0.5)) and fills(layer, square, (0.2, 0.5))

# --- Smoothing rounds where the outlines cross, growing in from nothing ----------------------------------------------
layer = scene()
under(layer, 1, 0)
notch = (1.006, 0.905)
assert not fills(layer, 0, notch)
assert ops.mesh.shape_smoothing_set(shape=str(ids(layer)[1]), value="0.05") == {'FINISHED'}
assert abs(layer.shape_style(1)["smoothing"] - 0.05) < 1e-6
assert fills(layer, 0, notch), "the corner where they cross is filled in, rounded"
assert not fills(layer, 0, (1.2, 0.98)), "only near the crossing"
# A rounding is a few cubics, not a polyline.
nodes = layer.shape_tree(0)["loops"][0]["nodes"]
assert len(nodes) < 20, len(nodes)
# Keyed: on frame 0 none, on frame 10 some; between, part way.
layer = scene()
under(layer, 1, 0)
doc = oanim.data.document
doc.auto_key = True
doc.frame_current = 10
ops.mesh.shape_smoothing_set(shape=str(ids(layer)[1]), value="0.05")
doc.frame_current = 0
assert layer.shape_style(1)["smoothing"] == 0.0, layer.shape_style(1)
assert not fills(layer, 0, notch)
doc.frame_current = 10
assert fills(layer, 0, notch)

# --- An eye closed: not drawn, and a sub shape stops acting ----------------------------------------------------------
layer = scene()
under(layer, 1, 0)
assert ops.mesh.shape_show_set(shape=str(ids(layer)[1]), show="FALSE") == {'FINISHED'}
assert not fills(layer, 0, (1.3, 0.5)), "the circle no longer adds"
assert ops.mesh.shape_show_set(shape=str(ids(layer)[1]), show="FALSE") == {'CANCELLED'}
assert ops.mesh.shape_show_set(shape=str(ids(layer)[0]), show="TOGGLE") == {'FINISHED'}
assert layer.evaluated_shape(0)["hidden"]

# --- Take Out of Parent: back in the list with its own look, in front of the tree it was in -------------------------
layer = scene()
layer.set_shape_style(1, fill=(0.1, 0.2, 0.9, 1.0))
under(layer, 1, 0)
assert ops.mesh.shape_parent_set(shape=str(ids(layer)[1])) == {'FINISHED'}
style = layer.shape_style(1)
assert style["parent"] == -1 and close(style["fill"], (0.1, 0.2, 0.9, 1.0)), style
assert not fills(layer, 0, (1.3, 0.5)) and fills(layer, 1, (1.3, 0.5))
assert ops.mesh.shape_parent_set(shape=str(ids(layer)[1])) == {'CANCELLED'}, "already out"

# --- What can't be a sub shape ----------------------------------------------------------------------------------------
layer = scene()
layer.add_curve([(2.0, 0.0), (3.0, 0.0), (3.0, 1.0)])
assert layer.shape_count == 3
assert ops.mesh.shape_parent_set(shape=str(ids(layer)[2]), parent=str(ids(layer)[0])) == {'CANCELLED'}, "an open line"
assert ops.mesh.shape_parent_set(shape=str(ids(layer)[0]), parent=str(ids(layer)[2])) == {'CANCELLED'}
assert under(layer, 0, 0) == {'CANCELLED'}, "itself"
under(layer, 1, 0)
assert under(layer, 0, 1) == {'CANCELLED'}, "under its own sub shape"

# --- Saved and opened ----------------------------------------------------------------------------------------------
layer = scene()
under(layer, 1, 0)
ops.mesh.shape_op_set(shape=str(ids(layer)[1]), op="INTERSECT")
ops.mesh.shape_smoothing_set(shape=str(ids(layer)[1]), value="0.03")
ops.mesh.shape_show_set(shape=str(ids(layer)[0]), show="FALSE")
path = os.path.join(tempfile.mkdtemp(), "tree.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
layer = L.active
child, parent = layer.shape_style(1), layer.shape_style(0)
assert child["parent"] == 0 and child["op"] == "INTERSECT" and abs(child["smoothing"] - 0.03) < 1e-6, child
assert not parent["shown"] and child["shown"], parent

# --- Its parent gone, a sub shape goes back into the list ----------------------------------------------------------
layer = scene()
under(layer, 1, 0)
assert ops.mesh.delete_shapes(shapes=str(ids(layer)[0])) == {'FINISHED'}
assert layer.shape_count == 1 and layer.shape_style(0)["parent"] == -1


# --- The list's drops: above, below and into a row, each tree moving whole ------------------------------------------
def names(layer):
    """Each shape (bottom first) by the curve it is on: a, b, c, d for curves 0 to 3."""
    return ["abcd"[layer.shape_runs(i)[0][0][0]] for i in range(layer.shape_count)]


layer = scene()
assert layer.add_primitive("BOX", [(3.0, 0.0), (4.0, 1.0)], fill=True)
assert layer.add_primitive("BOX", [(3.5, 0.5), (4.5, 1.5)], fill=True)
idx = lambda n: names(layer).index(n)
sid = lambda n: str(ids(layer)[idx(n)])
# Into: d goes under b, its tree just above b.
if names(layer) != ["a", "b", "c", "d"]:
    for n in "abcd":
        ops.mesh.shape_move(shape=sid(n), target=sid(names(layer)[-1]), place="ABOVE")
assert names(layer) == ["a", "b", "c", "d"], names(layer)
assert ops.mesh.shape_move(shape=sid("d"), target=sid("b"), place="INTO") == {'FINISHED'}
assert names(layer) == ["a", "b", "d", "c"] and layer.shape_style(idx("d"))["parent"] == idx("b"), names(layer)
# b (with d under it) above c: the two together, d still on b.
assert ops.mesh.shape_move(shape=sid("b"), target=sid("c"), place="ABOVE") == {'FINISHED'}
assert names(layer) == ["a", "c", "b", "d"], names(layer)
assert layer.shape_style(idx("d"))["parent"] == idx("b")
# Below a: the whole tree to the bottom.
assert ops.mesh.shape_move(shape=sid("b"), target=sid("a"), place="BELOW") == {'FINISHED'}
assert names(layer) == ["b", "d", "a", "c"], names(layer)
# Beside a sub shape: c below d joins b's tree, under d (acting first), as a Union.
assert ops.mesh.shape_move(shape=sid("c"), target=sid("d"), place="BELOW") == {'FINISHED'}
assert names(layer) == ["b", "c", "d", "a"], names(layer)
assert layer.shape_style(idx("c"))["parent"] == idx("b") and layer.shape_style(idx("c"))["op"] == "UNION"
# Out again: above b at the top level.
assert ops.mesh.shape_move(shape=sid("c"), target=sid("b"), place="ABOVE") == {'FINISHED'}
assert layer.shape_style(idx("c"))["parent"] == -1 and names(layer) == ["b", "d", "c", "a"], names(layer)
# Nowhere new: cancelled. Under its own sub shape: refused.
assert ops.mesh.shape_move(shape=sid("c"), target=sid("b"), place="ABOVE") == {'CANCELLED'}
assert ops.mesh.shape_move(shape=sid("b"), target=sid("d"), place="BELOW") == {'CANCELLED'}
assert ops.mesh.shape_move(shape=sid("b"), target=sid("d"), place="INTO") == {'CANCELLED'}
assert ops.mesh.shape_move(shape=sid("b"), target=sid("a"), place="SIDEWAYS") == {'CANCELLED'}
# Undone, back as it was.
ops.ed.undo()
assert names(layer) == ["b", "c", "d", "a"], names(layer)

# --- Copies: a duplicated tree is a tree of its own; the Mirror modifier's image too -------------------------------
layer = scene()
under(layer, 1, 0)
layer.select_points(list(range(layer.point_count)))
assert ops.mesh.duplicate_move() == {'FINISHED'}
tree = [(layer.shape_runs(i)[0][0][0], layer.shape_style(i)["parent"]) for i in range(layer.shape_count)]
assert tree == [(0, -1), (1, 0), (2, -1), (3, 2)], ("the copied circle under the copied square", tree)

layer = scene()
under(layer, 1, 0)
assert ops.object.modifier_add(type="MIRROR") == {'FINISHED'}
# The square, its image, then the circle and its image (sub shapes, drawing nothing).
assert layer.evaluated_shape(0, (1.3, 0.5))["contains"] and not layer.evaluated_shape(0, (-1.3, 0.5))["contains"]
assert layer.evaluated_shape(1, (-1.3, 0.5))["contains"], "the circle's image joins the square's image"
assert layer.evaluated_shape(2)["merged"] and layer.evaluated_shape(3)["merged"]

# --- Apply: the sub shape baked into its parent, the points it still runs through kept ------------------------------
def point_at(layer, pos, eps=1e-3):
    found = [i for i, p in enumerate(layer.points) if close(p[:2], pos, eps)]
    return found[0] if found else -1


layer = scene()
under(layer, 1, 0)
corner_ids = [layer.point_ids[point_at(layer, c)] for c in ((0, 0), (1, 0), (1, 1), (0, 1))]
far_id = layer.point_ids[point_at(layer, (1.45, 0.5))]
near = point_at(layer, (0.65, 0.5))
assert near >= 0
assert ops.mesh.shape_apply(shape=str(ids(layer)[1])) == {'FINISHED'}
assert layer.shape_count == 1 and layer.shape_style(0)["parent"] == -1
assert layer.curve_count == 1, "the outline is one curve of the shape's own; the old curves went"
# The square's corners and the circle's far point are the same points; its point inside the square went; two new
# where they cross.
assert [layer.point_ids[point_at(layer, c)] for c in ((0, 0), (1, 0), (1, 1), (0, 1))] == corner_ids
assert layer.point_ids[point_at(layer, (1.45, 0.5))] == far_id
assert point_at(layer, (0.65, 0.5)) < 0 and layer.point_count == 9, layer.points
assert point_at(layer, (1.0, 0.1031)) >= 0 and point_at(layer, (1.0, 0.8969)) >= 0
assert fills(layer, 0, (0.3, 0.5)) and fills(layer, 0, (1.3, 0.5)) and not fills(layer, 0, (1.2, 0.98))
ops.ed.undo()
assert layer.shape_count == 2 and layer.shape_style(1)["parent"] == 0 and layer.point_count == 8

# A hole cut through the middle comes in as a loop of its own.
layer = scene()
assert layer.add_primitive("CIRCLE", [(0.4, 0.4), (0.6, 0.6)], fill=True)
ops.mesh.shape_parent_set(shape=str(ids(layer)[on_curve(layer, 2)]), parent=str(ids(layer)[on_curve(layer, 0)]))
ops.mesh.shape_op_set(shape=str(ids(layer)[on_curve(layer, 2)]), op="SUBTRACT")
assert ops.mesh.shape_apply(shape=str(ids(layer)[on_curve(layer, 2)])) == {'FINISHED'}
square = next(i for i in range(layer.shape_count) if fills(layer, i, (0.2, 0.5)))
assert len(layer.shape_runs(square)) == 2 and not fills(layer, square, (0.5, 0.5)), layer.shape_runs(square)

# Only the sub shapes up to the one applied: one above it stays a sub shape.
layer = scene()
assert layer.add_primitive("CIRCLE", [(0.4, 0.4), (0.6, 0.6)], fill=True)
ops.mesh.shape_parent_set(shape=str(ids(layer)[on_curve(layer, 1)]), parent=str(ids(layer)[on_curve(layer, 0)]))
ops.mesh.shape_parent_set(shape=str(ids(layer)[on_curve(layer, 2)]), parent=str(ids(layer)[on_curve(layer, 0)]))
ops.mesh.shape_op_set(shape=str(ids(layer)[on_curve(layer, 2)]), op="SUBTRACT")
assert ops.mesh.shape_apply(shape=str(ids(layer)[on_curve(layer, 1)])) == {'FINISHED'}
assert layer.shape_count == 2
hole = next(i for i in range(layer.shape_count) if layer.shape_style(i)["parent"] >= 0)
assert layer.shape_style(hole)["op"] == "SUBTRACT"
assert fills(layer, layer.shape_style(hole)["parent"], (1.3, 0.5)), "the circle is part of the square now"

# Refused: off Setup, a hidden sub shape, a shape under nothing.
layer = scene()
under(layer, 1, 0)
oanim.data.document.frame_current = 5
assert ops.mesh.shape_apply(shape=str(ids(layer)[1])) == {'CANCELLED'}
oanim.data.document.frame_current = 0
ops.mesh.shape_show_set(shape=str(ids(layer)[1]), show="FALSE")
assert ops.mesh.shape_apply(shape=str(ids(layer)[1])) == {'CANCELLED'}
assert ops.mesh.shape_apply(shape=str(ids(layer)[0])) == {'CANCELLED'}
assert layer.shape_count == 2

print("test_shape_tree: OK")
