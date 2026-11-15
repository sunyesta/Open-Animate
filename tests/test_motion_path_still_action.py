"""A knob's keys key a bone's path only where its action moves the bone: a head turn's actions key the pupil where it
is (held at its setup on every key), so the turn's knob keyed on 28 left a key in the middle of the pupil's own move
0-47, splitting its path there (the halves drawn apart with Own Motion). An ear the turn carries keeps the knob's key
between its own, as before (On Path edits it there), Own Motion on or off.

Run with:  OpenAnimate --background --python tests/test_motion_path_still_action.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm
ops.wm.read_homefile()
doc.path_show_all = True
assert doc.path_own_motion, "on by default"
doc.auto_key = True
doc.frame_current = 0
doc.frame_end = 60
ops.layer.new_bone()
rig = layers.active


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


assert ops.armature.bone_add(name="pupil", head_x="0", head_y="0", tail_x="0.2", tail_y="0") == {'FINISHED'}
ops.armature.select_none()
assert ops.armature.bone_add(name="ear", head_x="0", head_y="-1", tail_x="0.2", tail_y="-1") == {'FINISHED'}
ops.armature.select_none()
assert ops.armature.bone_add(name="head", head_x="2", head_y="2", tail_x="2", tail_y="2.3") == {'FINISHED'}
# The turn keys the pupil where it is and carries the ear.
assert ops.anim.action_new(name="turn") == {'FINISHED'}
doc.frame_current = 10
rig.keyframe_insert('bones["pupil"].position')
rig.bone_set("ear", position=(0.3, -1.0))
go(10)
assert len(rig.keyframes('bones["pupil"].position')) >= 2, "the turn keys the pupil"
assert len({k["value"] for k in rig.keyframes('bones["pupil"].position')}) == 1, "held where it is"
doc.action = ""
go(0)
layers.active = rig
ops.armature.select_none()
rig.select_bone("head")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="turn") == {'FINISHED'}
# The pupil and the ear move on their own 0-47 (keyed first, so Auto-Freeze holds nothing at 28); the head turns on 28.
doc.frame_current = 47
rig.bone_set("pupil", position=(1.0, 0.0))
rig.bone_set("ear", position=(1.0, -1.0))
go(47)
doc.frame_current = 28
rig.bone_set("head", knob=(20.0, 0.0))
go(28)
for n in ("pupil", "ear"):
    assert [k["frame"] for k in rig.keyframes(f'bones["{n}"].position')] == [0, 47], n
assert 28 in [k["frame"] for k in rig.keyframes('bones["head"].position')]


def paths(name):
    out = [p for p in wm.motion_paths() if p["label"].startswith(name + " ")]
    assert out, [p["label"] for p in wm.motion_paths()]
    return out


assert ops.wm.tool_motion_path() == {'FINISHED'}

# --- The pupil: one stretch 0-47, whatever the frame shown, Own Motion on or off -------------------------------------
ops.armature.select_none()
rig.select_bone("pupil")
for own in (True, False):
    doc.path_own_motion = own
    for f in (20, 28, 40):
        go(f)
        for p in paths("pupil"):
            assert p["keys"] == [47], (own, f, p["label"], p["keys"])
            assert p["first"] == 0 and len(p["points"]) == 48, (own, f, p["first"], len(p["points"]))
        assert wm.motion_path_range() == (0, 47), (own, f, wm.motion_path_range())
doc.path_own_motion = True

# --- The ear the turn carries: the knob's key between its own, as before ---------------------------------------------
ops.armature.select_none()
rig.select_bone("ear")
go(40)
for p in paths("ear"):
    assert p["keys"] == [28, 47], (p["label"], p["keys"])

print("motion path still action: ok")
