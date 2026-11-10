"""Fix actions that follow bones, and what they touch, at their edges (from a bug sweep): converting a followed
knob, Symmetrize with other knobs moved, an independent knob, switches, a bone named twice. Each section starts
from a new file.

Run with:  OpenAnimate --background --python tests/test_bone_fix_edges.py
"""

import oanim

# --- Converting a knob a fix follows: its line keys go, never moving it --------------------------------------------------
# A fix following a 2 Axis Controller and a regular bone: convert the controller to Regular and the fix's line keys
# (knob frames) play as the fix, throwing the bone it follows 24 units each way. Spec: a fix never moves the bones it
# follows.
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True
ops.layer.new_bone(); rig_id = layers.active.id
ops.armature.bone_add(name="Bone", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0"); ops.armature.select_none()
ops.armature.bone_add(name="arm", head_x="0.0", head_y="-2.0", tail_x="1.0", tail_y="-2.0"); ops.armature.select_none()
ops.armature.bone_add(name="Lid", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
def settle(): doc.frame_current += 1; doc.frame_current -= 1
def mainline(): ops.anim.action_set(name=""); doc.frame_current = 0
# The knob's sides: actions turning Lid a little by frame 24.
for side in ("Right", "Up"):
    assert ops.anim.action_new(name="Bone " + side) == {'FINISHED'}
    doc.frame_current = 24; rig().bone_set("Lid", angle=bone("Lid")["setup_angle"] + 0.1); doc.frame_current = 25
    mainline()
rig().select_bone("Bone")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=side, action="Bone " + side.title()) == {'FINISHED'}
# The fix: from rest to the knob at (24, 24) and arm turned 0.8, turning Lid 0.5 more.
rig().select_bone("Bone"); rig().select_bone("arm", extend=True)
assert ops.armature.bone_fix_new(bones="Bone,arm") == {'FINISHED'}
doc.frame_current = 30
rig().bone_set("Bone", knob=(24.0, 24.0)); rig().bone_set("arm", angle=bone("arm")["setup_angle"] + 0.8)
rig().bone_set("Lid", angle=bone("Lid")["angle"] + 0.5); settle()
mainline()
name = rig().bone_fixes[0]["name"]
rig().select_bone("Bone")
assert ops.armature.bone_convert(type="REGULAR") == {'FINISHED'}
doc.frame_current = 10
rig().bone_set("arm", angle=bone("arm")["setup_angle"] + 0.8); settle()   # arm where the line ends: the fix plays
b = bone("Bone")
moved = abs(b["position"][0] - b["setup_position"][0]) + abs(b["position"][1] - b["setup_position"][1])
assert ops.anim.action_play_set(name=name, mute="1") == {'FINISHED'}; settle()
b2 = bone("Bone")
muted = abs(b2["position"][0] - b2["setup_position"][0]) + abs(b2["position"][1] - b2["setup_position"][1])
assert moved < 1e-3, (f"Bone, followed by fix {name!r}, is moved {moved:.3f} by it after Convert To Regular: at "
                      f"{b['position']}, setup {b['setup_position']} (with the fix muted it is off by {muted:.3f})")

# --- Symmetrize: another knob's keys mirror with Left and Right swapped --------------------------------------------------
# Symmetrize with Mirror Action Bone Actions: an action bone action (Eye_L Right) that also moves another 2 Axis
# Controller's knob (Brow_L to Right 6, Up 3) is mirrored into Eye_R Left with Brow_R's knob at Right 6, Down 3 (turned
# over through the bone) instead of Left 6, Up 3 (Left and Right swapped, as the sides and a fix's own line are), so
# Brow_R plays nothing where Brow_L played its Right and Up.
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True
ops.layer.new_bone(); rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
def turned(n):
    b = bone(n); return (b["angle"] - b["setup_angle"] + 3.14159265) % 6.2831853 - 3.14159265
def settle(): doc.frame_current += 1; doc.frame_current -= 1
def mainline(): ops.anim.action_set(name=""); doc.frame_current = 0
def knob(n, x, y):
    doc.frame_current = 5; rig().select_bone(n); rig().bone_set(n, knob=(x, y)); settle()
ops.armature.bone_add(name="Eye_L", head_x="2.0", head_y="3.0", tail_x="2.5", tail_y="3.0"); ops.armature.select_none()
ops.armature.bone_add(name="Lid_L", head_x="2.0", head_y="4.0", tail_x="3.0", tail_y="4.0"); ops.armature.select_none()
ops.armature.bone_add(name="Brow_L", head_x="2.0", head_y="6.0", tail_x="2.5", tail_y="6.0")
for knob_name, sides in (("Brow_L", ("Right", "Up")), ("Eye_L", ("Right",))):
    for side in sides:
        assert ops.anim.action_new(name=f"{knob_name} {side}") == {'FINISHED'}
        doc.frame_current = 24
        if knob_name == "Brow_L":   # Brow_L's sides turn the lid
            rig().bone_set("Lid_L", angle=bone("Lid_L")["setup_angle"] + 0.2)
        doc.frame_current = 25; mainline()
    rig().select_bone(knob_name)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    for side in sides:
        assert ops.armature.controller_side(side=side.upper(), action=f"{knob_name} {side}") == {'FINISHED'}
# Eye_L Right moves Brow_L's knob to Right 6, Up 3 by its end.
ops.anim.action_set(name="Eye_L Right", layer=str(rig_id)); doc.frame_current = 24
rig().bone_set("Brow_L", knob=(6.0, 3.0)); settle(); mainline()
knob("Eye_L", 24.0, 0.0)
left_knob, left_lid = bone("Brow_L")["knob"], turned("Lid_L")
knob("Eye_L", 0.0, 0.0); mainline()
ops.armature.select_none()
for n in ("Eye_L", "Lid_L", "Brow_L"):
    rig().select_bone(n, extend=True)
assert ops.armature.symmetrize(action_bone_actions="1") == {'FINISHED'}
knob("Eye_R", -24.0, 0.0)
right_knob, right_lid = bone("Brow_R")["knob"], turned("Lid_R")
assert abs(right_knob[0] + left_knob[0]) < 1e-3 and abs(right_knob[1] - left_knob[1]) < 1e-3 and abs(right_lid + left_lid) < 1e-3, (
    f"Eye_L Right puts Brow_L's knob at {left_knob} (Lid_L turned {left_lid:.3f}); mirrored, Eye_R Left puts Brow_R's knob "
    f"at {right_knob} (Lid_R turned {right_lid:.3f}): expected ({-left_knob[0]}, {left_knob[1]}) and {-left_lid:.3f}")

# --- A fix on an independent knob starts where the knob plays ------------------------------------------------------------
# Create Fix Action on an independent 2 Axis Controller knob riding its Knob Parent (moved 6 frames right on the
# mainline, so the knob sits and plays at Right 6): the fix's line starts at the knob's key (0, 0), not where it is on the
# mainline (6, 0), so back on the mainline at that very pose the fix plays partway (frame ~10 of 30, strength ~0.5) and
# the pose it was made at changes. Spec: "it opens on frame 1 with them keyed where they are on the mainline now".
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True; doc.frame_current = 0
ops.layer.new_bone(); rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
def go(f): doc.frame_current = f + 1; doc.frame_current = f
def add(name, head, tail):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]), tail_y=str(tail[1])) == {'FINISHED'}
add("eye", (0, 0), (0.1, 0)); add("center", (0, 0.5), (0.1, 0.5)); add("Lid", (3, 3), (4, 3))
for s in ("Right", "Up"):   # each side turns Lid 0.1
    assert ops.anim.action_new(name="eye " + s) == {'FINISHED'}
    doc.frame_current = 24; rig().bone_set("Lid", angle=bone("Lid")["setup_angle"] + 0.1); go(24)
    ops.anim.action_set(name=""); go(0)
rig().select_bone("eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for s in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=s, action="eye " + s.title()) == {'FINISHED'}
assert ops.armature.bone_relations_set(bone="eye", knob_parent="center") == {'FINISHED'}
size = bone("eye")["controller_frame_size"]
doc.frame_current = 5; rig().bone_set("center", position=(6 * size, 0.0)); go(5)   # the knob rides it to Right 6
shown = bone("eye")["knob_shown"]
lid_before = bone("Lid")["angle"] - bone("Lid")["setup_angle"]
rig().select_bone("eye")
assert ops.armature.bone_fix_new(bones="eye") == {'FINISHED'}
in_fix = bone("eye")["knob_shown"]
doc.frame_current = 30; rig().bone_set("eye", knob=(18.0, 12.0)); rig().bone_set("Lid", angle=bone("Lid")["angle"] + 0.5); go(30)
ops.anim.action_set(name=""); go(5)
f = rig().bone_fixes[0]
lid_after = bone("Lid")["angle"] - bone("Lid")["setup_angle"]
assert abs(f["frame"] - 1.0) < 0.5 and abs(lid_after - lid_before) < 1e-3, (
    f"mainline knob at {shown}; the fix opened with it at {in_fix} on frame 1; back at that mainline pose the fix plays "
    f"frame {f['frame']:.2f} strength {f['strength']:.2f} (expected frame 1: where it starts), Lid {lid_before:.4f} -> {lid_after:.4f}")

# --- A fix's switch keys pick on the mainline ----------------------------------------------------------------------------
# A fix that follows a 2 Axis Controller and switches a Switch layer inside the rig (to "B" where it ends) never switches
# it on the mainline, though the fix plays whole there (strength 1, its last frame): play_fix in apply_action_bone_actions
# skips switch channels. Spec: everything else keyed in it is the fix along that line (drawings, ...).
# (Picking B inside the fix also changes the switch's mainline default A -> B: put back to A here before checking.)
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True; doc.frame_current = 0
ops.layer.new_bone(); rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
def go(f): doc.frame_current = f + 1; doc.frame_current = f
def mainline(): ops.anim.action_set(name=""); go(0)
ops.armature.bone_add(name="Bone", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0"); ops.armature.select_none()
ops.armature.bone_add(name="Lid", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
assert ops.layer.new_switch() == {'FINISHED'}
sw_id = layers.active.id
assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
for name in ("A", "B"):
    ops.layer.new(); layers.active.name = name; layers.active.add_curve([(0.0, 0.0), (1.0, 0.0)])
    assert ops.layer.move_to_group(group=str(sw_id)) == {'FINISHED'}
sw = lambda: next(l for l in layers.all() if l.id == sw_id)
assert ops.layer.switch_set(layer=sw().name, child="A") == {'FINISHED'}   # the default
layers.active = rig()
for side in ("Right", "Up"):   # the knob's sides turn Lid
    assert ops.anim.action_new(name="Bone " + side) == {'FINISHED'}
    doc.frame_current = 24; rig().bone_set("Lid", angle=bone("Lid")["setup_angle"] + 0.1); go(24); mainline()
rig().select_bone("Bone")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=side, action="Bone " + side.title()) == {'FINISHED'}
rig().select_bone("Bone")
assert ops.armature.bone_fix_new(bones="Bone") == {'FINISHED'}
doc.frame_current = 30; rig().bone_set("Bone", knob=(24.0, 24.0)); go(30)
assert ops.layer.switch_set(layer=sw().name, child="B") == {'FINISHED'}   # the fix switches to B where it ends
go(30); in_fix = sw().switch_active
layers.active = rig(); mainline()
leaked = sw().switch_default
assert ops.layer.switch_set(layer=sw().name, child="A") == {'FINISHED'}   # the default back to A
layers.active = rig()
doc.frame_current = 5; rig().select_bone("Bone"); rig().bone_set("Bone", knob=(24.0, 24.0)); go(5)
f = rig().bone_fixes[0]
assert in_fix == "B" and abs(f["strength"] - 1.0) < 1e-4, (in_fix, f)
assert sw().switch_active == "B", (f"fix {f['name']!r} plays whole (frame {f['frame']}, strength {f['strength']}) and "
                                   f"switches to B in it, but the mainline shows {sw().switch_active!r} "
                                   f"(and the default had leaked to {leaked!r})")

# --- Picking a switch child in an action leaves the mainline's default ---------------------------------------------------
# Picking a Switch child (layer.switch_set) on frame 30 inside an ordinary action of the rig keys it there, but also
# changes the switch's mainline default (frame 0) from A to B when the mainline has no switch keys: back on the mainline,
# frame 0 shows B. An edit inside an action should leave the mainline alone.
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
doc.auto_key = True; doc.frame_current = 0
ops.layer.new_bone(); rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
def go(f): doc.frame_current = f + 1; doc.frame_current = f
ops.armature.bone_add(name="Bone", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
assert ops.layer.new_switch() == {'FINISHED'}
sw_id = layers.active.id
assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
for name in ("A", "B"):
    ops.layer.new(); layers.active.name = name; layers.active.add_curve([(0.0, 0.0), (1.0, 0.0)])
    assert ops.layer.move_to_group(group=str(sw_id)) == {'FINISHED'}
sw = lambda: next(l for l in layers.all() if l.id == sw_id)
assert ops.layer.switch_set(layer=sw().name, child="A") == {'FINISHED'}
before = sw().switch_default
layers.active = rig()
assert ops.anim.action_new(name="Wave") == {'FINISHED'}
go(30)
assert ops.layer.switch_set(layer=sw().name, child="B") == {'FINISHED'}
layers.active = rig(); assert ops.anim.action_set(name="") == {'FINISHED'}; go(0)
assert sw().switch_default == before and sw().switch_active == before, (
    f"default {before!r} before; after picking B on frame 30 of action Wave, the mainline default is "
    f"{sw().switch_default!r} and frame 0 shows {sw().switch_active!r}")

# --- A bone named twice counts once toward a fix's 2 ways ----------------------------------------------------------------
# armature.bone_fix_new(bones="arm,arm"): the one regular bone (one way) is counted twice toward the 2 ways a fix needs,
# so a fix following one bone turning is made (bones="arm" alone is refused).
oanim.ops.wm.read_homefile()
ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.layer.new_bone(); rig_id = layers.active.id
ops.armature.bone_add(name="arm", head_x="0.0", head_y="0.0", tail_x="1.0", tail_y="0.0")
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
assert ops.armature.bone_fix_new(bones="arm") == {'CANCELLED'}
r = ops.armature.bone_fix_new(bones="arm,arm")
assert r == {'CANCELLED'}, f"bone_fix_new(bones='arm,arm') returned {r}, making {rig().bone_fixes} (1 way, as bones='arm' which is refused)"

print("test_bone_fix_edges: ok")
