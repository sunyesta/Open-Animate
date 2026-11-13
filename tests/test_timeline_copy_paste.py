"""Copy Timeline and Paste Timeline (the timeline's right-click menu, under Clear Timeline): every key of the timeline
being edited copied (frame 0's setup pose left out), and pasted into another timeline in place of its keys, on the
same frames and the same layers' channels; frame 0 stays. The copied timeline, the mainline and other actions are
left alone; one undo step puts it back; nothing to paste onto changes nothing.

Run with:  OpenAnimate --background --python tests/test_timeline_copy_paste.py
"""

import oanim

ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers
D = lambda: oanim.data.document

ARM = 'bones["arm"].angle'


def keys(layer, path):
    return [(k["frame"], round(k["value"], 6) if isinstance(k["value"], float) else tuple(round(v, 6) for v in k["value"]))
            for k in layer.keyframes(path)]


def go(frame):
    D().frame_current = frame + 1
    D().frame_current = frame


assert ops.wm.read_homefile() == {'FINISHED'}
D().auto_key = True
D().frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = L.active
assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
ops.layer.new()
hand = L.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
hand = next(x for x in L.all() if x.id == hand.id)
hand.add_curve([(0.0, 0.0), (0.5, 0.5)])
setup_angle = next(b for b in rig.bones if b["name"] == "arm")["setup_angle"]

# A mainline key, to stay where it is.
L.active = rig
D().frame_current = 30
rig.bone_set("arm", angle=setup_angle + 0.3)
go(30)
mainline = keys(rig, ARM)

# Action "wave": the arm keyed on 10 and 20, the hand's point on 15.
L.active = rig
assert ops.anim.action_new(name="wave") == {'FINISHED'}
D().frame_current = 10
rig.bone_set("arm", angle=setup_angle + 0.5)
go(10)
D().frame_current = 20
rig.bone_set("arm", angle=setup_angle - 0.25)
go(20)
D().frame_current = 15
hand.set_point(1, (0.75, 0.25))
go(15)
wave_arm, wave_hand = keys(rig, ARM), keys(hand, "points[1].pos")
assert [f for f, _ in wave_arm] == [0, 10, 20] and [f for f, _ in wave_hand] == [0, 15], (wave_arm, wave_hand)
go(5)
wave_5 = next(b for b in rig.bones if b["name"] == "arm")["angle"]
D().action = ""
go(0)

# Action "shrug": a key of its own on 5, to be replaced.
L.active = rig
assert ops.anim.action_new(name="shrug") == {'FINISHED'}
D().frame_current = 5
rig.bone_set("arm", angle=setup_angle + 1.0)
go(5)
assert [f for f, _ in keys(rig, ARM)] == [0, 5], keys(rig, ARM)
D().action = ""
go(0)

# --- Nothing copied yet: Paste Timeline has nothing ------------------------------------------------------------------
assert ops.anim.action_set(name="shrug") == {'FINISHED'}
assert ops.anim.timeline_paste() == {'CANCELLED'}
assert [f for f, _ in keys(rig, ARM)] == [0, 5], ("nothing to paste changes nothing", keys(rig, ARM))

# --- Copy "wave", paste into "shrug": its keys replaced by wave's, on the same frames ------------------------------
assert ops.anim.action_set(name="wave") == {'FINISHED'}
assert ops.anim.timeline_copy() == {'FINISHED'}
assert ops.anim.action_set(name="shrug") == {'FINISHED'}
question = wm.timeline_paste_question()
assert question.startswith("Replace the 1 key on shrug with the ") and question.endswith(" keys copied from wave?"), \
    question
assert ops.anim.timeline_paste() == {'FINISHED'}
assert keys(rig, ARM) == wave_arm, ("the arm's keys are wave's", keys(rig, ARM), wave_arm)
assert keys(hand, "points[1].pos") == wave_hand, ("the hand's too", keys(hand, "points[1].pos"), wave_hand)
go(10)
arm_now = next(b for b in rig.bones if b["name"] == "arm")["angle"]
assert abs(arm_now - (setup_angle + 0.5)) < 1e-5, ("and it plays them", arm_now)
go(5)
arm_now = next(b for b in rig.bones if b["name"] == "arm")["angle"]
assert abs(arm_now - wave_5) < 1e-5 and abs(arm_now - (setup_angle + 1.0)) > 0.1, \
    ("shrug's own key on 5 is gone: wave's frame 5", arm_now, wave_5)

# The copied timeline and the mainline are as they were.
assert ops.anim.action_set(name="wave") == {'FINISHED'}
assert keys(rig, ARM) == wave_arm and keys(hand, "points[1].pos") == wave_hand, "wave untouched"
assert ops.anim.action_set(name="") == {'FINISHED'}
assert keys(rig, ARM) == mainline, ("the mainline untouched", keys(rig, ARM), mainline)

# --- One undo step puts shrug back ------------------------------------------------------------------------------------
assert ops.anim.action_set(name="shrug") == {'FINISHED'}
assert ops.anim.timeline_copy() == {'FINISHED'}
assert ops.anim.timeline_clear() == {'FINISHED'}
assert [f for f, _ in keys(rig, ARM)] == [], keys(rig, ARM)
assert ops.anim.timeline_paste() == {'FINISHED'}
assert keys(rig, ARM) == wave_arm, "a copy of shrug pasted back into it, cleared"
assert ops.ed.undo() == {'FINISHED'}
assert [f for f, _ in keys(rig, ARM)] == [], ("undone: cleared again", keys(rig, ARM))
assert ops.ed.undo() == {'FINISHED'}
assert keys(rig, ARM) == wave_arm, keys(rig, ARM)

# --- An empty timeline copies nothing, and keeps what was copied -----------------------------------------------------
L.active = rig
assert ops.anim.action_new(name="empty") == {'FINISHED'}
assert ops.anim.timeline_copy() == {'CANCELLED'}
assert ops.anim.timeline_paste() == {'FINISHED'}, "shrug's copy still there to paste"
assert keys(rig, ARM) == wave_arm, keys(rig, ARM)
D().action = ""
go(0)

# --- Pasted where none of its layers are: nothing changes ------------------------------------------------------------
assert ops.layer.new_bone() == {'FINISHED'}
other = L.active
assert ops.armature.bone_add(name="leg", head_x="3", head_y="0", tail_x="4", tail_y="0") == {'FINISHED'}
assert ops.anim.action_new(name="kick") == {'FINISHED'}
D().frame_current = 8
other.bone_set("leg", angle=next(b for b in other.bones if b["name"] == "leg")["setup_angle"] + 0.4)
go(8)
kick = keys(other, 'bones["leg"].angle')
assert ops.anim.timeline_paste() == {'CANCELLED'}
assert keys(other, 'bones["leg"].angle') == kick, ("kept: nothing of wave's is here", keys(other, 'bones["leg"].angle'))
D().action = ""
go(0)

print("Timeline copy and paste tests passed")
