"""IK Ends and IK Bases: a pair of legs hanging from a pelvis (an IK Base), each foot an IK End at the ankle (a foot is
short, so its point is its head). Pinned to the scene with U, a foot stays where the setup frame has it while the pelvis
lowers, the leg bending to reach and the foot keeping its angle; between two keys of the leg a pinned ankle goes
straight from where the key before has it to where the key after has it, eased as the keys are; pinned to a bone it
rides that bone. The chain runs only up to the IK Base. Pinned To is keyed. Adding on a posed frame, twice, or on a
root is refused, as is pinning to a bone the chain moves or one already following this end. Everything comes back
from a save.

Run with:  OpenAnimate --background --python tests/test_ik_end.py
"""

import math
import pathlib
import tempfile

import _oanim
import oanim

ops = oanim.ops
doc, layers = oanim.data.document, oanim.data.layers
doc.auto_freeze_keys = False
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active


def add(name, head, tail, parent=""):
    assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                 tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
    ops.armature.select_none()


def bones():
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def way(b):
    return math.atan2(b["tail"][1] - b["head"][1], b["tail"][0] - b["head"][0])


def turn(a, b):
    return abs(math.remainder(a - b, 2 * math.pi))


def end_of(name):
    return next(c for c in rig.bone_constraints(name) if c["type"] == "IK_END")


def end_index(name):
    return next(i for i, c in enumerate(rig.bone_constraints(name)) if c["type"] == "IK_END")


add("Ground", (0, -3.0), (0.5, -3.0))
add("Root", (0, -2.5), (0, -2.3))
add("Pelvis", (0, 0), (0, 0.4), "Root")
for tag, s in (("_R", -1), ("_L", 1)):
    add("Thigh" + tag, (0.15 * s, 0), (0.25 * s, -1.0), "Pelvis")
    add("Calf" + tag, (0.25 * s, -1.0), (0.2 * s, -2.0), "Thigh" + tag)
    add("Foot" + tag, (0.2 * s, -2.0), (0.5 * s, -2.05), "Calf" + tag)

# --- Adding: refused on a posed frame, on a root, twice; a foot's point is its head.
doc.frame_current = 3
assert ops.armature.ik_end_add(bone="Foot_R") == {'CANCELLED'}, "an IK End is added on frame 0"
doc.frame_current = 0
assert ops.armature.ik_end_add(bone="Root") == {'CANCELLED'}, "a root has nothing above it to bend"
assert ops.armature.ik_base_add(bone="Pelvis") == {'FINISHED'}
for tag in ("_R", "_L"):
    assert ops.armature.ik_end_add(bone="Foot" + tag) == {'FINISHED'}
assert ops.armature.ik_end_add(bone="Foot_R") == {'CANCELLED'}, "one IK End a bone"
assert ops.armature.ik_base_add(bone="Foot_R") == {'CANCELLED'}, "an IK End's bone takes no IK Base"
assert end_of("Foot_R")["ik_head"], "a foot (short) puts its point at its head: the ankle"
assert end_of("Foot_R")["keep_angle"] and end_of("Foot_R")["soft"]
assert end_of("Foot_R")["pin"] == ""
assert rig.bone_constraints("Pelvis")[0]["type"] == "IK_BASE" and not rig.bone_constraints("Pelvis")[0]["ik_head"]
assert list(_oanim.layer_bone_ik_chain(rig.id, "Foot_R", "IK_END")) == ["Calf_R", "Thigh_R"], \
    "the chain stops at the IK Base"
rest = bones()

# --- Pinned to the scene: the ankle stays where the setup frame has it while the pelvis lowers.
rig.select_bone("Foot_R")
assert ops.armature.ik_pin_toggle() == {'FINISHED'}
assert end_of("Foot_R")["pin"] == "SCENE"
doc.auto_key = True
doc.frame_current = 10
p = rest["Pelvis"]["position"]
rig.bone_set("Pelvis", position=(p[0] - 0.4, p[1] + 0.1))
for f in (4, 10, 14):
    doc.frame_current = f
    b = bones()
    assert dist(b["Pelvis"]["head"], rest["Pelvis"]["head"]) > 0.05 or f < 1, (f, "the pelvis moved")
    miss = dist(b["Calf_R"]["tail"], rest["Calf_R"]["tail"])
    assert miss < 1e-4, (f, "a pinned ankle stays put", miss)
    assert turn(way(b["Foot_R"]), way(rest["Foot_R"])) < 1e-4, (f, "Keep Angle: the foot keeps its angle")
    assert turn(way(b["Pelvis"]), way(rest["Pelvis"])) < 1e-6, (f, "the chain stops at the IK Base")
    left = dist(b["Calf_L"]["tail"], rest["Calf_L"]["tail"])
    assert left > 0.05, (f, "the unpinned foot goes with the pelvis", left)

# --- Keep Angle off: the foot turns with the calf.
rig.bone_constraint_set("Foot_R", end_index("Foot_R"), keep_angle=False)
doc.frame_current = 10
b = bones()
assert turn(way(b["Foot_R"]), way(rest["Foot_R"])) > 1e-3, "without Keep Angle the foot turns with the calf"
rig.bone_constraint_set("Foot_R", end_index("Foot_R"), keep_angle=True)

# --- Between keys of the leg: straight from the key before's place to the key after's. Auto-key keys the thigh alone
# on frame 20 (the pelvis's key is no key of the leg's).
doc.frame_current = 20
rig.bone_set("Thigh_R", angle=rest["Thigh_R"]["angle"] + 0.4)
doc.frame_current = 0
doc.frame_current = 20
at20 = bones()["Calf_R"]["tail"]
at0 = rest["Calf_R"]["tail"]
assert dist(at20, at0) > 0.1, "the key at 20 puts the ankle somewhere else"
for f in (4, 10, 16):
    doc.frame_current = f
    u = f / 20
    e = u * u * (3 - 2 * u)
    want = (at0[0] + (at20[0] - at0[0]) * e, at0[1] + (at20[1] - at0[1]) * e)
    got = bones()["Calf_R"]["tail"]
    assert dist(got, want) < 1e-3, (f, "the ankle goes straight between the keys' places, eased", got, want)
doc.frame_current = 20
assert dist(bones()["Calf_R"]["tail"], at20) < 1e-6, "on a key the keys' pose stands"

# --- Pinned To is keyed: unpinned from frame 30 on, the ankle goes with the pelvis.
doc.frame_current = 30
rig.bone_set("Pelvis", position=(p[0] - 0.2, p[1] - 0.2))
rig.select_bone("Foot_R")
assert ops.armature.ik_pin_toggle() == {'FINISHED'}
assert end_of("Foot_R")["pin"] == ""
doc.frame_current = 15
assert end_of("Foot_R")["pin"] == "SCENE", "Pinned To is keyed: still pinned before frame 30"
doc.frame_current = 34
b = bones()
fk = dist(b["Calf_R"]["tail"], at20)
assert fk > 1e-3, ("unpinned, the leg hangs from the pelvis", fk)

# --- Pinned to a bone: the ankle rides it.
doc.frame_current = 0
assert ops.armature.ik_pin_set(bone="Foot_L", to="Thigh_L") == {'CANCELLED'}, "the chain moves its own thigh"
assert "moves with" in oanim.wm.banner_report()[3], oanim.wm.banner_report()
assert ops.armature.ik_pin_set(bone="Foot_L", to="Foot_L") == {'CANCELLED'}, "the foot moves with the chain"
assert ops.armature.ik_pin_set(bone="Foot_L", to="Ground") == {'FINISHED'}
assert end_of("Foot_L")["pin"] == "Ground"
assert ops.armature.ik_pin_set(bone="Foot_L", to="Ground") == {'CANCELLED'}, "pinned already: nothing changes"
doc.frame_current = 10
g = rest["Ground"]["position"]
rig.bone_set("Ground", position=(g[0] + 0.15, g[1] + 0.1))
doc.frame_current = 0
doc.frame_current = 10
b = bones()
moved = (b["Ground"]["head"][0] - rest["Ground"]["head"][0], b["Ground"]["head"][1] - rest["Ground"]["head"][1])
want = (rest["Calf_L"]["tail"][0] + moved[0], rest["Calf_L"]["tail"][1] + moved[1])
assert dist(b["Calf_L"]["tail"], want) < 1e-3, ("pinned to the ground bone, the ankle rides it", b["Calf_L"]["tail"], want)

# --- One already following: R pinned to L's calf, then L to R's calf would chase it round.
doc.frame_current = 0
assert ops.armature.ik_pin_set(bone="Foot_R", to="Calf_L") == {'FINISHED'}
assert ops.armature.ik_pin_set(bone="Foot_L", to="Calf_R") == {'CANCELLED'}, "Calf_R already follows Foot_L"
assert ops.armature.ik_pin_set(bone="Foot_R", to="SCENE") == {'FINISHED'}

# --- Removing: on frame 0 only.
doc.frame_current = 5
assert ops.armature.ik_remove(bone="Foot_L") == {'CANCELLED'}
doc.frame_current = 0

# --- A save keeps it all.
kept = {f: bones() for f in (0, 12, 15, 34)}
for f in kept:
    doc.frame_current = f
    kept[f] = {n: (b["head"], b["tail"]) for n, b in bones().items()}
doc.frame_current = 0
settings = {n: rig.bone_constraints(n) for n in ("Foot_R", "Foot_L", "Pelvis")}
path = str(pathlib.Path(tempfile.mkdtemp()) / "ik_end.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
rig = next(l for l in oanim.data.layers.all() if l.id == rig.id)
doc.frame_current = 0
for n, cs in settings.items():
    back = rig.bone_constraints(n)
    for c, d in zip(cs, back):
        for k in ("type", "ik_head", "keep_angle", "soft", "pin"):
            assert c[k] == d[k], (n, k, c[k], d[k])
for f in kept:
    doc.frame_current = f
    for n, b in bones().items():
        assert dist(b["head"], kept[f][n][0]) < 1e-5 and dist(b["tail"], kept[f][n][1]) < 1e-5, (f, n)

doc.frame_current = 0
assert ops.armature.ik_remove(bone="Foot_L") == {'FINISHED'}
assert not any(c["type"] == "IK_END" for c in rig.bone_constraints("Foot_L"))
assert ops.armature.ik_remove(bone="Pelvis", type="IK_BASE") == {'FINISHED'}
assert list(_oanim.layer_bone_ik_chain(rig.id, "Foot_R", "IK_END")) == ["Calf_R", "Thigh_R", "Pelvis", "Root"], \
    "without the base the chain runs to the root"

# --- Moving IK points by hand (the viewport's dots and rings): a fresh pair of legs.
ops.wm.read_homefile(confirmed="1")
doc, layers = oanim.data.document, oanim.data.layers
doc.auto_freeze_keys = False
doc.frame_current = 0
ops.layer.new_bone()
rig = layers.active
add("Root", (0, -2.5), (0, -2.3))
add("Pelvis", (0, 0), (0, 0.4), "Root")
for tag, s in (("_R", -1), ("_L", 1)):
    add("Thigh" + tag, (0.15 * s, 0), (0.25 * s, -1.0), "Pelvis")
    add("Calf" + tag, (0.25 * s, -1.0), (0.2 * s, -2.0), "Thigh" + tag)
    add("Foot" + tag, (0.2 * s, -2.0), (0.5 * s, -2.05), "Calf" + tag)
assert ops.armature.ik_base_add(bone="Pelvis") == {'FINISHED'}
for tag in ("_R", "_L"):
    assert ops.armature.ik_end_add(bone="Foot" + tag) == {'FINISHED'}
rest = bones()
assert ops.armature.ik_drag(bone="Foot_R", x="-0.5", y="-1.6") == {'CANCELLED'}, "posed off the setup frame"
doc.auto_key = True
doc.frame_current = 10


def side(b):
    h, k, t = b["Thigh_R"]["head"], b["Thigh_R"]["tail"], b["Calf_R"]["tail"]
    return (t[0] - h[0]) * (k[1] - h[1]) - (t[1] - h[1]) * (k[0] - h[0])


assert ops.armature.ik_drag(bone="Foot_R", x="-0.5", y="-1.6") == {'FINISHED'}
b = bones()
assert dist(b["Calf_R"]["tail"], (-0.5, -1.6)) < 1e-4, ("the ankle goes where it is dragged", b["Calf_R"]["tail"])
assert turn(way(b["Foot_R"]), way(rest["Foot_R"])) < 1e-4, "Keep Angle: the foot keeps its angle"
assert turn(way(b["Pelvis"]), way(rest["Pelvis"])) < 1e-6, "the chain stops at the IK Base"
assert ops.armature.ik_flip(bone="Foot_R") == {'FINISHED'}
f = bones()
assert dist(f["Calf_R"]["tail"], (-0.5, -1.6)) < 1e-3, ("a flip keeps the ankle", f["Calf_R"]["tail"])
assert side(f) * side(b) < 0, "a flip bends the knee the other way"
assert dist(f["Thigh_R"]["tail"], b["Thigh_R"]["tail"]) > 0.1
# One bone more: the pelvis bends too (past its base, for this move).
assert ops.armature.ik_drag(bone="Foot_R", x="-0.9", y="-1.2", more="1") == {'FINISHED'}
m = bones()
assert dist(m["Calf_R"]["tail"], (-0.9, -1.2)) < 1e-3, m["Calf_R"]["tail"]
assert turn(way(m["Pelvis"]), way(rest["Pelvis"])) > 1e-3, "one bone more turns the pelvis"
# Out of reach: Soft draws it in short of full reach; stretch reaches.
reach = dist(rest["Thigh_R"]["head"], rest["Thigh_R"]["tail"]) + dist(rest["Calf_R"]["head"], rest["Calf_R"]["tail"])
far = (m["Thigh_R"]["head"][0], m["Thigh_R"]["head"][1] - 3.0)
edge = (m["Thigh_R"]["head"][0], m["Thigh_R"]["head"][1] - reach)
assert ops.armature.ik_drag(bone="Foot_R", x=repr(edge[0]), y=repr(edge[1])) == {'FINISHED'}
got = dist(bones()["Calf_R"]["tail"], bones()["Thigh_R"]["head"])
assert reach * 0.9 < got < reach - 0.03, ("Soft: a goal at full reach is drawn in", got, reach)
rig.bone_constraint_set("Foot_R", end_index("Foot_R"), soft=False)
assert ops.armature.ik_drag(bone="Foot_R", x=repr(edge[0]), y=repr(edge[1] + 0.001)) == {'FINISHED'}
got = dist(bones()["Calf_R"]["tail"], bones()["Thigh_R"]["head"])
assert abs(got - reach) < 2e-3, ("not Soft: straight out to full reach", got, reach)
rig.bone_constraint_set("Foot_R", end_index("Foot_R"), soft=True)
assert ops.armature.ik_drag(bone="Foot_R", x=repr(far[0]), y=repr(far[1]), stretch="1") == {'FINISHED'}
s = bones()
assert dist(s["Calf_R"]["tail"], far) < 1e-3, ("stretched, it reaches", s["Calf_R"]["tail"], far)
assert abs(s["Thigh_R"]["scale"][1] - 1.0) > 0.1, s["Thigh_R"]["scale"]
assert ops.armature.ik_clear_scale(bone="Foot_R") == {'FINISHED'}
assert all(abs(v - 1.0) < 1e-6 for v in bones()["Thigh_R"]["scale"]), bones()["Thigh_R"]["scale"]
assert ops.armature.ik_clear_scale(bone="Foot_R") == {'CANCELLED'}, "nothing left to clear"

# Holds: the left foot pinned stays put while the pelvis moves; the right, unpinned, goes with it.
rig.select_bone("Foot_L")
assert ops.armature.ik_pin_toggle() == {'FINISHED'}
before = bones()
rig.select_bone("Pelvis")
assert ops.armature.translate(move_x="0.15", move_y="-0.3", posing="1") == {'FINISHED'}
b = bones()
assert dist(b["Calf_L"]["tail"], before["Calf_L"]["tail"]) < 1e-4, ("a pinned ankle holds", b["Calf_L"]["tail"])
assert dist(b["Calf_R"]["tail"], before["Calf_R"]["tail"]) > 0.1, "an unpinned ankle goes with the pelvis"
doc.frame_current = 11
doc.frame_current = 10
assert dist(bones()["Calf_L"]["tail"], before["Calf_L"]["tail"]) < 1e-4, "keyed where it was held"
# Pinned to a bone: an ankle held rides that bone as it moves.
assert ops.armature.ik_pin_set(bone="Foot_R", to="Root") == {'FINISHED'}
b0 = bones()
rig.select_bone("Root")
# Toward the left ankle, so it stays in reach.
toward = (b0["Calf_L"]["tail"][0] - b0["Thigh_L"]["head"][0], b0["Calf_L"]["tail"][1] - b0["Thigh_L"]["head"][1])
k = 0.15 / math.hypot(*toward)
assert ops.armature.translate(move_x=repr(toward[0] * k), move_y=repr(toward[1] * k), posing="1") == {'FINISHED'}
b1 = bones()
moved = (b1["Root"]["head"][0] - b0["Root"]["head"][0], b1["Root"]["head"][1] - b0["Root"]["head"][1])
assert dist(moved, (0, 0)) > 0.1
want = (b0["Calf_R"]["tail"][0] + moved[0], b0["Calf_R"]["tail"][1] + moved[1])
assert dist(b1["Calf_R"]["tail"], want) < 1e-3, ("pinned to the root, the ankle rides it", b1["Calf_R"]["tail"], want)
assert dist(b1["Calf_L"]["tail"], b0["Calf_L"]["tail"]) < 1e-4, "pinned to the scene, the other stays"

# --- Symmetrize: the copy's IK End is pinned to the other side's bone, and so is the mirrored action's.
ops.wm.read_homefile(confirmed="1")
doc, layers = oanim.data.document, oanim.data.layers
doc.auto_key = True
ops.layer.new_bone()
rig = layers.active
add("Turn_L", (0.5, 1.5), (1.0, 1.5))
add("Root_X", (0, 0), (0, 0.3))
add("Thigh_L", (0.2, 0), (0.3, -1), "Root_X")
add("Shin_L", (0.3, -1), (0.3, -2), "Thigh_L")
add("Pad_L", (0.5, -2.5), (0.8, -2.5))
rig.bone_set("Turn_L", strength=0.0)
assert ops.armature.ik_end_add(bone="Shin_L") == {'FINISHED'}
rig.select_bone("Turn_L")
assert ops.anim.action_new(name="Turn_L", action_bone="1") == {'FINISHED'}
doc.frame_current = 10
rig.bone_set("Turn_L", angle=0.5)
assert ops.armature.ik_pin_set(bone="Shin_L", to="Pad_L") == {'FINISHED'}
doc.frame_current = 11
doc.frame_current = 0
doc.action = ""
ops.armature.select_all()
assert ops.armature.symmetrize() == {'FINISHED'}
assert [c["type"] for c in rig.bone_constraints("Shin_R")] == ["IK_END"]
doc.action = "Turn_L"
doc.frame_current = 10
assert rig.bone_constraints("Shin_R")[0]["pin"] == "Pad_R", "the copy is pinned to its own side's pad"
doc.action = "Turn_R"
doc.frame_current = 10
assert rig.bone_constraints("Shin_R")[0]["pin"] == "Pad_R", "the mirrored action pins the other side's pad"
assert rig.bone_constraints("Shin_L")[0]["pin"] == "Pad_L"

print("test_ik_end: OK")
