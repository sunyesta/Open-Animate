"""IK legs as a cut-out rig has them: each a thigh and a calf hanging nearly straight from a hip that IK ignores, the
knee bent a little outward at rest, the calf's IK aimed at a foot bone hanging from the root. Lowering the hip deep into
a crouch, each calf's tip reaches its foot exactly (a two-bone chain is solved, not stepped toward) and each knee bends
the way it rests, outward, the mirrored leg too; with Arc IK, the even bend chosen of the two that reach is the one
curving as the chain rests. Then the deep bend from frame 1 is the same when reached from other frames, and a
straight two-bone chain (no way it rests bent) still reaches.

Run with:  OpenAnimate --background --python tests/test_ik_bend.py
"""

import math

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


def side(b, tag):
    """Which side of the line from the thigh's head to the calf's tip the knee is on (+1 left, -1 right)."""
    h, k, t = b["Thigh" + tag]["head"], b["Thigh" + tag]["tail"], b["Calf" + tag]["tail"]
    c = (t[0] - h[0]) * (k[1] - h[1]) - (t[1] - h[1]) * (k[0] - h[0])
    return 1 if c > 0 else -1


add("Root", (0, -2.0), (0, -1.8))
add("Hip", (0, 0), (0, 0.5), "Root")
# The R leg on the left (x < 0) with its knee bent out to the left; the L leg its mirror image.
for tag, s in (("_R", -1), ("_L", 1)):
    add("Thigh" + tag, (0.1 * s, 0), (0.17 * s, -1.0), "Hip")
    add("Calf" + tag, (0.17 * s, -1.0), (0.2 * s, -2.0), "Thigh" + tag)
    add("Foot" + tag, (0.2 * s, -2.0), (0.4 * s, -2.05), "Root")
rig.bone_set("Hip", ik_ignore=True)
for tag in ("_R", "_L"):
    rig.select_bone("Calf" + tag)
    assert ops.armature.constraint_add(type="IK", bone="Calf" + tag) == {'FINISHED'}
    rig.bone_constraint_set("Calf" + tag, 0, target="Foot" + tag)
    ops.armature.select_none()
rest = bones()
rest_side = {t: side(rest, t) for t in ("_R", "_L")}
assert rest_side["_R"] == -rest_side["_L"], rest_side

doc.auto_key = True
doc.frame_current = 1
hip = rest["Hip"]
# Root points up: its x is the document's up. Down 0.7: the legs fold deep.
rig.bone_set("Hip", position=(hip["position"][0] - 0.7, hip["position"][1]))
doc.frame_current = 0
doc.frame_current = 1


def check(what, eps=1e-4, deep=0.6):
    b = bones()
    for tag in ("_R", "_L"):
        miss = dist(b["Calf" + tag]["tail"], b["Foot" + tag]["head"])
        assert miss < eps, (what, tag, "the calf reaches its foot", miss)
        assert side(b, tag) == rest_side[tag], (what, tag, "the knee bends the way it rests")
        bend = abs(math.atan2(b["Calf" + tag]["tail"][1] - b["Calf" + tag]["head"][1],
                              b["Calf" + tag]["tail"][0] - b["Calf" + tag]["head"][0]) -
                   math.atan2(b["Thigh" + tag]["tail"][1] - b["Thigh" + tag]["head"][1],
                              b["Thigh" + tag]["tail"][0] - b["Thigh" + tag]["head"][0]))
        assert bend > deep, (what, tag, "a deep bend", bend)
    return b


check("cyclic")
# The same frame reached from elsewhere is the same pose.
a = {n: tuple(b["tail"]) for n, b in bones().items()}
for f in (5, 0, 3, 1):
    doc.frame_current = f
b = bones()
assert all(dist(a[n], b[n]["tail"]) < 1e-5 for n in a), "frame 1 from other frames"

# Arc IK: of the two even bends reaching as far, the one curving as the chain rests.
for tag in ("_R", "_L"):
    rig.bone_set("Calf" + tag, arc_ik=True)
# Crouching from shallow to deep: either even bend can come out a hair closer, so each depth must pick by the rest.
for drop in (0.15, 0.25, 0.35, 0.45, 0.55, 0.7, 0.85):
    rig.bone_set("Hip", position=(hip["position"][0] - drop, hip["position"][1]))
    check("arc, down %g" % drop, 2e-3, 0.3)  # the even bend is searched in steps
for tag in ("_R", "_L"):
    rig.bone_set("Calf" + tag, arc_ik=False)

# A straight two-bone chain has no bend to keep: it still reaches.
doc.frame_current = 0
add("Arm", (3, 0), (4, 0))
add("ForeArm", (4, 0), (5, 0), "Arm")
add("Goal", (5, 0), (5.2, 0))
rig.select_bone("ForeArm")
assert ops.armature.constraint_add(type="IK", bone="ForeArm") == {'FINISHED'}
rig.bone_constraint_set("ForeArm", 0, target="Goal")
ops.armature.select_none()
doc.frame_current = 1
g = bones()["Goal"]
rig.bone_set("Goal", position=(g["position"][0] - 0.8, g["position"][1] + 0.3))
b = bones()
assert dist(b["ForeArm"]["tail"], b["Goal"]["head"]) < 1e-4, ("a straight chain reaches", b["ForeArm"]["tail"])
print("test_ik_bend passed")
