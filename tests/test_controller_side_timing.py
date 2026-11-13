"""A 2 Axis Controller side's timing: in that side's own action the knob moves along the side's axis only, and its keys
there say how far out it is on each frame: at rest until the first, straight between them, held after the last. On the
mainline how far out the knob is picks the action's frame through those keys (past the last one's place, the frame it
first got there); with none, frame N is N Frame Sizes out. Keys never go back (a lower one is held at the one before),
the box reaches where the knob plays the action's end, and the keys never move the knob on the mainline. Deleting them
gives even timing back.

Run with:  OpenAnimate --background --python tests/test_controller_side_timing.py
"""

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active
KNOB = 'bones["eye"].position'


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


def hi():
    return bone("eye")["controller_box"][1]


assert ops.armature.bone_add(name="eye", head_x="0", head_y="0", tail_x="0.1", tail_y="0") == {'FINISHED'}
ops.layer.new()
pupil = layers.active
ops.layer.move_to_group(group=str(rig.id))
pupil.add_curve([(0.0, 0.0), (0.2, 0.0)])
assert ops.layer.parent_bone_set(bone="eye") == {'FINISHED'}
assert ops.anim.action_new(name="eye_r") == {'FINISHED'}
doc.frame_current = 40
pupil.set_point(1, (0.3, 0.0))
go(40)
doc.action = ""
go(0)
layers.active = rig
ops.armature.select_none()
rig.select_bone("eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="eye_r") == {'FINISHED'}
size = bone("eye")["controller_frame_size"]
assert close(hi(), (40, 0)), ("even timing: the box reaches the action's length", hi())

# --- In the side's own action: the knob keys along its axis only -----------------------------------------------------
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
go(10)
assert close(bone("eye")["knob_shown"], (0, 0)), ("no keys yet: it rests, not moving by itself", bone("eye")["knob_shown"])
doc.frame_current = 20
rig.bone_set("eye", knob=(10.0, 5.0))
go(20)
keyed = {k["frame"]: k["value"] for k in rig.keyframes(KNOB)}
assert 20 in keyed and close(keyed[20], (10, 0)), ("the key is along its axis only", keyed)
assert close(bone("eye")["knob_shown"], (10, 0)), ("keyed along its axis only", bone("eye")["knob_shown"])
go(10)
assert close(bone("eye")["knob_shown"], (5, 0)), ("straight between keys", bone("eye")["knob_shown"])
go(30)
assert close(bone("eye")["knob_shown"], (10, 0)), ("held past the last key", bone("eye")["knob_shown"])

# Dragged, it goes along the axis from where it is shown.
ops.armature.select_none()
rig.select_bone("eye")
go(30)
assert ops.armature.select_all(action="SELECT") == {'FINISHED'}
assert bone("eye")["selected"], "free in its own side action: it stays picked"
assert rig.drag_bone_ends([(0.0, 0.0), (5 * size, 5 * size)])
go(30)
assert 30 in [k["frame"] for k in rig.keyframes(KNOB)], rig.keyframes(KNOB)
assert close(bone("eye")["knob_shown"], (15, 0)), ("dragged along its axis, from where it is held",
                                                   bone("eye")["knob_shown"])
assert close(hi(), (15, 0)), ("the box reaches where the action's end plays: the last key's place", hi())

# A key going back is held at the one before.
doc.frame_current = 35
rig.bone_set("eye", knob=(5.0, 0.0))
go(35)
assert close(hi(), (15, 0)), ("never going back", hi())
assert close(bone("eye")["knob_shown"], (15, 0)), bone("eye")["knob_shown"]

# --- The mainline: how far out picks the frame through the keys; they never move the knob -----------------------------
assert ops.anim.action_set(name="") == {'FINISHED'}
go(7)
assert close(bone("eye")["knob"], (0, 0)), ("the action's keys don't move the knob", bone("eye")["knob"])
assert close(playing("eye_r"), 0), playing("eye_r")
for out, frame in ((5, 10), (10, 20), (12.5, 25), (15, 30), (20, 30), (50, 30)):
    rig.bone_set("eye", knob=(float(out), 0.0))
    go(7)
    assert close(playing("eye_r"), frame), ("%s out plays frame %s" % (out, frame), playing("eye_r"))

# --- A copy isn't the action's controller: the timing keys stay behind -------------------------------------------------
go(0)
ops.armature.select_none()
rig.select_bone("eye")
assert ops.armature.duplicate_move() == {'FINISHED'}
copy = next(b["name"] for b in rig.bones if b["name"].startswith("eye."))
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
frames = lambda name: [k["frame"] for k in rig.keyframes('bones["%s"].position' % name) if k["frame"]]
assert frames(copy) == [], ("they'd play as moves", frames(copy))
assert frames("eye") == [20, 30, 35], ("the original keeps them", frames("eye"))
assert ops.anim.action_set(name="") == {'FINISHED'}
go(7)

# --- Deleting the keys: even timing again ------------------------------------------------------------------------------
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
for frame in (20, 30, 35):
    rig.keyframe_delete(KNOB, frame)
assert ops.anim.action_set(name="") == {'FINISHED'}
rig.bone_set("eye", knob=(10.0, 0.0))
go(7)
assert close(hi(), (40, 0)), ("even again", hi())
assert close(playing("eye_r"), 10), playing("eye_r")

# --- Set from Python, the knob plays its action at once, as dragging it does ------------------------------------------
rig.bone_set("eye", knob=(25.0, 0.0))
right_after = pupil.shown()[0]
go(7)
assert close(right_after, pupil.shown()[0], 1e-5), ("bone_set(knob=) shows its pose at once", right_after, pupil.shown()[0])

# --- Keys copied in the side's own action, pasted on the mainline: its timing keys stay behind ---------------------------
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
doc.frame_current = 20
rig.bone_set("eye", knob=(10.0, 0.0))
go(40)
assert 20 in [k["frame"] for k in rig.keyframes(KNOB)], rig.keyframes(KNOB)
assert ops.anim.action_set(name="") == {'FINISHED'}
go(7)
mainline_knob = [(k["frame"], k["value"]) for k in rig.keyframes(KNOB)]
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
go(40)
layers.active = rig
pupil.selected = True
assert ops.anim.keys_select(frame_start="20", frame_end="40") == {'FINISHED'}
assert ops.anim.keys_copy() == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
go(100)
assert ops.anim.keys_paste() == {'FINISHED'}
assert [(k["frame"], k["value"]) for k in rig.keyframes(KNOB)] == mainline_knob, \
    ("the timing keys would move the knob", mainline_knob, rig.keyframes(KNOB))
pasted = [k["frame"] for k in pupil.keyframes("points[1].pos")]
assert 100 in pasted, ("the pupil's key lands on the frame pasted on", pasted)
right_after = pupil.shown()[0]
go(100)
assert close(right_after, pupil.shown()[0], 1e-5), ("the frame shown after the paste", right_after, pupil.shown()[0])
# In the same action they are its timing still, and paste there.
assert ops.anim.action_set(name="eye_r") == {'FINISHED'}
go(60)
assert ops.anim.keys_paste() == {'FINISHED'}
assert 60 in [k["frame"] for k in rig.keyframes(KNOB)], rig.keyframes(KNOB)
assert ops.anim.action_set(name="") == {'FINISHED'}
go(7)

# Mainline keys of the knob pasted on the mainline move it there, shown at once.
go(7)
assert ops.anim.keys_select(frame_start="7", frame_end="7") == {'FINISHED'}
assert ops.anim.keys_copy() == {'FINISHED'}
go(60)
assert ops.anim.keys_paste() == {'FINISHED'}
assert 60 in [k["frame"] for k in rig.keyframes(KNOB)], rig.keyframes(KNOB)
right_after = (pupil.shown()[0], bone("eye")["knob_shown"])
go(60)
assert close(right_after[0], pupil.shown()[0], 1e-5) and close(right_after[1], bone("eye")["knob_shown"]), \
    ("the frame shown after the paste", right_after, pupil.shown()[0], bone("eye")["knob_shown"])

print("Controller side timing tests passed")
