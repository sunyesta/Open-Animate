"""Bone Symmetrize makes the other side the same bone in every setting, mirrored, as Blender's does: new or already
there, the other side takes the first side's relations, knob settings, look, collections and constraints;
the bones and layers they name switch to the other side's (the same one where there is none), and what has a way
flips left to right (the box's slant, Limit Angle's limits, a bone's own wind). Mirror Bones off leaves an other side
that is there as it is.

Run with:  OpenAnimate --background --python tests/test_symmetrize_settings.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    if isinstance(a, (tuple, list)):
        return all(abs(x - y) < eps for x, y in zip(a, b))
    return abs(a - b) < eps


def fresh():
    global doc, layers, rig_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.frame_current = 0
    for name in ("Hand_L", "Hand_R"):
        assert ops.layer.new() == {'FINISHED'}
        layers.active.name = name
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id


def rig():
    return next(l for l in layers.all() if l.id == rig_id)


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def has(name):
    return any(b["name"] == name for b in rig().bones)


def add(name, hx, hy, tx, ty, parent=""):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(hx), head_y=str(hy), tail_x=str(tx), tail_y=str(ty),
                                 parent=parent) == {'FINISHED'}


def constraint(name, kind):
    return next(c for c in rig().bone_constraints(name) if c["type"] == kind)


def left_side():
    """Head and two look targets with no partner made yet; Arm_L, Eye_L (a controller) and Hand_L (made after Arm_L, so
    Arm_L's Track To target's partner is made later in the same Symmetrize) with every setting off its default."""
    layers.active = rig()
    add("Head", 0, 0, 0, 1)
    add("Target_L", 1.5, 2, 1.5, 2.5)
    add("Target_R", -1.5, 2, -1.5, 2.5)
    add("Arm_L", 0.5, 0.5, 1.5, 0.3, parent="Head")
    add("Eye_L", 0.4, 1.2, 0.7, 1.2, parent="Head")
    add("Hand_L", 2.5, 0.0, 3.0, 0.0)
    rig().select_bone("Eye_L")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    rig().select_bone("Eye_L")
    assert rig().rotate_bones(0.4)
    assert abs(bone("Eye_L")["controller_box_angle"]) > 0.1, bone("Eye_L")
    assert ops.armature.bone_relations_set(bone="Eye_L", knob_independent="1", knob_parent="Target_L") == {'FINISHED'}
    assert ops.armature.bone_relations_set(bone="Arm_L", inherit_rotation="0", local_location="0") == {'FINISHED'}
    rig().bone_set("Eye_L", contain_knob=False, controller_box_show="SELECTED")
    rig().bone_set("Arm_L", strength=2.0, color_set="THEME03", shape_layer="Hand_L")
    rig().select_bone("Arm_L")
    assert ops.armature.constraint_add(bone="Arm_L", type="TRACK_TO") == {'FINISHED'}
    rig().bone_constraint_set("Arm_L", 0, target="Hand_L")
    assert ops.armature.constraint_add(bone="Arm_L", type="LIMIT_ANGLE") == {'FINISHED'}
    rig().bone_constraint_set("Arm_L", 1, min_angle=-0.3, max_angle=1.0)
    assert ops.armature.constraint_add(bone="Arm_L", type="DYNAMICS") == {'FINISHED'}
    rig().bone_constraint_set("Arm_L", 2, own_wind=True, wind=0.5, wind_direction=0.25)
    # Collections: one with a side, its partner, and one with none.
    for name in ("Arm_L", "Arm_R", "Body"):
        assert ops.armature.collection_add(name=name) == {'FINISHED'}
    rig().select_bone("Arm_L")
    assert ops.armature.collection_assign(collection="Arm_L") == {'FINISHED'}
    assert ops.armature.collection_assign(collection="Body") == {'FINISHED'}


def check_mirrored(why):
    eye, arm = bone("Eye_R"), bone("Arm_R")
    assert eye["knob_independent"] and eye["knob_parent"] == "Target_R", (why, "the knob rides the other target", eye)
    assert eye["contain_knob"] is False and eye["controller_box_show"] == "SELECTED", (why, eye)
    assert close(eye["controller_box_angle"], -bone("Eye_L")["controller_box_angle"]), \
        (why, "the box slants the other way", eye["controller_box_angle"], bone("Eye_L")["controller_box_angle"])
    assert arm["inherit_rotation"] is False and arm["local_location"] is False, (why, arm)
    assert close(arm["strength"], 2.0) and arm["color_set"] == "THEME03" and arm["shape_layer"] == "Hand_R", (why, arm)
    assert sorted(arm["collections"]) == ["Arm_R", "Body"], (why, arm["collections"])
    cs = rig().bone_constraints("Arm_R")
    assert [c["type"] for c in cs] == ["TRACK_TO", "LIMIT_ANGLE", "DYNAMICS"], (why, cs)
    assert cs[0]["target"] == "Hand_R", (why, "it aims at the other hand", cs[0])
    assert close(cs[1]["min_angle"], -1.0) and close(cs[1]["max_angle"], 0.3), (why, "limits turn the other way", cs[1])
    assert close(cs[2]["wind_direction"], math.pi - 0.25), (why, "its wind blows the other way", cs[2])


# --- The other side not there yet: made with every setting, names switched --------------------------------------------
fresh()
left_side()
layers.active = rig()
ops.armature.select_none()
assert ops.armature.symmetrize() == {'FINISHED'}
assert has("Eye_R") and has("Arm_R") and has("Hand_R")
check_mirrored("made")
assert bone("Arm_R")["parent"] == "Head", "no side: the same parent"

# --- The other side already there: it takes every setting too ---------------------------------------------------------
fresh()
left_side()
layers.active = rig()
add("Arm_R", -0.5, 0.5, -1.5, 0.3, parent="Head")
add("Hand_R", -2.5, 0.0, -3.0, 0.0)
add("Eye_R", -0.4, 1.2, -0.7, 1.2, parent="Head")
rig().select_bone("Eye_R")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.constraint_add(bone="Arm_R", type="COPY_ANGLE") == {'FINISHED'}
eye_r_id, arm_r_id = bone("Eye_R")["id"], bone("Arm_R")["id"]
ops.armature.select_none()
for name in ("Arm_L", "Eye_L", "Hand_L"):
    rig().select_bone(name, extend=True)
assert ops.armature.symmetrize() == {'FINISHED'}
assert bone("Eye_R")["id"] == eye_r_id and bone("Arm_R")["id"] == arm_r_id, "kept, not made anew"
check_mirrored("there")
# Undo puts the other side's own settings back.
assert ops.ed.undo() == {'FINISHED'}
assert not bone("Eye_R")["knob_independent"] and bone("Eye_R")["contain_knob"], bone("Eye_R")
assert [c["type"] for c in rig().bone_constraints("Arm_R")] == ["COPY_ANGLE"]

# --- Mirror Bones off: an other side that is there keeps its own settings ---------------------------------------------
ops.armature.select_none()
for name in ("Arm_L", "Eye_L", "Hand_L"):
    rig().select_bone(name, extend=True)
ops.armature.symmetrize(positions="0")
assert not bone("Eye_R")["knob_independent"] and bone("Eye_R")["contain_knob"], bone("Eye_R")
assert [c["type"] for c in rig().bone_constraints("Arm_R")] == ["COPY_ANGLE"]
assert bone("Arm_R")["inherit_rotation"] is True

print("symmetrize settings: ok")
