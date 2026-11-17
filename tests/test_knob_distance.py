"""A 2 Axis Controller's knob is keyed as far as it is from its rest point, as any bone's Transform: its frames times its
Frame Size (before, its keys were frames, so the Bone tab's Knob and a point's Transform moved by different amounts for
the same number). G moves the knob's keys by as much as the mouse; a new Frame Size scales its keys so they play the same
frames; and a file from before (format 8, keys in frames) opens with its keys turned into distances, playing as it did.

Run with:  OpenAnimate --background --python tests/test_knob_distance.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active
KNOB = 'bones["eye"].position'


def bone(name="eye"):
    return next(b for b in rig.bones if b["name"] == name)


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def close(a, b, eps=1e-4):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def key_at(frame):
    return next(tuple(k["value"]) for k in rig.keyframes(KNOB) if k["frame"] == frame)


def playing():
    return next(a["frame"] for a in rig.actions if a["name"] == "eye_r")


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
size = bone()["controller_frame_size"]
assert size > 0 and abs(size - 1.0) > 1e-3, size

# --- Keyed as far as it is: 20 frames out is 20 Frame Sizes ----------------------------------------------------------
go(10)
rig.bone_set("eye", knob=(20.0, 0.0))
go(10)
assert close(bone()["knob"], (20.0, 0.0)), bone()["knob"]
assert close(key_at(10), (20.0 * size, 0.0)), (key_at(10), size)
assert close(playing(), 20.0, 1e-2), playing()

# G moves the key by as much as the mouse moved, the same as a point or a bone (the panel's numbers match).
rig.select_bone("eye")
assert ops.armature.translate(move_x="0.05", move_y="0", posing="1") == {'FINISHED'}
go(10)
assert close(key_at(10), (20.0 * size + 0.05, 0.0)), (key_at(10), size)
assert close(bone()["knob"], (20.0 + 0.05 / size, 0.0)), bone()["knob"]
# Back to 20 frames out (Python's knob= joined G's undo step, so it is set again).
rig.bone_set("eye", knob=(20.0, 0.0))
go(10)
assert close(key_at(10), (20.0 * size, 0.0)), key_at(10)

# --- A new Frame Size keeps what plays: its keys scale with it ---------------------------------------------------------
rig.bone_set("eye", controller_frame_size=size * 2.0)
go(10)
assert close(bone()["knob"], (20.0, 0.0)), ("the same frames", bone()["knob"])
assert close(key_at(10), (40.0 * size, 0.0)), ("twice as far", key_at(10))
assert close(playing(), 20.0, 1e-2), playing()
rig.bone_set("eye", controller_frame_size=size)
go(10)
assert close(key_at(10), (20.0 * size, 0.0)), key_at(10)

# --- Saved as distance; a file from before (keys in frames) opens playing as it did ------------------------------------
folder = tempfile.mkdtemp(prefix="oanim_knob_")
path = os.path.join(folder, "knob.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    entries = {n: z.read(n) for n in z.namelist()}
root = json.loads(entries["document.json"])
assert root["version"] >= 9, root["version"]


def walk(j):
    if isinstance(j, dict):
        if j.get("name") == "eye" and "position_keys" in j:
            yield j
        for v in j.values():
            yield from walk(v)
    elif isinstance(j, list):
        for v in j:
            yield from walk(v)


eye = next(walk(root))
saved = {k["frame"]: k["value"] for k in eye["position_keys"]}
assert close(saved[10], [20.0 * size, 0.0]), ("saved as distance", saved)

# As a format 8 file had it: the knob's keys in frames.
root["version"] = 8
for k in eye["position_keys"]:
    k["value"] = [v / size for v in k["value"]]
for keys in eye.get("position_keys_actions", {}).values():
    for k in keys:
        k["value"] = [v / size for v in k["value"]]
entries["document.json"] = json.dumps(root).encode()
old = os.path.join(folder, "old.oanim")
with zipfile.ZipFile(old, "w") as z:
    for n, data in entries.items():
        z.writestr(n, data)
assert ops.wm.open_mainfile(filepath=old) == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
rig = next(l for l in layers.all() if l.bones)
go(10)
assert close(bone()["knob"], (20.0, 0.0)), ("plays the frames it did", bone()["knob"])
assert close(key_at(10), (20.0 * size, 0.0)), ("its keys are distances now", key_at(10))
assert close(playing(), 20.0, 1e-2), playing()

print("knob distance ok")
