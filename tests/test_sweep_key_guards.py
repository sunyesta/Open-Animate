"""Guards from a bug sweep of the eye file: numbers past any use, key moves past the last frame, pasted keys and the
setup frame, Select All with Only Selected, a no-op Scale Keys, Save Incremental's digits and a switch's reference.
Each section builds its own scene and failed on the build before its fix.

Run with:  OpenAnimate --background --python tests/test_sweep_key_guards.py
"""

import math
import os
import shutil
import tempfile

import oanim

ops, doc, L, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def rig_scene(*bones):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc.auto_key = True
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = L.active
    for name, head, tail in bones:
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                     tail_y=str(tail[1])) == {'FINISHED'}
    ops.anim.timeline_filter(only_selected="0")
    return rig


def bone(rig, name):
    return next(b for b in rig.bones if b["name"] == name)


def finite(values):
    return all(math.isfinite(v) for v in values)


def key_scene():
    """A layer keyed at 5, 10 and 20 (and 0), its keys at 5 and 10 picked."""
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc.auto_key = True
    ops.layer.new()
    lay = L.active
    for f, x in ((5, 1.0), (10, 2.0), (20, 3.0)):
        doc.frame_current = f
        lay.location_x = x
    doc.frame_current = 12
    assert ops.anim.keys_select(frame_start="5", frame_end="10", layers=str(lay.id), path="position") == {'FINISHED'}
    return lay


def frames(lay):
    return [k['frame'] for k in lay.keyframes('position')]


# --- Numbers past ten million are refused, as nan is: a bone added or moved by 1e30 posed nothing finite
rig = rig_scene(("A", (0, 0), (1, 0)))
r = ops.armature.bone_add(name="Far", head_x="1e30", head_y="0", tail_x="0.1", tail_y="1e30")
for b in rig.bones:
    assert finite(tuple(b["head"]) + tuple(b["tail"])), ("bone_add 1e30", r, b["name"], b["head"], b["tail"])
ops.armature.select_none()
rig.select_bone("A")
doc.frame_current = 10
ops.armature.translate(move_x="1e30", move_y="0.01")
a = bone(rig, "A")
assert finite(tuple(a["head"]) + tuple(a["tail"])), ("translate 1e30", a["head"], a["tail"])
assert abs(a["head"][0]) < 1e7, ("translate 1e30 refused", a["head"])

# --- Bones scale at most a thousand times: by ten thousand each drawing's deform took seconds, by INT_MAX forever
rig = rig_scene(("A", (0, 0), (1, 0)))
rig.select_bone("A")
doc.frame_current = 10
ops.armature.resize(scale="100000", axis="0", squash="0")
a = bone(rig, "A")
length = math.dist(a["head"], a["tail"])
assert length <= 1000.0 + 1e-2, ("scaled past a thousand", length)

# --- A knob key pasted on frame 0 leaves its controller where it rests
rig = rig_scene(("stick", (0, 0), (1, 0)))
rig.select_bone("stick")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
ops.layer.new()
face = L.active
ops.layer.move_to_group(group=str(rig.id))
face.add_curve([(8.0, 8.0), (9.0, 8.0)])
for name, at in (("go_r", 40), ("go_u", 20)):
    assert ops.anim.action_new(name=name) == {'FINISHED'}
    doc.frame_current = at
    face.set_point(0, (8.0, 9.0))
    doc.frame_current = at + 1
    doc.action = ""
    doc.frame_current = 0
L.active = rig
ops.armature.select_none()
rig.select_bone("stick")
for side, act in (("RIGHT", "go_r"), ("UP", "go_u")):
    assert ops.armature.controller_side(side=side, action=act) == {'FINISHED'}
for o in L.all():
    o.selected = o.id == rig.id
L.active = rig
doc.frame_current = 10
rig.bone_set("stick", knob=(10.0, 5.0))
doc.frame_current = 11
doc.frame_current = 0
rest = tuple(bone(rig, "stick")["head"])
doc.frame_current = 10
ops.anim.keys_select(frame_start="10", frame_end="10")
assert ops.anim.keys_copy() == {'FINISHED'}
doc.frame_current = 0
ops.anim.keys_paste()
doc.frame_current = 1
doc.frame_current = 0
now = tuple(bone(rig, "stick")["head"])
assert math.dist(now, rest) < 1e-4, ("the controller moved on frame 0", rest, now)

# --- Keys pasted onto a channel not keyed yet leave frame 0's setup pose, as a hand key does
rig = rig_scene(("A", (0, 0), (1, 0)))
assert ops.anim.action_new(name="wave") == {'FINISHED'}
doc.frame_current = 10
rig.bone_set("A", angle=0.5)
doc.frame_current = 11
ops.anim.keys_select(frame_start="10", frame_end="10")
assert ops.anim.keys_copy() == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
doc.frame_current = 0
before = bone(rig, "A")["angle"]
doc.frame_current = 20
assert ops.anim.keys_paste() == {'FINISHED'}
doc.frame_current = 0
assert abs(bone(rig, "A")["angle"] - before) < 1e-6, ("paste at 20 changed frame 0", before, bone(rig, "A")["angle"])
doc.frame_current = 20
assert abs(bone(rig, "A")["angle"] - 0.5) < 1e-6, ("the pasted key", bone(rig, "A")["angle"])

# --- Select All with Only Selected picks the keys the rows show: an unpicked bone's went with the next Delete
rig = rig_scene(("A", (0, 0), (1, 0)), ("B", (0, 1), (1, 1)))
ops.anim.timeline_filter(only_selected="1")
doc.frame_current = 10
rig.bone_set("A", angle=0.5)
doc.frame_current = 15
rig.bone_set("B", angle=0.3)
doc.frame_current = 12
assert doc.timeline_only_selected
ops.armature.select_none()
rig.select_bone("A")
ops.anim.keys_select_all()
ops.anim.keys_delete()
b_keys = [k['frame'] for k in rig.keyframes('bones["B"].angle')]
assert 15 in b_keys, ("B's keys, on no row, were deleted", b_keys)

# --- Key moves past the last frame stop there: INT_MAX wrapped round the int, a big scale lost keys
lay = key_scene()
ops.anim.keys_offset(frames="2147483647")
f = frames(lay)
assert min(x for x in f if x) >= 5 and max(f) <= 1048574, ("keys_offset(INT_MAX)", f)
lay = key_scene()
ops.anim.keys_duplicate(frames="2147483647")
f = frames(lay)
assert 1 not in f and max(f) <= 1048574, ("keys_duplicate(INT_MAX)", f)
lay = key_scene()
ops.anim.keys_scale(factor="1000000")
f = frames(lay)
assert len(f) == 4 and max(f) <= 1048574, ("keys_scale(1e6) lost a key", f)

# --- Scale Keys by 1 changes nothing: no undo step, no keys picked
lay = key_scene()
assert ops.anim.keyframe_insert() == {'FINISHED'}
assert ops.anim.keys_select(frame_start="5", frame_end="10", layers=str(lay.id), path="position") == {'FINISHED'}
rot = [k['selected'] for k in lay.keyframes('rotation')]
steps = wm.undo_history()[1]
r = ops.anim.keys_scale(factor="1")
assert r == {'CANCELLED'} and wm.undo_history()[1] == steps, ("scale by 1", r, steps, wm.undo_history()[1])
assert [k['selected'] for k in lay.keyframes('rotation')] == rot, ("scale by 1 picked keys", rot)

# --- Save Incremental keeps the file's own digit count
folder = tempfile.mkdtemp(prefix="oanim_incremental_")
try:
    assert ops.wm.read_homefile() == {'FINISHED'}
    assert ops.wm.save_as_mainfile(filepath=os.path.join(folder, "take_09.oanim")) == {'FINISHED'}
    assert ops.wm.save_incremental() == {'FINISHED'}
    assert "take_10.oanim" in os.listdir(folder), os.listdir(folder)
    assert ops.wm.save_as_mainfile(filepath=os.path.join(folder, "scene.oanim")) == {'FINISHED'}
    assert ops.wm.save_incremental() == {'FINISHED'}
    assert "scene_001.oanim" in os.listdir(folder), os.listdir(folder)
finally:
    ops.wm.read_homefile()
    shutil.rmtree(folder, ignore_errors=True)

# --- A reference of a switch shows its original's picks
assert ops.wm.read_homefile() == {'FINISHED'}
doc.auto_key = True
assert ops.layer.new_switch() == {'FINISHED'}
sw = L.active
sw.name = "Sw"
for n in ("A", "B"):
    L.active = sw
    ops.layer.new()
    k = L.active
    k.name = n
    k.add_curve([(0, 0), (1, 0), (1, 1)], closed=True, fill=True)
    assert ops.layer.move_to_group(group=str(sw.id)) == {'FINISHED'}
L.active = sw
doc.frame_current = 8
assert ops.layer.switch_set(layer="Sw", child="B") == {'FINISHED'}
doc.frame_current = 0
for o in L.all():
    o.selected = o.id == sw.id
L.active = sw
assert ops.layer.make_reference() == {'FINISHED'}
ref = L.active
assert ref.reference_source is not None and ref.type == "SWITCH"
for f, want in ((0, "A"), (9, "B")):
    doc.frame_current = f
    assert sw.switch_active == want and ref.switch_active == want, (f, sw.switch_active, ref.switch_active)

print("test_sweep_key_guards: all passed")
