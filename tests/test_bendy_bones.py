"""Bendy bones: each bone bends along a curve from head to tail, shaped by a handle at each end. A joint between
connected bones has two handles, lined up and staying lined up as the bones turn; Alt (alone=1) moves one alone,
breaking them, after which each keeps its angle to its own bone, so a sharp corner stays sharp. An end joint has one
handle, and left alone mirrors the other end (the bone an arc). Flatten Both to Bone lays a bone's handles along it
(broken, so the bones beside keep their curves); Sharp Corner points a joint's handles along their bones. The handles
are keyed. A drawing whose Parent Bone has Deform: Curve bends along its bone's curve, or a chain of connected bones,
each point going where its place on the rest curve goes, as far along the same bone. Saved with the file.

Run with:  OpenAnimate --background --python tests/test_bendy_bones.py
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
    if parent:
        assert ops.armature.bone_relations_set(bone=name, connected="1") == {'FINISHED'}
    ops.armature.select_none()


def bones():
    doc.frame_current = doc.frame_current
    return {b["name"]: b for b in rig.bones}


def ctrl(name, rest=False):
    return _oanim.bone_curve_controls(rig.id, name, rest)


def ang(v):
    return math.atan2(v[1], v[0])


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def head_dev(name):
    """The angle of a bone's head handle to the bone."""
    p = ctrl(name)
    return wrap(ang(sub(p[1], p[0])) - ang(sub(p[3], p[0])))


def tail_dev(name):
    p = ctrl(name)
    return wrap(ang(sub(p[3], p[2])) - ang(sub(p[3], p[0])))


def gap(a, b):
    """How far the curve turns across the joint from bone a to bone b (0: smooth)."""
    pa, pb = ctrl(a), ctrl(b)
    return abs(wrap(ang(sub(pb[1], pb[0])) - ang(sub(pa[3], pa[2]))))


def corner(a, b):
    """The turn between the two bones themselves."""
    pa, pb = ctrl(a), ctrl(b)
    return abs(wrap(ang(sub(pb[3], pb[0])) - ang(sub(pa[3], pa[0]))))


def turn(name, by):
    """Pose: turns a bone by `by` (its children with it)."""
    rig.bone_set(name, angle=bones()[name]["angle"] + by)


# An arm: upper arm, forearm and hand, connected, bent at the elbow and the wrist.
add("Upper", (0.0, 0.0), (1.0, 0.0))
add("Fore", (1.0, 0.0), (1.6, -0.8), "Upper")
add("Hand", (1.6, -0.8), (1.7, -1.2), "Fore")
b = bones()
assert b["Fore"]["connected"] and b["Hand"]["connected"]
for k in ("curve_turn", "curve_lined", "curve_head_reach", "curve_tail_reach"):
    assert k in b["Upper"], k

# --- At rest: a joint left alone is lined up; a free end mirrors the other end (an arc).
assert gap("Upper", "Fore") < 1e-5 and gap("Fore", "Hand") < 1e-5, "joints smooth"
assert abs(head_dev("Upper") + tail_dev("Upper")) < 1e-5 and abs(head_dev("Upper")) > 0.1, \
    ("the upper arm's free shoulder end mirrors its elbow end", head_dev("Upper"), tail_dev("Upper"))
# A circular arc: every point of the curve the same distance from one centre.
p = ctrl("Upper")
t0 = (p[1][0] - p[0][0], p[1][1] - p[0][1])
n = (-t0[1], t0[0])
c = sub(p[3], p[0])
den = 2 * (c[0] * n[0] + c[1] * n[1])
r = (c[0] ** 2 + c[1] ** 2) / den
o = (p[0][0] + n[0] / math.hypot(*n) * r * math.hypot(*n), p[0][1] + n[1] / math.hypot(*n) * r * math.hypot(*n))
o = (p[0][0] + n[0] * r, p[0][1] + n[1] * r)


def bez(p, t):
    a = 1 - t
    w = (a * a * a, 3 * a * a * t, 3 * a * t * t, t * t * t)
    return (sum(w[i] * p[i][0] for i in range(4)), sum(w[i] * p[i][1] for i in range(4)))


radius = dist(o, p[0])
worst = max(abs(dist(o, bez(p, i / 16)) - radius) for i in range(17)) / dist(p[0], p[3])
assert worst < 1e-3, ("an end left alone carries the curve on as an arc", worst)

# --- Sharp Corner on the elbow, then the forearm turned (posed, auto-key): the corner stays sharp.
doc.auto_key = True
doc.frame_current = 10
assert ops.armature.curve_sharp_corner(bone="Fore", end="HEAD") == {'FINISHED'}
assert abs(tail_dev("Upper")) < 1e-6 and abs(head_dev("Fore")) < 1e-6, "Sharp Corner: both handles along their bones"
assert abs(gap("Upper", "Fore") - corner("Upper", "Fore")) < 1e-5
assert ops.armature.curve_sharp_corner(bone="Fore", end="HEAD") == {'CANCELLED'}, "twice changes nothing"
turn("Fore", -0.6)
assert abs(tail_dev("Upper")) < 1e-6 and abs(head_dev("Fore")) < 1e-6, "turned: still along their bones"
assert abs(gap("Upper", "Fore") - corner("Upper", "Fore")) < 1e-5 and corner("Upper", "Fore") > 0.3, "still sharp"
assert gap("Fore", "Hand") < 1e-5, "the wrist, lined up, stays smooth"
turn("Hand", 0.5)
assert gap("Fore", "Hand") < 1e-5, "a lined-up joint stays smooth as a bone turns"
# Keyed: frame 0 is still smooth; between frame 0 and 10 the elbow blends.
doc.frame_current = 0
assert gap("Upper", "Fore") < 1e-5, "frame 0 keeps the rest"
doc.frame_current = 5
lined = bones()["Fore"]["curve_lined"]
assert 0.01 < lined < 0.99, ("between a smooth key and a sharp key the joint blends", lined)
doc.frame_current = 10
assert bones()["Fore"]["curve_lined"] == 0.0

# --- Dragging a handle: a plain drag lines the joint's handles up again, the handle at the mouse.
H = ctrl("Fore")[1]
J = bones()["Fore"]["head"]
goal = (J[0] + (H[0] - J[0]) * 1.2 - (H[1] - J[1]) * 0.3, J[1] + (H[1] - J[1]) * 1.2 + (H[0] - J[0]) * 0.3)
assert ops.armature.curve_handle_set(bone="Fore", end="HEAD", x=repr(goal[0]), y=repr(goal[1])) == {'FINISHED'}
assert dist(ctrl("Fore")[1], goal) < 1e-4, ("the handle goes to the mouse", ctrl("Fore")[1], goal)
assert gap("Upper", "Fore") < 1e-5, "lined up again"
assert bones()["Fore"]["curve_lined"] == 1.0
# Alt: the other side stays, the joint broken; turning a bone keeps each handle's angle to its bone.
G = ctrl("Upper")[2]
th = -0.4 if tail_dev("Upper") > 0 else 0.4
goal2 = (J[0] + ((G[0] - J[0]) * math.cos(th) - (G[1] - J[1]) * math.sin(th)) * 0.9,
         J[1] + ((G[0] - J[0]) * math.sin(th) + (G[1] - J[1]) * math.cos(th)) * 0.9)
fore_side = ctrl("Fore")[1]
assert ops.armature.curve_handle_set(bone="Upper", end="TAIL", x=repr(goal2[0]), y=repr(goal2[1]), alone="1") == \
    {'FINISHED'}
assert dist(ctrl("Upper")[2], goal2) < 1e-4 and dist(ctrl("Fore")[1], fore_side) < 1e-5, "alone: the other side stays"
assert gap("Upper", "Fore") > 0.1
du, df = tail_dev("Upper"), head_dev("Fore")
turn("Fore", 0.7)
assert abs(tail_dev("Upper") - du) < 1e-5 and abs(head_dev("Fore") - df) < 1e-5, \
    "broken handles keep their angles to their own bones"
# The same from the other side: the forearm's head handle alone, the upper arm's staying.
J = bones()["Fore"]["head"]
F, up_side = ctrl("Fore")[1], ctrl("Upper")[2]
th = -0.2 if head_dev("Fore") > 0 else 0.2
goal3 = (J[0] + ((F[0] - J[0]) * math.cos(th) - (F[1] - J[1]) * math.sin(th)) * 1.1,
         J[1] + ((F[0] - J[0]) * math.sin(th) + (F[1] - J[1]) * math.cos(th)) * 1.1)
assert ops.armature.curve_handle_set(bone="Fore", end="HEAD", x=repr(goal3[0]), y=repr(goal3[1]), alone="1") ==     {'FINISHED'}
assert dist(ctrl("Fore")[1], goal3) < 1e-4 and dist(ctrl("Upper")[2], up_side) < 1e-5,     ("alone from the head: the other side stays", ctrl("Fore")[1], goal3, ctrl("Upper")[2], up_side)

# --- Flatten Both to Bone: the forearm straight, the handles across its joints as they were.
up_tail, hand_head = ctrl("Upper")[2], ctrl("Hand")[1]
assert ops.armature.curve_flatten(bone="Fore") == {'FINISHED'}
assert abs(head_dev("Fore")) < 1e-6 and abs(tail_dev("Fore")) < 1e-6, "the forearm straight"
assert dist(ctrl("Upper")[2], up_tail) < 1e-5 and dist(ctrl("Hand")[1], hand_head) < 1e-5, "its neighbours keep theirs"
turn("Hand", -0.8)
turn("Upper", 0.3)
assert abs(head_dev("Fore")) < 1e-6 and abs(tail_dev("Fore")) < 1e-6, "a flattened bone stays straight as others turn"

# --- Reset Curve.
assert ops.armature.curve_reset(bone="Fore") == {'FINISHED'}
assert gap("Upper", "Fore") < 1e-5 and gap("Fore", "Hand") < 1e-5, "reset: both joints lined up"
assert ops.armature.curve_reset(bone="Fore") == {'CANCELLED'}
# Bad arguments change nothing.
assert ops.armature.curve_sharp_corner(bone="Fore", end="MIDDLE") == {'CANCELLED'}
assert ops.armature.curve_handle_set(bone="Nobody", end="HEAD", x="1", y="1") == {'CANCELLED'}
# A sharp wrist keyed on frame 10, for saving.
assert ops.armature.curve_sharp_corner(bone="Hand", end="HEAD") == {'FINISHED'}

# --- A drawing along the arm, Deform: Curve along the chain from the upper arm to the forearm (a new rig, unkeyed).
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
add("Upper", (0.0, 0.0), (1.0, 0.0))
add("Fore", (1.0, 0.0), (1.6, -0.8), "Upper")
add("Hand", (1.6, -0.8), (1.7, -1.2), "Fore")
assert ops.layer.new() == {'FINISHED'}
art = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
art = next(l for l in layers.all() if l.id == art.id)
# Its tip (points 4 to 6) runs on past the forearm's end, the chain's, its other end (0 and 9) back past the shoulder.
outline = [(-0.08, 0.12), (0.5, 0.15), (0.95, 0.15), (1.2, -0.1), (1.75, -0.92), (1.8, -1.0), (1.62, -1.02),
           (1.05, -0.25), (0.5, -0.12), (-0.08, -0.12)]
art.add_curve(outline)
assert ops.layer.parent_bone_set(bone="Upper") == {'FINISHED'}
assert ops.layer.parent_bone_set(chain_end="Hand") == {'FINISHED'}
assert art.parent_bone_deform == "CURVE" and list(_oanim.layer_parent_bone_chain(art.id)) == ["Upper", "Fore", "Hand"]
assert ops.layer.parent_bone_set(chain_end="Fore") == {'FINISHED'}
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["Upper", "Fore"]
assert ops.layer.parent_bone_set(chain_end="Upper") == {'CANCELLED'} or \
    list(_oanim.layer_parent_bone_chain(art.id)) == ["Upper"]
assert ops.layer.parent_bone_set(chain_end="Fore") in ({'FINISHED'}, {'CANCELLED'})
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["Upper", "Fore"]
# A bone not connected on from the Parent Bone can't end the chain.
add("Loose", (3.0, 0.0), (3.5, 0.0))
assert ops.layer.parent_bone_set(chain_end="Loose") == {'CANCELLED'}


def points():
    pts, _, _ = art.evaluated()
    return pts


rest_pts = points()
assert all(dist(a, b) < 1e-5 for a, b in zip(rest_pts, outline)), "frame 0: the drawing as drawn"
doc.frame_current = 20
assert all(dist(a, b) < 1e-5 for a, b in zip(points(), outline)), "unposed: nothing moves"
# The forearm turned: the forearm's end of the drawing goes with it, rigidly; the shoulder end stays.
fore0 = bones()["Fore"]
turn("Fore", -0.5)
fore1 = bones()["Fore"]
moved = points()


def to_local(bone, q):
    h, a = bone["head"], ang(sub(bone["tail"], bone["head"]))
    d = sub(q, h)
    return (d[0] * math.cos(-a) - d[1] * math.sin(-a), d[0] * math.sin(-a) + d[1] * math.cos(-a))


tip_ok = max(dist(to_local(fore1, moved[i]), to_local(fore0, outline[i])) for i in (4, 5, 6))
assert tip_ok < 1e-4, ("past the chain's end the drawing turns with the forearm", tip_ok)
# The upper arm's free end carries its curve on as an arc: the shoulder end turns about the shoulder, keeping its shape.
assert all(abs(dist(moved[i], (0, 0)) - dist(outline[i], (0, 0))) < 1e-5 for i in (0, 9)), "the shoulder end turns"
assert abs(dist(moved[0], moved[9]) - dist(outline[0], outline[9])) < 1e-5
assert dist(moved[2], outline[2]) > 0.01, "the elbow bends"
# Bending, not moving rigidly: the upper arm's half nearest the elbow follows the curve's bend.
assert max(dist(a, b) for a, b in zip(moved, outline)) > 0.1

# --- Saved with the file: the curve channels, their keys, Deform Curve and the chain.
first = next(l for l in layers.all() if l.bones and l.id != rig.id)


def curves(r):
    out = {}
    for f in (0, 3, 5, 10):
        doc.frame_current = f
        for b in r.bones:
            out[(f, b["name"])] = {k: v for k, v in b.items() if k.startswith("curve_")}
    return out


kept = curves(first)
assert any(v["curve_lined"] < 0.99 for v in kept.values()), "the first rig has broken joints keyed"
doc.frame_current = 0
path = str(pathlib.Path(tempfile.mkdtemp()) / "bendy.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
art = next(l for l in oanim.data.layers.all() if l.point_count == len(outline))
assert art.parent_bone_deform == "CURVE" and list(_oanim.layer_parent_bone_chain(art.id)) == ["Upper", "Fore"]
first = next(l for l in oanim.data.layers.all() if l.id == first.id)
back = curves(first)
for k in kept:
    assert all(abs(kept[k][c] - back[k][c]) < 1e-6 for c in kept[k]), (k, kept[k], back[k])

# --- A drawing's right-click menu on a bone: Extend its chain to a bone in line with it (connected), above its Parent
# Bone (the chain starts there) or below its end (it ends there); refused for a bone already in it, one not in line, or
# off frame 0. (Parent to the bone is layer.parent_bone_set bone=, as before.)
ops.wm.read_homefile(confirmed="1")
doc, layers = oanim.data.document, oanim.data.layers
doc.auto_freeze_keys = False
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
add("Root", (0.0, 0.0), (1.0, 0.0))
add("A", (1.0, 0.0), (2.0, 0.0), "Root")
add("B", (2.0, 0.0), (3.0, 0.0), "A")
add("C", (3.0, 0.0), (4.0, 0.0), "B")
add("Side", (2.0, 0.0), (2.0, 1.0), "A")
add("Loose", (0.0, 2.0), (1.0, 2.0))
assert ops.layer.new() == {'FINISHED'}
art = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
art = next(l for l in layers.all() if l.id == art.id)
art.add_curve([(1.0, 0.1), (3.5, 0.1), (3.5, -0.1), (1.0, -0.1)])
assert ops.layer.parent_bone_set(bone="B") == {'FINISHED'}
assert art.parent_bone_deform != "CURVE"
assert ops.layer.parent_bone_set(extend_to="C") == {'FINISHED'}
assert art.parent_bone_deform == "CURVE" and list(_oanim.layer_parent_bone_chain(art.id)) == ["B", "C"]
assert ops.layer.parent_bone_set(extend_to="A") == {'FINISHED'}
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["A", "B", "C"], "above: it starts there, its end kept"
assert ops.layer.parent_bone_set(extend_to="B") == {'CANCELLED'}, "already in the chain"
assert ops.layer.parent_bone_set(extend_to="Side") == {'CANCELLED'}, "connected, but not in line"
assert ops.layer.parent_bone_set(extend_to="Loose") == {'CANCELLED'}
assert ops.layer.parent_bone_set(extend_to="Nobody") == {'CANCELLED'}
assert ops.ed.undo() == {'FINISHED'}
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["B", "C"], "one undo step"
doc.frame_current = 10
assert ops.layer.parent_bone_set(extend_to="Root") == {'CANCELLED'}, "frame 0 only"
doc.frame_current = 0
assert ops.layer.parent_bone_set(extend_to="Root") == {'FINISHED'}
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["Root", "A", "B", "C"]
# Parent to one bone: the chain starts again from it.
assert ops.layer.parent_bone_set(bone="A") == {'FINISHED'}
assert list(_oanim.layer_parent_bone_chain(art.id)) == ["A"]

print("test_bendy_bones: OK")
