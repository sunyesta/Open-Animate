"""A point of a drawing bent along a bone chain's curve (Parent Bone Deform: Curve) goes where it is moved on a posed
frame, as under Deform Points. Its skin there is a guess round where it was, and the settle that corrects the guess
under a deform modifier was left out for a curve, so a point moved 0.32 landed 0.049 off; the same for a drawing inside a
group bound by Curve.

Run with:  OpenAnimate --background --python tests/test_bone_curve_point_drag.py
"""

import math

import oanim

ops, L = oanim.ops, oanim.data.layers


def find(name):
    return next(l for l in L.all() if l.name == name)


def shown(name):
    layer = find(name)
    return [layer.to_document(q) for q in layer.evaluated()[0]]


def rig_scene():
    """A bendy chain Upper (0,0)-(1,0), Fore connected on to (2,0). Fore turned on frame 10, so the curve bends."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = L.active
    rig.name = "Rig"
    for name, h, t, parent in (("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper")):
        assert ops.armature.bone_add(name=name, head_x=str(h[0]), head_y=str(h[1]), tail_x=str(t[0]),
                                     tail_y=str(t[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    assert ops.armature.bone_relations_set(bone="Fore", connected="1") == {'FINISHED'}
    for name in ("Upper", "Fore"):
        assert ops.armature.bendy_set(bone=name) == {'FINISHED'}
    return doc, rig


def line(name, into):
    ops.layer.new()
    L.active.name = name
    L.active.add_curve([(0.2 + 0.4 * i, 0.05) for i in range(5)])
    assert ops.layer.move_to_group(group=str(into.id)) == {'FINISHED'}
    L.active = find(name)


def pose(doc, rig):
    doc.auto_key = True
    doc.frame_current = 10
    rig.bone_set("Fore", angle=-0.8)
    doc.frame_current = 9
    doc.frame_current = 10


def lands(doc, name):
    """Point 2 moved (0.3, -0.1) by G: how far from there it shows."""
    goal = tuple(a + b for a, b in zip(shown(name)[2], (0.3, -0.1)))
    L.active = find(name)
    ops.mesh.select_none()
    find(name).select_points([2])
    assert ops.mesh.translate(move_x="0.3", move_y="-0.1") == {'FINISHED'}
    doc.frame_current = 11
    doc.frame_current = 10
    return math.dist(shown(name)[2], goal)


# --- A drawing bound Deform Curve along the chain: the point lands where it is moved, as under Deform Points -----------
doc, rig = rig_scene()
for name, args in (("Curve", dict(deform="CURVE", chain_end="Fore")), ("Points", dict(deform="POINTS"))):
    line(name, rig)
    assert ops.layer.parent_bone_set(bone="Upper", **args) == {'FINISHED'}
pose(doc, rig)
for name in ("Points", "Curve"):
    off = lands(doc, name)
    assert off < 1e-3, (name, "lands off where it was moved", off)

# --- A drawing in a group bound Deform Curve: the same ------------------------------------------------------------------
doc, rig = rig_scene()
assert ops.layer.new_group() == {'FINISHED'}
group = L.active
group.name = "Group"
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
group = find("Group")
line("Inside", group)
L.active = group
assert ops.layer.parent_bone_set(bone="Upper", deform="CURVE", chain_end="Fore") == {'FINISHED'}
pose(doc, rig)
off = lands(doc, "Inside")
assert off < 1e-3, ("a drawing in a group bound Curve lands off where it was moved", off)

print("bone curve point drag: ok")
