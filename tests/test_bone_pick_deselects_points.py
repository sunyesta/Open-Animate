"""Picking a bone lets go of the points picked before: a point of a drawing inside the bone layer (edited along with
its bones) stayed picked beside a 2 Axis Controller's knob pressed with the Select tool, and beside a bone clicked
with the Transform tool, so a G after moved both. Shift still adds.

Run with:  OpenAnimate --background --python tests/test_bone_pick_deselects_points.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.layer.new_bone()
rig = layers.active
ops.armature.bone_add(name="knob", head_x="3.0", head_y="3.0", tail_x="3.0", tail_y="3.5")
ops.armature.bone_add(name="arm", head_x="-3.0", head_y="0.0", tail_x="-1.0", tail_y="0.0")
ops.layer.new()
face = layers.active
face.name = "Face"
face.add_curve([(0.0, -2.0), (1.0, -2.0), (0.5, -1.0)], closed=True)
ops.layer.move_to_group(group=str(rig.id))
face = next(l for l in layers.all() if l.name == "Face")
face.edit_with_bones = True  # its points edited along with the bones, as in the practice file
layers.active = rig
rig.select_bone("knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
zoom = 100.0


def picked_points():
    return [i for i, p in enumerate(face.points) if p[2]]


def picked_bones():
    return sorted(b["name"] for b in rig.bones if b["selected"])


def start():
    layers.active = rig
    rig.select_bone("arm")
    face.select_points([0, 1, 2], False)
    face.select_points([1])
    assert picked_points() == [1]


# --- A knob pressed with the Select tool ---------------------------------------------------------------------------------
start()
assert wm.bone_press(3.0, 3.0, zoom), "the press is on the knob"
assert picked_bones() == ["knob"], picked_bones()
assert picked_points() == [], ("the point lets go when the knob is picked", picked_points())

# --- A bone clicked with the Transform tool ------------------------------------------------------------------------------
start()
rig.select_bone("knob")
wm.bone_press(-2.0, 0.0, zoom, transform_tool=True)
assert picked_bones() == ["arm"], picked_bones()
assert picked_points() == [], ("the point lets go when a bone is clicked", picked_points())

# --- Shift adds: the point stays ---------------------------------------------------------------------------------------
start()
rig.select_bone("knob")
wm.bone_press(-2.0, 0.0, zoom, transform_tool=True, shift=True)
assert picked_bones() == ["arm", "knob"], picked_bones()
assert picked_points() == [1], ("Shift keeps the point", picked_points())

print("bone pick deselects points: ok")

# --- A bone of the bone layer around the sub bone group worked in: that layer's points let go too ---------------------
# Clicked without Shift (Transform tool, Motion Path tool), the outer bone layer becomes the one worked in; a point of
# a drawing edited with its bones, picked before, stayed picked beside the bone (only the sub group's were let go).
ops.wm.read_homefile()
ops.layer.new_bone()
layers.active.name = "Rig"
ops.armature.bone_add(name="arm", head_x="-3.0", head_y="0.0", tail_x="-1.0", tail_y="0.0")
ops.layer.new()
layers.active.name = "Face"
layers.active.add_curve([(0.0, -2.0), (1.0, -2.0), (0.5, -1.0)], closed=True)
ops.layer.move_to_group(group=str(next(l for l in layers.all() if l.name == "Rig").id))
ops.layer.new_bone()
layers.active.name = "Sub"
ops.armature.bone_add(name="jaw", head_x="3.0", head_y="3.0", tail_x="5.0", tail_y="3.0")
ops.layer.move_to_group(group=str(next(l for l in layers.all() if l.name == "Rig").id))
get = lambda n: next(l for l in layers.all() if l.name == n)
face, sub, rig = get("Face"), get("Sub"), get("Rig")
face.edit_with_bones = True
for how in ("transform", "motion_path"):
    layers.active = rig
    ops.armature.select_none()
    face.select_points([0, 1, 2], False)
    face.select_points([1])  # picked while working in Rig
    layers.active = sub  # then the sub bone group is worked in
    if how == "transform":
        wm.bone_press(-2.0, 0.0, zoom, transform_tool=True)
    else:
        assert wm.motion_path_pick(-2.0, 0.0, zoom)
    assert layers.active.name == "Rig", (how, layers.active.name)
    assert [b["name"] for b in rig.bones if b["selected"]] == ["arm"], how
    assert picked_points() == [], (how, "the outer layer's points let go", picked_points())

print("bone pick deselects points, the layer around: ok")
