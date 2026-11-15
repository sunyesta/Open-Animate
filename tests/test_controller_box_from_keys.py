"""A 2 Axis Controller's box comes from where its knob is keyed in each side's action, with no Frame Size to set: a side
reaches the farthest place the knob is keyed there. Picking another action never moves a keyed edge (the box is
fitted to its actions' lengths only while no side is keyed); a side not keyed yet takes the opposite side's length,
keyed there, with even timing (else its action's length, as before); a side keyed only at rest counts as not keyed.

Run with:  OpenAnimate --background --python tests/test_controller_box_from_keys.py
"""

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active


def bone(name):
    return next(b for b in rig.bones if b["name"] == name)


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def close(a, b, eps=1e-3):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def playing(name):
    return next(a["frame"] for a in rig.actions if a["name"] == name)


def box():
    return bone("eye")["controller_box"]


def size():
    return bone("eye")["controller_frame_size"]


assert ops.armature.bone_add(name="eye", head_x="0", head_y="0", tail_x="0.1", tail_y="0") == {'FINISHED'}
ops.layer.new()
pupil = layers.active
ops.layer.move_to_group(group=str(rig.id))
pupil.add_curve([(0.0, 0.0), (0.2, 0.0)])
assert ops.layer.parent_bone_set(bone="eye") == {'FINISHED'}
for name, length, to in (("eye_r", 40, (0.3, 0.0)), ("eye_l", 60, (-0.3, 0.0)), ("eye_u", 30, (0.0, 0.3))):
    layers.active = pupil
    assert ops.anim.action_new(name=name) == {'FINISHED'}
    doc.frame_current = length
    pupil.set_point(1, to)
    go(length)
    doc.action = ""
go(0)
layers.active = rig
ops.armature.select_none()
rig.select_bone("eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="eye_r") == {'FINISHED'}

# --- Keyed in its action: the right edge is where the knob was keyed --------------------------------------------------
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
doc.frame_current = 40
rig.bone_set("eye", knob=(10.0, 0.0))
go(40)
assert ops.anim.action_set(name="") == {'FINISHED'}
go(0)
edge = box()[1][0] * size()
assert close(box()[1][0], 10), ("the right side reaches the knob's key", box())

# --- Picking a longer action for Left leaves the keyed right edge where it is -----------------------------------------
assert ops.armature.controller_side(side="LEFT", action="eye_l") == {'FINISHED'}
go(0)
assert close(box()[1][0] * size(), edge, 1e-6), ("the keyed edge stays put", box()[1][0] * size(), edge)

# --- Left, not keyed yet, is as long as Right is keyed, its frames even along it --------------------------------------
assert close(box()[0][0], -10), ("the unkeyed side takes the keyed opposite side's length", box())
go(7)
rig.bone_set("eye", knob=(-5.0, 0.0))
go(7)
assert close(playing("eye_l"), 30), ("halfway out plays half its 60 frames", playing("eye_l"))
rig.bone_set("eye", knob=(-10.0, 0.0))
go(7)
assert close(playing("eye_l"), 60), ("at the edge it plays its end", playing("eye_l"))
rig.bone_set("eye", knob=(0.0, 0.0))
go(7)

# In its own action the knob runs out evenly to that length.
assert ops.anim.action_set(name="eye_l") == {'FINISHED'}
go(30)
assert close(bone("eye")["knob_shown"], (-5, 0)), ("even timing out to the borrowed length", bone("eye")["knob_shown"])
assert ops.anim.action_set(name="") == {'FINISHED'}

# --- Up has no keyed opposite: its own length, as before; keyed only at rest it still is -------------------------------
assert ops.armature.controller_side(side="UP", action="eye_u") == {'FINISHED'}
go(0)
assert close(box()[1][1], 30), ("no keyed opposite: its action's length", box())
assert ops.anim.action_set(name="eye_u") == {'FINISHED'}
doc.frame_current = 15
rig.bone_set("eye", knob=(0.0, 0.0))
go(15)
assert ops.anim.action_set(name="") == {'FINISHED'}
go(0)
assert close(box()[1][1], 30), ("a key at rest gives the side no length: not keyed", box())

print("controller box from keys OK")
