"""Frames held within the last frame there is (1048574), and settings set as they already are making no undo step
(from a bug sweep: Insert Keys in Row took frame=INT_MAX as is, and Next Frame from there wrapped to INT_MIN; a file
opened on such a frame; Set Action and Reference Settings set as they were pushed a step). Each section starts from a
new file.

Run with:  OpenAnimate --background --python tests/test_frame_last_noop.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, layers = oanim.ops, oanim.data.layers
LAST = 1048574


def doc():
    return oanim.data.document


def saved():
    p = os.path.join(tempfile.mkdtemp(), "c.oanim")
    assert ops.wm.save_copy(filepath=p) == {'FINISHED'}
    return json.loads(zipfile.ZipFile(p).read("document.json"))["document"]


def step():
    return oanim.wm.undo_history()[1]


def box():
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    doc().auto_key = True
    ops.layer.new()
    b = layers.active
    b.add_curve([(0.0, 0.0), (0.5, 0.0)])
    assert ops.anim.motion_path_move(frame="10", x="2", y="0", layer=str(b.id)) == {'FINISHED'}
    return b


def frames(b):
    return [k["frame"] for k in b.keyframes("position")]


# --- Insert Keys in Row past the last frame keys the last frame, and a move past it keeps the key there ------------
b = box()
assert ops.anim.keys_insert(frame="2147483647", layers=str(b.id)) == {'FINISHED'}
assert frames(b) == [0, 10, LAST] and doc().frame_current == LAST, (frames(b), doc().frame_current)
ops.anim.keys_select(frame_start=str(LAST), frame_end=str(LAST))
ops.anim.keys_offset(frames="5")
assert frames(b) == [0, 10, LAST], ("the key stays on the last frame", frames(b))

# --- Next Frame on the last frame stays there ---------------------------------------------------------------------
assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
doc().frame_current = LAST
ops.screen.frame_offset_forward()
assert doc().frame_current == LAST, doc().frame_current
doc().frame_current = 5
ops.screen.frame_offset_forward()
assert doc().frame_current == 6, doc().frame_current

# --- A file saved on a frame past the last opens on the last ------------------------------------------------------
d = tempfile.mkdtemp()
a, b = os.path.join(d, "a.oanim"), os.path.join(d, "b.oanim")
assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
assert ops.wm.save_as_mainfile(filepath=a) == {'FINISHED'}
with zipfile.ZipFile(a) as zi, zipfile.ZipFile(b, "w") as zo:
    for it in zi.infolist():
        data = zi.read(it.filename)
        if it.filename == "document.json":
            j = json.loads(data)
            j["document"]["frame_current"] = 2147483647
            j["document"]["frame_end"] = 2147483647
            data = json.dumps(j).encode()
        zo.writestr(it, data)
assert ops.wm.open_mainfile(filepath=b, confirmed="1") == {'FINISHED'}
assert doc().frame_current == LAST and doc().frame_end == LAST, (doc().frame_current, doc().frame_end)
ops.screen.frame_offset_forward()
assert doc().frame_current == LAST, doc().frame_current

# --- Set Action as it already is: CANCELLED, no undo step, nothing saved; a real change still goes in --------------
for args in (dict(mute="0"), dict(loop="AUTO"), dict(frame="0"), dict(mute="1")):
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    doc().auto_key = True
    ops.layer.new_bone()
    rig = layers.active
    ops.armature.bone_add(name="b", head_x="0", head_y="0", tail_x="1", tail_y="0")
    ops.layer.new()
    face = layers.active
    face.add_curve([(0.0, 0.0), (1.0, 0.0)])
    ops.layer.move_to_group(group=str(rig.id))
    layers.active = rig
    assert ops.anim.action_new(name="wave") == {'FINISHED'}
    doc().frame_current = 10
    face.set_point(0, (1.0, 1.0))
    doc().frame_current = 11
    ops.anim.action_set(name="")
    doc().frame_current = 30
    layers.active = rig
    before, s0 = saved(), step()
    r = ops.anim.action_play_set(name="wave", **args)
    after, s1 = saved(), step()
    if args == dict(mute="1"):
        assert r == {'FINISHED'} and s1 != s0 and before != after, ("a real change", r)
    else:
        assert r == {'CANCELLED'} and s1 == s0 and before == after, (args, r, s1 - s0)

# --- Reference Settings as they already are, on a reopened file: CANCELLED and no undo step -------------------------
for args in ({}, dict(match_original="1"), dict(edit_points="0"), dict(follow_animation="1"), dict(edit_points="1")):
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    ops.layer.new()
    src = layers.active
    src.add_curve([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
    assert ops.layer.make_reference() == {'FINISHED'}
    p = os.path.join(tempfile.mkdtemp(), "base.oanim")
    assert ops.wm.save_as_mainfile(filepath=p) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=p, confirmed="1") == {'FINISHED'}
    layers.active = next(l for l in layers.all() if l.reference_source)
    s0 = step()
    r = ops.layer.reference_set(**args)
    if args == dict(edit_points="1"):
        assert r == {'FINISHED'} and step() != s0 and layers.active.reference["edit_points"], ("a real change", r)
    else:
        assert r == {'CANCELLED'} and step() == s0, (args, r)

print("Frame last and no-op tests passed")
