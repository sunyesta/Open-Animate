"""A 2 Axis Controller's knob keys are distances (frames times its box's Frame Size): carried from one knob to
another, or kept while a size changes, they play the same frames. Paste Pose Flipped, Bone Symmetrize, Layer Symmetrize
(Keep Partner's), a side action mirrored, poses saved and copied (they keep the size they were made at) and older files'
drivers reading a knob (which read frames) each put a knob on the frames it had: before, the distance came over as it
was, so a knob with another box size went to other frames.

Run with:  OpenAnimate --background --python tests/test_knob_distance_copies.py
"""

import json
import os
import tempfile
import zipfile

import _oanim
import oanim

ops = oanim.ops
OUT = tempfile.mkdtemp(prefix="oanim_knobs_")


def _print(*args):
    print(*args)

import oanim
ops = oanim.ops


def go(frame):
    d = oanim.data.document
    d.frame_current = frame + 1
    d.frame_current = frame


def rig():
    return next(l for l in oanim.data.layers.all() if l.bones and l.name == RIG_NAME[0])


RIG_NAME = [""]


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def action_frame(name):
    return next(a["frame"] for a in rig().actions if a["name"] == name)


def build(size_l=0.01, size_r=0.02, sides=("UP",)):
    ops.wm.read_homefile()
    doc = oanim.data.document
    doc.auto_key = True
    doc.frame_current = 0
    ops.layer.new_bone()
    r = oanim.data.layers.active
    RIG_NAME[0] = r.name
    for name, x in (("Eye_L", 0.5), ("Eye_R", -0.5)):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="0.1", parent="") == {'FINISHED'}
    for name, x in (("Eye_L", 0.5), ("Eye_R", -0.5)):
        oanim.data.layers.active = rig()
        ops.layer.new()
        pupil = oanim.data.layers.active
        pupil.name = "Pupil" + name[-2:]
        ops.layer.move_to_group(group=str(rig().id))
        pupil.add_curve([(x, 0.0), (x + 0.1, 0.0)])
        assert ops.layer.parent_bone_set(bone=name) == {'FINISHED'}
        for side in sides:
            act = name + " " + side.capitalize()
            oanim.data.layers.active = rig()
            assert ops.anim.action_new(name=act) == {'FINISHED'}, act
            doc.frame_current = 40
            oanim.data.layers.active = pupil
            pupil.set_point(1, (x + 0.1, 0.3 if side == "UP" else -0.3 if side == "DOWN" else 0.0))
            go(40)
            doc.action = ""
            go(0)
    oanim.data.layers.active = rig()
    for name, size in (("Eye_L", size_l), ("Eye_R", size_r)):
        ops.armature.select_none()
        rig().select_bone(name)
        assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
        for side in sides:
            assert ops.armature.controller_side(side=side, action=name + " " + side.capitalize()) == {'FINISHED'}
        rig().bone_set(name, contain_knob=False)
        if size:
            rig().bone_set(name, controller_frame_size=size)
    ops.armature.select_none()
    go(0)
    return rig()


# --- Paste Pose Flipped from a knob onto its other side's, whose box has another Frame Size: the same frames ----------
r = build(size_l=0.01, size_r=0.02)
go(10)
r.bone_set("Eye_L", knob=(0.0, 20.0))
go(10)
assert abs(bone("Eye_L")["knob"][1] - 20.0) < 1e-3, bone("Eye_L")["knob"]
assert abs(action_frame("Eye_L Up") - 20.0) < 1e-2, action_frame("Eye_L Up")
ops.armature.select_none()
rig().select_bone("Eye_L")
assert ops.pose.copy() == {'FINISHED'}
assert ops.pose.paste_flipped() == {'FINISHED'}
go(10)
got = bone("Eye_R")["knob"]
_print("Eye_R knob after flipped paste", got, "Eye_R Up frame", action_frame("Eye_R Up"))
assert abs(got[1] - 20.0) < 1e-2 and abs(action_frame("Eye_R Up") - 20.0) < 1e-2, \
    f"Eye_L's knob 20 frames up, flipped onto Eye_R (Frame Size 0.02 vs 0.01): expected 20 frames, got {got[1]:.3f} (Eye_R Up plays frame {action_frame('Eye_R Up'):.3f})"
_print("flip ok")


# --- Bone Symmetrize onto a knob already there with another Frame Size: its keys play the same frames -----------------
r = build(size_l=0.01, size_r=0.02)
go(10)
r.bone_set("Eye_R", knob=(0.0, 20.0))
go(10)
before = (bone("Eye_R")["knob"], action_frame("Eye_R Up"))
assert abs(before[1] - 20.0) < 1e-2, before
go(0)
ops.armature.select_none()
rig().select_bone("Eye_L")
assert ops.armature.symmetrize(action_bone_actions="0") == {'FINISHED'}
go(10)
after = (bone("Eye_R")["knob"], action_frame("Eye_R Up"), bone("Eye_R")["controller_frame_size"])
_print("before", before, "after", after)
assert abs(after[1] - 20.0) < 1e-2, \
    f"Eye_R keyed 20 frames up (Frame Size 0.02), Symmetrize from Eye_L (0.01) keeping Eye_R's keys: expected Eye_R Up at frame 20, got {after[1]:.3f} (knob {after[0]}, size {after[2]})"
_print("symmetrize ok")


# --- Layer Symmetrize, Keep Partner's: the partner knob's kept keys play the same frames at the new size --------------
L = lambda: oanim.data.layers
find = lambda n: next((l for l in L().all() if l.name == n), None)


def at(d, f):
    d.frame_current = f + 1
    d.frame_current = f


assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
d = oanim.data.document
d.auto_key = True
d.frame_current = 0
ops.layer.new_group()
grp = L().active
grp.name = "Eye_L"
ops.layer.new_bone()
eye_rig = L().active
eye_rig.name = "EyeRig_L"
assert ops.armature.bone_add(name="knob", head_x="0.5", head_y="0", tail_x="0.5", tail_y="0.1", parent="") == {'FINISHED'}
assert ops.layer.move_to_group(group=str(grp.id)) == {'FINISHED'}
ops.layer.new()
pupil = L().active
pupil.name = "Pupil_L"
pupil.add_curve([(0.5, 0.0), (0.6, 0.0)])
assert ops.layer.move_to_group(group=str(find("EyeRig_L").id)) == {'FINISHED'}
assert ops.layer.parent_bone_set(bone="knob") == {'FINISHED'}
L().active = find("EyeRig_L")
assert ops.anim.action_new(name="look up") == {'FINISHED'}
d.frame_current = 40
L().active = find("Pupil_L")
find("Pupil_L").set_point(1, (0.6, 0.3))
at(d, 40)
d.action = ""
at(d, 0)
L().active = find("EyeRig_L")
eye_rig = find("EyeRig_L")
eye_rig.select_bone("knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
assert ops.armature.controller_side(side="UP", action="look up") == {'FINISHED'}
eye_rig.bone_set("knob", contain_knob=False)
eye_rig.bone_set("knob", controller_frame_size=0.01)
L().active = grp
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE") == {'FINISHED'}
rig_r = next(l for l in find("Eye_R").children if l.type == 'BONE')
kb = lambda l: next(b for b in l.bones if b["name"] == "knob")
_print("partner size", kb(rig_r)["controller_frame_size"], kb(rig_r)["controller_actions"])
L().active = rig_r
rig_r.bone_set("knob", controller_frame_size=0.02)
at(d, 10)
rig_r.bone_set("knob", knob=(0.0, 20.0))
at(d, 10)
upr = kb(rig_r)["controller_actions"]["UP"]
fr = lambda l, n: next(a["frame"] for a in l.actions if a["name"] == n)
before = fr(rig_r, upr)
assert abs(before - 20.0) < 1e-2, before
at(d, 0)
L().active = grp
assert ops.layer.symmetrize(direction="POSITIVE_TO_NEGATIVE", animation="KEEP_PARTNER") == {'FINISHED'}
rig_r = next(l for l in find("Eye_R").children if l.type == 'BONE')
at(d, 10)
upr = kb(rig_r)["controller_actions"]["UP"]
after = fr(rig_r, upr)
_print("before", before, "after", after, "size", kb(rig_r)["controller_frame_size"], "knob", kb(rig_r)["knob"])
assert abs(after - 20.0) < 1e-2, \
    f"partner knob keyed 20 frames up at Frame Size 0.02; Layer Symmetrize KEEP_PARTNER: expected its Up action at frame 20, got {after:.3f} (size now {kb(rig_r)['controller_frame_size']})"
_print("ok")


# --- A knob's side action mirrored onto the other knob (another size): its timing on the same frames ------------------
r = build(size_l=0.01, size_r=0.02)
doc = oanim.data.document
# Eye_L's timing: in its Up action, 10 frames up by frame 20 (an ease-in).
assert ops.anim.action_set(name="Eye_L Up") == {'FINISHED'}
go(20)
rig().bone_set("Eye_L", knob=(0.0, 10.0))
go(20)
_print("Eye_L timing keys", [(k["frame"], k["value"]) for k in rig().keyframes('bones["Eye_L"].position')])
assert ops.anim.action_set(name="") == {'FINISHED'}
go(0)
def frame_for(knob, y):
    go(5)
    rig().bone_set(knob, knob=(0.0, y))
    go(5)
    f = action_frame(knob + " Up")
    return f
fl = frame_for("Eye_L", 5.0); bl = bone("Eye_L")["controller_box"]
_print("Eye_L knob 5 up plays Eye_L Up frame", fl)
go(0)
ops.armature.select_none()
rig().select_bone("Eye_L")
assert ops.armature.symmetrize(positions="0", action_bone_actions="1") == {'FINISHED'}
_print("sizes", bone("Eye_L")["controller_frame_size"], bone("Eye_R")["controller_frame_size"])
doc.action = "Eye_R Up"
_print("Eye_R timing keys", [(k["frame"], k["value"]) for k in rig().keyframes('bones["Eye_R"].position')])
doc.action = ""
fr = frame_for("Eye_R", 5.0); br = bone("Eye_R")["controller_box"]; _print("boxes", bl, br)
_print("Eye_R knob 5 up plays Eye_R Up frame", fr)
assert abs(fr - fl) < 1e-2 and abs(bl[1][1] - br[1][1]) < 1e-3, f"boxes {bl} vs {br}; Eye_L Up mirrored into Eye_R Up (sizes 0.01 / 0.02): Eye_R's knob 5 frames up should play its Up at frame {fl:.3f} as Eye_L's does, got {fr:.3f}"
_print("ok")


# --- A pose saved or copied, applied after the knob's Frame Size changed: the same frames -----------------------------
r = build(size_l=0.01, size_r=0.01)
go(10)
rig().bone_set("Eye_L", knob=(0.0, 20.0))
go(10)
ops.armature.select_none()
rig().select_bone("Eye_L")
assert ops.poselib.pose_new(name="Up20", new_collection="Eyes") == {'FINISHED'}
assert ops.pose.copy() == {'FINISHED'}
pid = next(p for p in _oanim.poses() if p["name"] == "Up20")["id"]
rig().bone_set("Eye_L", controller_frame_size=0.02)
go(10)
assert abs(bone("Eye_L")["knob"][1] - 20.0) < 1e-3, bone("Eye_L")["knob"]
go(25)
assert ops.poselib.apply(pose=str(pid)) == {'FINISHED'}
go(25)
lib = bone("Eye_L")["knob"][1]
go(30)
assert ops.pose.paste() == {'FINISHED'}
go(30)
clip = bone("Eye_L")["knob"][1]
_print("pose library", lib, "clipboard", clip)
assert abs(lib - 20.0) < 1e-2 and abs(clip - 20.0) < 1e-2, \
    f"a pose saved/copied with the knob 20 frames up, applied after Frame Size 0.01 -> 0.02: expected 20 frames, got {lib:.3f} (library), {clip:.3f} (paste)"


# --- A format 8 file's driver reading a knob (its frames then) reads the same numbers once opened ---------------------
r = build(size_l=0.01, size_r=0.02)
other = next(l for l in oanim.data.layers.all() if l.name == "Layer 1")
v = json.dumps([{"name": "k", "layer": rig().id, "path": 'bones["Eye_L"].position', "component": 1}])
assert ops.anim.driver_add(layer=str(other.id), path="rotation", vars=v, expression="k") == {'FINISHED'}
go(10)
rig().bone_set("Eye_L", knob=(0.0, 20.0))
go(10)
p9 = os.path.join(OUT, "driver_v9.oanim")
assert ops.wm.save_as_mainfile(filepath=p9) == {'FINISHED'}
with zipfile.ZipFile(p9) as z:
    entries = {n: z.read(n) for n in z.namelist()}
root = json.loads(entries["document.json"])
root["version"] = 8
def walk(j):
    if isinstance(j, dict):
        if j.get("type") == "CONTROLLER_2D":
            s = j["controller_frame_size"]
            for k in j.get("position_keys", []):
                k["value"] = [x / s for x in k["value"]]
            for keys in j.get("position_keys_actions", {}).values():
                for k in keys:
                    k["value"] = [x / s for x in k["value"]]
        for x in j.values(): walk(x)
    elif isinstance(j, list):
        for x in j: walk(x)
walk(root["document"])
entries["document.json"] = json.dumps(root).encode()
p8 = os.path.join(OUT, "driver_v8.oanim")
with zipfile.ZipFile(p8, "w") as z:
    for n, d in entries.items(): z.writestr(n, d)
assert ops.wm.open_mainfile(filepath=p8) == {'FINISHED'}
go(10)
other = next(l for l in oanim.data.layers.all() if l.name == "Layer 1")
_print("knob", bone("Eye_L")["knob"], "driven", other.rotation)
assert abs(bone("Eye_L")["knob"][1] - 20.0) < 1e-3
assert abs(other.rotation - 20.0) < 1e-2, \
    f"format 8 file: a driver reading Eye_L's knob (20 frames up) gave 20 there; opened now it gives {other.rotation:.4f}"

print("knob distance copies ok")
