"""Timeline and file edges a sweep found: Paste Timeline keeps frame 0's keys as they are (their interpolation and path
handles) and pastes only onto the layers it came from or ones of the same name; keys never go past the last frame there
is (One Frame More by a huge amount, Paste Keys on the last frame); Save Incremental counts a number of any length; and
moving points by nothing on a posed frame changes nothing and keys nothing.

Run with:  OpenAnimate --background --python tests/test_sweep_timeline_guards.py
"""

import glob
import os
import tempfile

import oanim

ops, layers = oanim.ops, oanim.data.layers
LAST = 1048574
P = 'bones["arm"].angle'


def doc():
    return oanim.data.document


def go(f):
    doc().frame_current = f + 1
    doc().frame_current = f


def arm_rig():
    """A bone layer with bone arm turning on 10 and 20 (auto-key on)."""
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_key = True
    doc().frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
    setup = next(b for b in rig.bones if b["name"] == "arm")["setup_angle"]
    for f, a in ((10, 1.0), (20, -0.5)):
        doc().frame_current = f
        rig.bone_set("arm", angle=setup + a)
        go(f)
    return rig


def arm_angle(rig):
    return next(b for b in rig.bones if b["name"] == "arm")["angle"]


def box_layer(frames):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_key = True
    doc().path_show_all = True
    ops.layer.new()
    box = layers.active
    box.add_curve([(0.0, 0.0), (0.5, 0.0)])
    for frame, x in frames:
        assert ops.anim.motion_path_move(frame=str(frame), x=str(x), y="0", layer=str(box.id)) == {'FINISHED'}
    return box


# --- Paste Timeline onto itself: frame 0's key keeps its interpolation (Step), so frame 5 shows what it did ---------------
rig = arm_rig()
rig.keyframe_set(P, 0, interp="STEP")
assert [k["frame"] for k in rig.keyframes(P)] == [0, 10, 20] and rig.keyframes(P)[0]["interp"] == "STEP"
go(5)
before = arm_angle(rig)
assert ops.anim.timeline_copy() == {'FINISHED'}
assert ops.anim.timeline_paste() == {'FINISHED'}
assert rig.keyframes(P)[0]["interp"] == "STEP", rig.keyframes(P)[0]
go(5)
assert abs(arm_angle(rig) - before) < 1e-6, (before, arm_angle(rig))

# --- Paste Timeline onto itself: frame 0's dragged path handle stays, so the path out of it stays ------------------------
box = box_layer(((10, 2.0), (20, 4.0)))
doc().motion_paths = True
assert ops.anim.motion_path_handle(frame="0", side="OUT", x="0", y="1", layer=str(box.id)) == {'FINISHED'}
k0 = next(k for k in box.keyframes("position") if k["frame"] == 0)
assert k0["path_handles"] != "AUTO", k0
go(5)
before = (box.location_x, box.location_y)
assert ops.anim.timeline_copy() == {'FINISHED'}
assert ops.anim.timeline_paste() == {'FINISHED'}
k1 = next(k for k in box.keyframes("position") if k["frame"] == 0)
assert k1["path_handles"] == k0["path_handles"], (k0, k1)
go(5)
assert abs(box.location_x - before[0]) < 1e-5 and abs(box.location_y - before[1]) < 1e-5, (before, box.location_x,
                                                                                             box.location_y)

# --- Paste Timeline into another bone layer's action, none of the copied layers there: CANCELLED, nothing changed --------
assert ops.wm.read_homefile() == {'FINISHED'}
doc().auto_key = True
assert ops.layer.new_bone() == {'FINISHED'}
a = layers.active
assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
b = layers.active
assert ops.armature.bone_add(name="arm", head_x="3", head_y="0", tail_x="4", tail_y="0") == {'FINISHED'}
assert a.name != b.name
layers.active = a
assert ops.anim.action_new(name="wave") == {'FINISHED'}
doc().frame_current = 10
a.bone_set("arm", angle=next(x for x in a.bones if x["name"] == "arm")["setup_angle"] + 0.5)
go(10)
assert ops.anim.timeline_copy() == {'FINISHED'}
assert ops.anim.action_set(name="") in ({'FINISHED'}, {'CANCELLED'})
go(0)
layers.active = b
assert ops.anim.action_new(name="kick") == {'FINISHED'}
doc().frame_current = 8
b.bone_set("arm", angle=next(x for x in b.bones if x["name"] == "arm")["setup_angle"] - 0.3)
go(8)
kick = [k["frame"] for k in b.keyframes(P)]
assert ops.anim.timeline_paste() == {'CANCELLED'}
assert [k["frame"] for k in b.keyframes(P)] == kick == [0, 8], kick

# --- One Frame More by a huge amount, Paste Keys on the last frame: no key goes past the last frame there is ------------
for amount in ("2000000", "2147483647"):
    box = box_layer(((10, 2.0), (20, 4.0), (30, 6.0)))
    doc().frame_current = 15
    assert ops.anim.span_frames_add(amount=amount) == {'FINISHED'}
    frames = [k["frame"] for k in box.keyframes("position")]
    assert frames == sorted(frames) and max(frames) <= LAST and min(frames) >= 0, (amount, frames)
    assert frames[-1] == LAST and frames[-1] - frames[-2] == 10, ("the keys after stop there together", frames)
box = box_layer(((10, 2.0), (20, 4.0)))
ops.anim.keys_select_all()
assert ops.anim.keys_copy() == {'FINISHED'}
doc().frame_current = LAST
assert ops.anim.keys_paste() == {'FINISHED'}
frames = [k["frame"] for k in box.keyframes("position")]
assert max(frames) == LAST and LAST - 20 in frames and LAST - 10 in frames, ("pasted ending on the last frame", frames)

# --- Save Incremental on a name ending in a number too long for a long long: it counts on -----------------------------
here = tempfile.mkdtemp()
assert ops.wm.read_homefile() == {'FINISHED'}
for stem in ("shot_9223372036854775807", "shot_99999999999999999999", "take_09", "scene"):
    assert ops.wm.save_as_mainfile(filepath=os.path.join(here, stem + ".oanim")) == {'FINISHED'}
    assert ops.wm.save_incremental() == {'FINISHED'}
names = sorted(os.path.basename(f) for f in glob.glob(os.path.join(here, "*.oanim")))
for want in ("shot_9223372036854775808.oanim", "shot_100000000000000000000.oanim", "take_10.oanim", "scene_001.oanim"):
    assert want in names, (want, names)
assert not any("-" in n for n in names), names

# --- Moving points by nothing on a posed frame: nothing moves, no handle keyed ----------------------------------------
assert ops.wm.read_homefile() == {'FINISHED'}
doc().auto_key = True
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
assert ops.armature.bone_add(name="b", head_x="0", head_y="0", tail_x="2", tail_y="0") == {'FINISHED'}
ops.layer.new()
face = layers.active
face.add_curve([(0.2, 0.3), (1.0, 0.8), (1.8, 0.2)])
face.move_handle(0, 1, "OUT", (1.4, 1.1))
ops.layer.move_to_group(group=str(rig.id))
layers.active = face
ops.mesh.select_all()
assert ops.weight.automatic() == {'FINISHED'}
layers.active = rig
doc().frame_current = 10
rig.bone_set("b", angle=next(x for x in rig.bones if x["name"] == "b")["setup_angle"] + 0.7)
go(10)
face = next(l for l in layers.all() if l.id == face.id)
layers.active = face
ops.mesh.select_all()
n = len(face.curve_handles(0))


def handle_keys():
    return sum(len(face.keyframes(f"curves[0].points[{i}].{s}")) for i in range(n) for s in ("handle_in", "handle_out"))


keyed = handle_keys()
stored = [face.curve_handles(0), [tuple(p) for p in face.points]]
for call in (lambda: ops.mesh.translate(move_x="0", move_y="0"), lambda: ops.mesh.translate(),
             lambda: ops.mesh.rotate(angle="0"), lambda: ops.mesh.resize(scale_x="1", scale_y="1")):
    assert call() == {'FINISHED'}  # as Blender's G let go where it began: a step, nothing changed
    go(10)
    assert handle_keys() == keyed, ("handles keyed by a move by nothing", keyed, handle_keys())
    assert [face.curve_handles(0), [tuple(p) for p in face.points]] == stored, "a move by nothing moved something"

print("Timeline guards tests passed")
