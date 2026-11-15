"""A knob's keys key a bone's path only where its action moves the bone: a head turn's actions key the pupil where it
is (held at its setup on every key), so the turn's knob keyed on 28 left a key in the middle of the pupil's own move
0-47, splitting its path there (the halves drawn apart with Own Motion). An ear the turn carries keeps the knob's key
between its own, as before (On Path edits it there), Own Motion on or off. Action keys hold the change from the setup,
so a pupil resting off the origin or turned (the practice file's Head_X points up) is held still by keys of 0 too.

Run with:  OpenAnimate --background --python tests/test_motion_path_still_action.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def scene(pupil_head=(0.0, 0.0), pupil_tail=(0.2, 0.0), key_angle=False):
    """The pupil and the ear keyed 0 and 47, a head knob keyed 28 whose action "turn" keys the pupil where it is
    (its angle too with key_angle) and carries the ear. Returns the rig."""
    ops.wm.read_homefile()
    doc.path_show_all = True
    assert doc.path_own_motion, "on by default"
    doc.auto_key = True
    doc.frame_current = 0
    doc.frame_end = 60
    ops.layer.new_bone()
    rig = layers.active
    assert ops.armature.bone_add(name="pupil", head_x=str(pupil_head[0]), head_y=str(pupil_head[1]),
                                 tail_x=str(pupil_tail[0]), tail_y=str(pupil_tail[1])) == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="ear", head_x="0", head_y="-1", tail_x="0.2", tail_y="-1") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="head", head_x="2", head_y="2", tail_x="2", tail_y="2.3") == {'FINISHED'}
    assert ops.anim.action_new(name="turn") == {'FINISHED'}
    doc.frame_current = 10
    rig.keyframe_insert('bones["pupil"].position')
    if key_angle:
        rig.keyframe_insert('bones["pupil"].angle')
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
    # The pupil and the ear move on their own 0-47 (keyed first, so Auto-Freeze holds nothing at 28); the head turns
    # on 28.
    doc.frame_current = 47
    rig.bone_set("pupil", position=(pupil_head[0] + 1.0, pupil_head[1]))
    rig.bone_set("ear", position=(1.0, -1.0))
    go(47)
    doc.frame_current = 28
    rig.bone_set("head", knob=(20.0, 0.0))
    go(28)
    for n in ("pupil", "ear"):
        assert [k["frame"] for k in rig.keyframes(f'bones["{n}"].position')] == [0, 47], n
    assert 28 in [k["frame"] for k in rig.keyframes('bones["head"].position')]
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    return rig


def paths(name):
    out = [p for p in wm.motion_paths() if p["label"].startswith(name + " ")]
    assert out, [p["label"] for p in wm.motion_paths()]
    return out


def pupil_one_stretch(rig, what):
    ops.armature.select_none()
    rig.select_bone("pupil")
    for own in (True, False):
        doc.path_own_motion = own
        for f in (20, 28, 40):
            go(f)
            for p in paths("pupil"):
                assert p["keys"] == [47], (what, own, f, p["label"], p["keys"])
                assert p["first"] == 0 and len(p["points"]) == 48, (what, own, f, p["first"], len(p["points"]))
            assert wm.motion_path_range() == (0, 47), (what, own, f, wm.motion_path_range())
    doc.path_own_motion = True


# --- The pupil at the origin: one stretch 0-47, whatever the frame shown, Own Motion on or off -----------------------
rig = scene()
pupil_one_stretch(rig, "at the origin")

# --- The ear the turn carries: the knob's key between its own, as before ---------------------------------------------
ops.armature.select_none()
rig.select_bone("ear")
go(40)
for p in paths("ear"):
    assert p["keys"] == [28, 47], (p["label"], p["keys"])

# --- A pupil resting off the origin, held still by the turn: one stretch too -----------------------------------------
pupil_one_stretch(scene(pupil_head=(0.5, 0.5), pupil_tail=(0.7, 0.5)), "resting at (0.5, 0.5)")

# --- A pupil pointing up, its angle held by the turn too: one stretch ------------------------------------------------
pupil_one_stretch(scene(pupil_tail=(0.0, 0.2), key_angle=True), "pointing up")

# --- On Path: a bone the turn holds still can't be put On Path; one it carries takes keys where only the moving
# action's knob has them ------------------------------------------------------------------------------------------
ops.wm.read_homefile()
doc.path_show_all = True
doc.auto_key = True
doc.frame_current = 0
doc.frame_end = 60
ops.layer.new_bone()
rig = layers.active
for name, y in (("eye", 0.0), ("ear", -1.0)):
    assert ops.armature.bone_add(name=name, head_x="0", head_y=str(y), tail_x="0.2", tail_y=str(y)) == {'FINISHED'}
    ops.armature.select_none()
for name, x in (("head", 2.0), ("lid", 4.0)):
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y="2", tail_x=str(x), tail_y="2.3") == {'FINISHED'}
    ops.armature.select_none()
# The turn carries the ear and holds the eye still; the blink holds both still.
assert ops.anim.action_new(name="turn") == {'FINISHED'}
doc.frame_current = 10
rig.keyframe_insert('bones["eye"].position')
rig.bone_set("ear", position=(0.3, -1.0))
go(10)
doc.action = ""
assert ops.anim.action_new(name="blink") == {'FINISHED'}
doc.frame_current = 10
rig.keyframe_insert('bones["eye"].position')
rig.keyframe_insert('bones["ear"].position')
go(10)
doc.action = ""
go(0)
layers.active = rig
for knob, action in (("head", "turn"), ("lid", "blink")):
    ops.armature.select_none()
    rig.select_bone(knob)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action=action) == {'FINISHED'}
for knob, f in (("head", 28), ("lid", 15)):
    doc.frame_current = f
    rig.bone_set(knob, knob=(20.0, 0.0))
    go(f)
assert ops.wm.tool_motion_path() == {'FINISHED'}
doc.path_all = True
ops.armature.select_none()
rig.select_bone("eye")
go(20)
assert all(p["on_path"] is None for p in paths("eye")), ("no On Path to set", [p["on_path"] for p in paths("eye")])
assert ops.anim.motion_path_on_path(on="1", bone="eye", head="1", layer=str(rig.id)) == {'CANCELLED'}, "held still"
assert not rig.keyframes('bones["eye"].position')
ops.armature.select_none()
rig.select_bone("ear")
go(20)
assert ops.anim.motion_path_on_path(on="1", bone="ear", head="1", layer=str(rig.id)) == {'FINISHED'}
frames = [k["frame"] for k in rig.keyframes('bones["ear"].position')]
assert frames == [0, 28], ("the turn's knob, not the blink's that holds it still", frames)

print("motion path still action: ok")
