"""Properties' Selected Points: the picked points' Median (Point with one) where they show, bent by the bones, and
Rotation and Scale about it, each dragged field shown from the drawings as the drag began and let go as one undo step
(mesh.transform_selected); Width (scaled) and Opacity (moved) means over every drawing being edited, mesh.points_mean_set;
the position and width key buttons (mesh.points_keyframe: yellow only when every picked point is keyed here); the same
panel in a bone layer's Drawing tab; and the one picked point's Point Weights (weight.point_set).

Run with:  OpenAnimate --background --python tests/test_points_panel.py
"""

import math
import os
import tempfile

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def fresh(layer):
    return next(l for l in layers.all() if l.id == layer.id)


def drawing(points=((0.0, 0.0), (1.0, 0.0), (2.0, 1.0), (3.0, 0.0))):
    ops.wm.read_homefile()
    assert ops.layer.new() == {'FINISHED'}
    layer = layers.active
    layer.add_curve(list(points))
    # Saved and opened again, so the curve (a Python edit, no undo step of its own) is what undo goes back to.
    path = os.path.join(tempfile.gettempdir(), "oa_points_panel_%d.oanim" % os.getpid())
    ops.wm.save_copy(filepath=path)
    assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    os.remove(path)
    return layers.active


def where(layer, picked):
    pts = layer.shown()[0]
    return [pts[i] for i in picked]


def mean(ps):
    return (sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))


# --- Median: the picked points' middle; dragging X moves them all from where the drag began, one undo step ----------
layer = drawing()
layer.select_points([0, 1, 2])
panel = wm.points_panel()
assert panel and panel["label"] == "Median" and panel["count"] == 3, panel
assert close(panel["median"], (1.0, 1.0 / 3.0)), panel
was = where(layer, [0, 1, 2])
steps_seen = []
assert wm.points_panel_drag("x", [1.1, 1.3, 1.6, 2.0], during=lambda: steps_seen.append(wm.points_panel()["median"]))
assert [round(m[0], 4) for m in steps_seen] == [1.1, 1.3, 1.6], steps_seen
assert all(close(a, (b[0] + 1.0, b[1])) for a, b in zip(where(layer, [0, 1, 2]), was)), where(layer, [0, 1, 2])
assert close(where(layer, [3])[0], (3.0, 0.0)), "a point not picked stays"
assert ops.ed.undo() == {'FINISHED'}
layer = fresh(layer)
assert all(close(a, b) for a, b in zip(where(layer, [0, 1, 2]), was)), "one undo step takes the whole drag back"

# --- One point: Point --------------------------------------------------------------------------------------------------
layer.select_points(range(4), select=False)
layer.select_points([3])
assert wm.points_panel()["label"] == "Point" and close(wm.points_panel()["median"], (3.0, 0.0))

# --- Rotation and Scale about the median: the same angle held over updates turns them as far once ---------------------
layer = drawing(((0.0, 0.0), (2.0, 0.0), (5.0, 5.0)))
layer.select_points([0, 1])
assert wm.points_panel_drag("rotation", [30.0, 60.0, 90.0, 90.0, 90.0])
assert close(where(layer, [0])[0], (1.0, -1.0)) and close(where(layer, [1])[0], (1.0, 1.0)), where(layer, [0, 1])
assert wm.points_panel_drag("scale_y", [2.0, 3.0, 3.0])
assert close(where(layer, [0])[0], (1.0, -3.0)) and close(where(layer, [1])[0], (1.0, 3.0)), where(layer, [0, 1])
assert close(where(layer, [2])[0], (5.0, 5.0))

# --- Width scales, Opacity moves, over every drawing being edited --------------------------------------------------------
layer = drawing(((0.0, 0.0), (1.0, 0.0), (2.0, 0.0)))
layer.select_points([0])
layer.mean_radius = 1.0
layer.select_points([0], select=False)
layer.select_points([1])
layer.mean_radius = 2.0
layer.select_points([0, 1])
assert ops.mesh.points_mean_set(what="WIDTH", value="3") == {'FINISHED'}
assert close(fresh(layer).radii[:3], (2.0, 4.0, 1.0)), fresh(layer).radii
assert abs(wm.points_panel()["width"] - 3.0) < 1e-5
assert ops.mesh.points_mean_set(what="OPACITY", value="0.5") == {'FINISHED'}
assert close(fresh(layer).opacities[:3], (0.5, 0.5, 1.0)), fresh(layer).opacities
assert ops.mesh.points_mean_set(what="OPACITY", value="0.5") == {'CANCELLED'}, "nothing to change"

# --- Keys: yellow only when every picked point is keyed here ------------------------------------------------------------
layer = drawing()
layer.key_whole_drawing = False  # keyed point by point here
layer.key_together = False
doc.auto_key = False
doc.frame_current = 10
layer.select_points([0, 1])
assert wm.points_panel()["key"] == 0
assert ops.mesh.points_keyframe(what="POSITION") == {'FINISHED'}
assert wm.points_panel()["key"] == 2
assert wm.points_panel()["width_key"] == 0, ("the widths aren't keyed by a position key", layer.keyed_at(10))
layer.select_points([2])
assert wm.points_panel()["key"] == 1, "one picked point not keyed here: animated, not keyed"
layer.select_points([2], select=False)
assert ops.mesh.points_keyframe(what="POSITION", mode="DELETE") == {'FINISHED'}
assert wm.points_panel()["key"] == 0, wm.points_panel()
assert ops.mesh.points_keyframe(what="WIDTH") == {'FINISHED'}
assert wm.points_panel()["width_key"] == 2 and wm.points_panel()["key"] == 0

# --- In a bone layer's Drawing tab: where the points show, bent by the posed bone, and the one point's weights ----------
ops.wm.read_homefile()
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
assert ops.armature.bone_add(name="Arm", head_x="0", head_y="0", tail_x="2", tail_y="0", parent="") == {'FINISHED'}
assert ops.armature.bone_add(name="Hand", head_x="2", head_y="0", tail_x="3", tail_y="0", parent="") == {'FINISHED'}
ops.layer.new()
arm = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
arm = fresh(arm)
arm.add_curve([(0.5, 0.2), (1.5, 0.2), (2.5, 0.2)])
arm.edit_with_bones = True
layers.active = arm
assert ops.weight.automatic() == {'FINISHED'}
doc.auto_key = True
doc.frame_current = 5
layers.active = rig
rig.bone_set("Arm", angle=math.radians(90.0))
ops.armature.select_none()
arm = fresh(arm)
arm.selected = True
arm.select_points([0, 1])
layers.active = rig
panel = wm.points_panel()
shown = where(arm, [0, 1])
assert panel and close(panel["median"], mean(shown)), (panel, shown)
assert not close(mean(shown), (1.0, 0.2)), "bent by the bone"
assert panel["weights"] is None, "two points picked: no weights"
assert wm.points_panel_drag("x", [panel["median"][0] + 0.1, panel["median"][0] + 0.3])
assert close(mean(where(fresh(arm), [0, 1])), (shown[0][0] / 2 + shown[1][0] / 2 + 0.3, mean(shown)[1]), 1e-3), \
    (where(fresh(arm), [0, 1]), shown)

arm = fresh(arm)
arm.select_points([0, 1], select=False)
arm.select_points([2])
weights = dict(wm.points_panel()["weights"])
assert set(weights) <= {"Arm", "Hand"} and weights, weights
ids = {b["name"]: str(b["id"]) for b in fresh(rig).bones}
assert ops.weight.point_set(layer=str(arm.id), point="2", bone=ids["Hand"], weight="0.25") == {'FINISHED'}
assert dict(wm.points_panel()["weights"])["Hand"] == 0.25, wm.points_panel()["weights"]
assert dict(fresh(arm).weights[2])["Hand"] == 0.25
assert ops.weight.point_set(layer=str(arm.id), point="2", bone=ids["Arm"], remove="1") in ({'FINISHED'}, {'CANCELLED'})
assert "Arm" not in dict(wm.points_panel()["weights"]), wm.points_panel()["weights"]
assert ops.weight.point_set(layer=str(arm.id), point="2", bone=ids["Arm"], weight="0.6") == {'FINISHED'}
assert dict(wm.points_panel()["weights"]) == {"Hand": 0.25, "Arm": 0.6} or     {k: round(v, 5) for k, v in dict(wm.points_panel()["weights"]).items()} == {"Hand": 0.25, "Arm": 0.6}
assert ops.weight.point_set(layer=str(arm.id), point="9", bone=ids["Arm"], weight="0.6") == {'CANCELLED'}
assert ops.weight.point_set(layer=str(arm.id), point="2", bone=ids["Arm"], weight="2") == {'CANCELLED'}

# --- Nothing moved, turned or scaled: CANCELLED, no undo step (a drag let go back at rest too) --------------------------
layer = drawing()
layer.select_points([0, 1])
for args in ({}, {"move_x": "0"}, {"angle": "0", "scale_x": "1"}, {"move_x": "nan"}):
    step = wm.undo_history()[1]
    assert ops.mesh.transform_selected(**args) == {'CANCELLED'}, args
    assert wm.undo_history()[1] == step, args
m = wm.points_panel()["median"]
step = wm.undo_history()[1]
before = fresh(layer).points
wm.points_panel_drag("x", [m[0] + 0.5, m[0]])
assert wm.undo_history()[1] == step, "dragged away and back"
assert fresh(layer).points == before

# --- Far from the origin: turned about the median exactly where it is ---------------------------------------------------
layer = drawing(((1234.5678, 0.0), (1236.5678, 0.0), (5.0, 5.0)))
layer.select_points([0, 1])
m = wm.points_panel()["median"]
wm.points_panel_drag("rotation", [90.0, 180.0])
assert abs(wm.points_panel()["median"][0] - m[0]) < 1e-3, (m, wm.points_panel()["median"])

# --- Bent by a deform on a posed frame: the Median moved by d moves the point by d where it shows -----------------------
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
assert ops.layer.new() == {'FINISHED'}
cage = layers.active
cage.name = "Cage"
assert cage.add_primitive("BOX", [(-1, -1), (1, 1)])
# The deform on a group round the drawing (a group's deforms bend every drawing inside).
assert ops.layer.new_group() == {'FINISHED'}
group = layers.active
assert ops.object.modifier_add(type="MESH_DEFORM") == {'FINISHED'}
group.modifier_set(0, curve_method="SMOOTH", cage_method="MEAN_VALUE")
group.modifier_set(0, layer=cage.name, shape=cage.shapes[0][0])
assert ops.layer.new() == {'FINISHED'}
art = layers.active
art.name = "Art"
assert ops.layer.move_to_group(group=str(group.id)) == {'FINISHED'}
art = fresh(art)
art.add_curve([(-0.55, -0.3), (-0.2, 0.35), (0.25, -0.15), (0.6, 0.3)])
doc.frame_current = 10
for i, p in enumerate(fresh(cage).points):
    # One corner pulled far out: bent hard, so a point's skin holds only round where it was.
    fresh(cage).set_point(i, (p[0] * 2.5, p[1] * 2.5) if p[0] > 0 and p[1] > 0 else (p[0], p[1]))
doc.frame_current = 11
doc.frame_current = 10
layers.active = fresh(art)
fresh(art).select_points([1])
was = where(fresh(art), [1])[0]
m = wm.points_panel()["median"]
assert close(m, was), (m, was)
assert wm.points_panel_drag("x", [m[0] + 0.3])
now = where(fresh(art), [1])[0]
assert close(now, (was[0] + 0.3, was[1]), 1e-3), ("moved 0.3 where it shows", was, now)

# --- Every bone taken off a point: it has none (not its neighbours' again) ---------------------------------------------
ops.wm.read_homefile()
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
assert ops.armature.bone_add(name="Arm", head_x="0", head_y="0", tail_x="2", tail_y="0", parent="") == {'FINISHED'}
assert ops.armature.bone_add(name="Hand", head_x="2", head_y="0", tail_x="3", tail_y="0", parent="") == {'FINISHED'}
ops.layer.new()
arm = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
arm = fresh(arm)
arm.add_curve([(0.5, 0.2), (1.5, 0.2), (2.9, 0.2)])
arm.edit_with_bones = True
layers.active = arm
assert ops.weight.automatic() == {'FINISHED'}
ids = {b["name"]: str(b["id"]) for b in fresh(rig).bones}
arm.select_points([0])
for name in list(fresh(arm).weights[0]):
    assert ops.weight.point_set(layer=str(arm.id), point="0", bone=ids[name], remove="1") == {'FINISHED'}
assert not fresh(arm).weights[0], fresh(arm).weights[0]

# --- Keyed twice on a frame: nothing to put in the second time ---------------------------------------------------------
layer = drawing()
layer.key_whole_drawing = False
layer.key_together = False
doc.auto_key = False
doc.frame_current = 10
layer.select_points([0, 1])
assert ops.mesh.points_keyframe(what="POSITION") == {'FINISHED'}
step = wm.undo_history()[1]
assert ops.mesh.points_keyframe(what="POSITION") == {'CANCELLED'}
assert wm.undo_history()[1] == step
layer.select_points([2])
assert ops.mesh.points_keyframe(what="POSITION") == {'FINISHED'}, "one picked point not keyed here yet"

# --- A reference without Edit Points: its widths and opacity follow its original, nothing to set -----------------------
layer = drawing()
assert ops.layer.make_reference() == {'FINISHED'}
ref = layers.active
assert ref.reference["edit_points"] is False
ref.select_points([0, 1])
for what, value in (("WIDTH", "3"), ("OPACITY", "0.3")):
    step = wm.undo_history()[1]
    assert ops.mesh.points_mean_set(what=what, value=value) == {'CANCELLED'}, what
    assert wm.undo_history()[1] == step, what

print("test_points_panel: OK")
