"""Auto-Freeze Keys and a 2 Axis Controller's knob: a bone edited holds at the rig's poses either side, but not at
frames only a knob is keyed on whose actions don't move it. A head turn's knob keyed on 28 held a pupil the turn holds
still there, so editing the pupil on 20 put a key on 28 in the middle of its own move (its path split again). A bone
the turn carries still holds there, and other bones' keys still hold every bone (pose to pose).

Run with:  OpenAnimate --background --python tests/test_auto_freeze_knob.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def frames(rig, name):
    return [k["frame"] for k in rig.keyframes(f'bones["{name}"].position')]


def bone(rig, name):
    return next(b for b in rig.bones if b["name"] == name)


ops.wm.read_homefile()
assert doc.auto_freeze_keys, "on for new files"
doc.auto_key = True
doc.frame_current = 0
doc.frame_end = 60
ops.layer.new_bone()
rig = layers.active
for name, at in (("pupil", (0.5, 0.5)), ("ear", (0.0, -1.0)), ("arm", (-2.0, 0.0))):
    assert ops.armature.bone_add(name=name, head_x=str(at[0]), head_y=str(at[1]), tail_x=str(at[0] + 0.2),
                                 tail_y=str(at[1])) == {'FINISHED'}
    ops.armature.select_none()
assert ops.armature.bone_add(name="head", head_x="2", head_y="2", tail_x="2", tail_y="2.3") == {'FINISHED'}
# The turn holds the pupil where it is and carries the ear.
assert ops.anim.action_new(name="turn") == {'FINISHED'}
doc.frame_current = 10
rig.keyframe_insert('bones["pupil"].position')
rig.bone_set("ear", position=(0.3, -1.0))
go(10)
doc.action = ""
go(0)
layers.active = rig
ops.armature.select_none()
rig.select_bone("head")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="turn") == {'FINISHED'}
# The pupil and the ear move 0-47 (keyed first); the arm is keyed on 10; the head turns on 28.
doc.frame_current = 47
rig.bone_set("pupil", position=(1.5, 0.5))
rig.bone_set("ear", position=(1.0, -1.0))
go(47)
doc.frame_current = 10
rig.bone_set("arm", position=(-2.0, 1.0))
go(10)
doc.frame_current = 28
rig.bone_set("head", knob=(20.0, 0.0))
go(28)
assert frames(rig, "pupil") == [0, 47] and frames(rig, "ear") == [0, 47], (frames(rig, "pupil"), frames(rig, "ear"))
go(28)
ear_on_28 = bone(rig, "ear")["position"]

# --- The pupil edited on 20: held at the arm's 10, not the head turn's 28 --------------------------------------------
go(20)
p = bone(rig, "pupil")["position"]
rig.bone_set("pupil", position=(p[0], p[1] + 0.4))
go(20)
assert frames(rig, "pupil") == [0, 10, 20, 47], ("no hold on the knob's 28", frames(rig, "pupil"))
ops.armature.select_none()
rig.select_bone("pupil")
assert ops.wm.tool_motion_path() == {'FINISHED'}
go(20)
for path in [p for p in wm.motion_paths() if p["label"].startswith("pupil ")]:
    assert 28 not in path["keys"], (path["label"], path["keys"])

# --- The ear the turn carries, edited on 20: held at 28 as before, its pose there kept -------------------------------
go(20)
p = bone(rig, "ear")["position"]
rig.bone_set("ear", position=(p[0], p[1] + 0.4))
go(20)
assert frames(rig, "ear") == [0, 10, 20, 28, 47], ("held at the knob's 28", frames(rig, "ear"))
go(28)
e = bone(rig, "ear")["position"]
assert abs(e[0] - ear_on_28[0]) < 1e-5 and abs(e[1] - ear_on_28[1]) < 1e-5, (e, ear_on_28)

# --- The knob itself, edited on 20: its own key on 28 and the other bones' 10 and 47 hold it ----------------------------------------
go(20)
rig.bone_set("head", knob=(5.0, 0.0))
go(20)
assert frames(rig, "head") == [0, 10, 20, 28, 47], frames(rig, "head")

print("auto freeze knob: ok")
