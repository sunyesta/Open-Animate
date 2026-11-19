"""A Parent Bone's Deform on groups, and Curve from a bone's head or tail.

A group given a Parent Bone starts as Layer (it moves as a whole); Points and Curve bend every drawing inside as a
drawing of its own would be bent with that Deform, the group itself left where it is and its bone overriding the
drawings' own; what inside has no points (a picture) still rides the bone whole. Attached To Head or Tail with Deform
Curve bends along the bone's curve (or its chain's) with each point as far along it from that end as it was, so it bends
but never stretches; Rigid is the end's whole move, with its Turn.

Run with:  OpenAnimate --background --python tests/test_bone_group_deform.py
"""

import json
import math
import os
import pathlib
import tempfile
import zipfile

import _oanim
import oanim

ops = oanim.ops
STILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "media", "still.png")
XS = (0.1, 0.3, 0.5, 0.7, 0.9)
LONG = (0.2, 0.6, 1.0, 1.4, 1.8)
Y = 0.05


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def scene():
    """Upper (0,0)-(1,0) with Fore connected on to (2,0), both bendy; Strip, a line along Upper, and Long, along both."""
    global doc, layers, rig
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail, parent in (("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper")):
        assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                     tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    assert ops.armature.bone_relations_set(bone="Fore", connected="1") == {'FINISHED'}
    for name in ("Upper", "Fore"):
        ops.armature.bone_relations_set(bone=name, keep_end_distance="0")
        assert ops.armature.bendy_set(bone=name) == {'FINISHED'}
    drawing("Strip", XS)
    drawing("Long", LONG)
    doc.auto_key = True


def drawing(name, xs, into=None):
    ops.layer.new()
    layers.active.name = name
    layers.active.add_curve([(x, Y) for x in xs])
    ops.layer.move_to_group(group=str((into or rig).id))
    layers.active = find(name)
    return find(name)


def bind(name, **args):
    doc.frame_current = 0
    layers.active = find(name)
    return ops.layer.parent_bone_set(**args)


def pose(upper_stretch=1.0, fore=0.0):
    doc.frame_current = 10
    rig.bone_set("Upper", scale=(1.0, upper_stretch))
    rig.bone_set("Fore", angle=fore)
    doc.frame_current = 10


def shown(name):
    l = find(name)
    return [l.to_document(q) for q in l.evaluated()[0]]


def bez(p, t):
    u = 1 - t
    return (u ** 3 * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t ** 3 * p[3][0],
            u ** 3 * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t ** 3 * p[3][1])


def curve_line(names):
    """The chain's curve now, finely: its points (document space: the rig sits at the origin)."""
    pts = []
    for name in names:
        p = _oanim.bone_curve_controls(rig.id, name, False)
        pts += [bez(p, k / 400) for k in range(0 if not pts else 1, 401)]
    return pts


def along(line, q):
    """How far along `line` the nearest place to q is, and how far off it q is."""
    best, s, run = 1e9, 0.0, 0.0
    for a, b in zip(line, line[1:]):
        v = (b[0] - a[0], b[1] - a[1])
        vv = v[0] ** 2 + v[1] ** 2
        u = max(0.0, min(1.0, ((q[0] - a[0]) * v[0] + (q[1] - a[1]) * v[1]) / vv))
        d = dist(q, (a[0] + v[0] * u, a[1] + v[1] * u))
        if d < best:
            best, s = d, run + u * math.sqrt(vv)
        run += math.sqrt(vv)
    return s, best, run


def near(a, b, what, tol=1e-4):
    assert dist(a, b) < tol, (what, a, b)


# --- Head + Curve on a stretched bone: each point as far from the head as it was; Body + Curve stretches -------------
scene()
assert bind("Strip", bone="Upper", attached_to="HEAD", deform="CURVE") == {'FINISHED'}
strip = find("Strip")
assert strip.parent_bone_attached_to == "HEAD" and strip.parent_bone_deform == "CURVE"
pose(upper_stretch=2.0)
for x, p in zip(XS, shown("Strip")):
    near(p, (x, Y), "Head: not stretched")
pose(upper_stretch=0.5)
for x, p in zip(XS, shown("Strip")):
    near(p, (x, Y), "Head: past a shortened bone's tip, carried straight on")
assert bind("Strip", attached_to="BODY") == {'FINISHED'}
assert strip.parent_bone_deform == "CURVE", "Curve kept for the whole bone"
pose(upper_stretch=2.0)
for x, p in zip(XS, shown("Strip")):
    near(p, (2 * x, Y), "Body: stretched with the bone")

# --- Tail + Curve: as far back from the tip -----------------------------------------------------------------------------
scene()
assert bind("Strip", bone="Upper", attached_to="TAIL", deform="CURVE") == {'FINISHED'}
pose(upper_stretch=2.0)
for x, p in zip(XS, shown("Strip")):
    near(p, (2.0 - (1.0 - x), Y), "Tail: on from the stretched tip, not stretched")
pose(upper_stretch=0.5)
for x, p in zip(XS, shown("Strip")):
    near(p, (0.5 - (1.0 - x), Y), "Tail: past a shortened bone's head, carried straight on")
doc.frame_current = 0
for x, p in zip(XS, shown("Strip")):
    near(p, (x, Y), "Setup: where it was drawn")

# --- Bent and stretched: along the curve, as far from the end as it was and as far off it ------------------------------
for at in ("HEAD", "TAIL"):
    scene()
    assert bind("Strip", bone="Upper", attached_to=at, deform="CURVE") == {'FINISHED'}
    assert bind("Long", bone="Upper", attached_to=at, deform="CURVE", chain_end="Fore") == {'FINISHED'}
    assert find("Long").parent_bone_attached_to == at, "Chain To leaves Attached To as it is"
    pose(upper_stretch=1.5, fore=math.pi / 2)
    upper, both = curve_line(["Upper"]), curve_line(["Upper", "Fore"])
    mid = bez(_oanim.bone_curve_controls(rig.id, "Upper", False), 0.5)
    assert abs(mid[1]) > 0.02, ("the upper arm bends (its joint lined up with the turned forearm)", mid)
    for name, xs, line, total in (("Strip", XS, upper, 1.0), ("Long", LONG, both, 2.0)):
        for x, p in zip(xs, shown(name)):
            s, off, run = along(line, p)
            want = x if at == "HEAD" else run - (total - x)
            assert abs(s - want) < 4e-3 and abs(off - Y) < 4e-3, (at, name, x, s, want, off)

# --- Rigid: the end's whole move; Turn only with it; only at an end ------------------------------------------------------
scene()
assert bind("Strip", bone="Upper", attached_to="TAIL", deform="CURVE") == {'FINISHED'}
assert bind("Strip", deform="RIGID") == {'FINISHED'}
strip = find("Strip")
assert strip.parent_bone_deform == "RIGID"
assert bind("Strip", deform="RIGID") == {'CANCELLED'}, "pressed twice changes nothing"
pose(upper_stretch=2.0)
for x, p in zip(XS, shown("Strip")):
    near(p, (1.0 + x, Y), "Rigid: moved whole with the tip")
ops.ed.undo()
assert find("Strip").parent_bone_deform == "CURVE", "one undo step"
assert bind("Strip", attached_to="BODY") == {'FINISHED'}
assert bind("Strip", deform="RIGID") == {'CANCELLED'}, "Rigid is for an end"
doc.frame_current = 10
layers.active = find("Strip")
assert ops.layer.parent_bone_set(deform="CURVE") == {'CANCELLED'}, "Setup only"

# --- A group: Layer to start, its move as a whole --------------------------------------------------------------------
scene()
ops.layer.new_group()
arm = layers.active
arm.name = "Arm"
ops.layer.move_to_group(group=str(rig.id))
arm = find("Arm")
for name in ("Strip", "Long"):
    layers.active = find(name)
    ops.layer.move_to_group(group=str(arm.id))
drawing("Twin", XS)
# A drawing's own Parent Bone, given before the group gets one: the group's wins.
assert bind("Strip", bone="Fore", deform="LAYER") == {'FINISHED'}
assert bind("Arm", bone="Upper") == {'FINISHED'}
arm = find("Arm")
assert arm.parent_bone_deform == "LAYER", "a group given a Parent Bone moves as a whole"
assert bind("Strip", bone="Upper") == {'CANCELLED'}, "the group decides for the drawings inside"
assert ops.media.add(filepath=STILL) == {'FINISHED'}
picture = layers.active
picture.name = "Picture"
ops.layer.move_to_group(group=str(find("Arm").id))
pose(upper_stretch=2.0, fore=0.6)
group_moved = find("Arm").to_document((0.5, 0.0))
assert dist(group_moved, (0.5, 0.0)) > 0.4, ("Layer: the group moves with the bone", group_moved)
picture_whole = find("Picture").to_document((0.3, 0.2))

# --- Points and Curve: every drawing inside bent as one of its own would be; the group stays; a picture rides whole -----
assert bind("Twin", bone="Upper") == {'FINISHED'}
for deform, args in (("POINTS", {"deform": "POINTS"}), ("CURVE", {"deform": "CURVE", "chain_end": "Fore"}),
                     ("HEAD", {"attached_to": "HEAD", "deform": "CURVE"})):
    assert bind("Arm", **args) == {'FINISHED'}, deform
    assert bind("Twin", **args) in ({'FINISHED'}, {'CANCELLED'})
    pose(upper_stretch=2.0, fore=0.6)
    near(find("Arm").to_document((0.5, 0.0)), (0.5, 0.0), (deform, "the group stays where it is"))
    for a, b in zip(shown("Strip"), shown("Twin")):
        near(a, b, (deform, "bent as a drawing of its own with that Deform, by the group's bone"), 1e-4)
    moved = max(dist(p, (x, Y)) for x, p in zip(XS, shown("Strip")))
    assert moved > 0.1, (deform, "and bent", moved)
    if deform != "HEAD":
        near(find("Picture").to_document((0.3, 0.2)), picture_whole, (deform, "a picture rides the bone whole"))
    assert find("Arm").parent_bone_deform == ("CURVE" if deform != "POINTS" else "POINTS")

# --- Saved and opened; a file from before opens a group's Deform as Layer ---------------------------------------------
before = shown("Strip"), shown("Long")
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp) / "group.oanim"
    assert ops.wm.save_as_mainfile(filepath=str(path)) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=str(path), confirmed="1") == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    rig = next(l for l in layers.all() if l.bones)
    doc.frame_current = 10
    assert (find("Arm").parent_bone_attached_to, find("Arm").parent_bone_deform) == ("HEAD", "CURVE")
    for a, b in zip(before[0] + before[1], shown("Strip") + shown("Long")):
        near(a, b, "shows the same after opening")
    old = pathlib.Path(tmp) / "old.oanim"
    with zipfile.ZipFile(path) as z, zipfile.ZipFile(old, "w") as out:
        for item in z.infolist():
            data = z.read(item.filename)
            if item.filename == "document.json":
                root = json.loads(data)
                root["version"] = 10
                data = json.dumps(root).encode()
            out.writestr(item, data)
    assert ops.wm.open_mainfile(filepath=str(old), confirmed="1") == {'FINISHED'}
    assert find("Arm").parent_bone_deform == "RIGID", "a group from before moved as a whole"
    assert find("Twin").parent_bone_deform == "CURVE", "a drawing keeps its Deform"

print("bone group deform: ok")
