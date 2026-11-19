"""Apply Pose as Rest bends a drawing bound Parent Bone Deform: Curve into the new rest, as it does Deform Points. The
curve lines it bent by were the posed frame's, not the bones' move from their old rest to their new one, so the drawing
stayed as it was on the setup frame (0.446 off for a line along a bone turned 0.5).

Run with:  OpenAnimate --background --python tests/test_apply_rest_curve.py
"""

import math

import oanim

ops, L = oanim.ops, oanim.data.layers


def find(name):
    return next(l for l in L.all() if l.name == name)


def shown(name):
    layer = find(name)
    return [layer.to_document(q) for q in layer.evaluated()[0]]


def scene(bones):
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = L.active
    rig.name = "Rig"
    for name, h, t, parent in bones:
        assert ops.armature.bone_add(name=name, head_x=str(h[0]), head_y=str(h[1]), tail_x=str(t[0]),
                                     tail_y=str(t[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    return doc, rig


def line(name, rig, **args):
    ops.layer.new()
    L.active.name = name
    L.active.add_curve([(0.1 + 0.4 * i, 0.05) for i in range(5)])
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    L.active = find(name)
    assert ops.layer.parent_bone_set(bone="Upper", **args) == {'FINISHED'}


def applied_same(doc, rig, names):
    """Apply Pose as Rest on frame 10: frame 0 shows each drawing as frame 10 did."""
    doc.frame_current = 9
    doc.frame_current = 10
    before = {n: shown(n) for n in names}
    L.active = rig
    assert ops.armature.apply_pose_as_rest() == {'FINISHED'}
    doc.frame_current = 0
    for n in names:
        off = max(math.dist(a, b) for a, b in zip(before[n], shown(n)))
        assert off < 1e-3, (n, "frame 0 after Apply Pose as Rest is off what frame 10 showed", off)


# --- One straight bone turned: Curve goes into the new rest as Points does ---------------------------------------------
doc, rig = scene([("Upper", (0, 0), (1, 0), "")])
line("Curve", rig, deform="CURVE")
line("Points", rig, deform="POINTS")
doc.auto_key = True
doc.frame_current = 10
rig.bone_set("Upper", angle=0.5)
applied_same(doc, rig, ["Points", "Curve"])

# --- A bendy chain bent at its joint and moved: the drawing along it keeps the bend in the new rest ----------------------
doc, rig = scene([("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper")])
assert ops.armature.bone_relations_set(bone="Fore", connected="1") == {'FINISHED'}
for name in ("Upper", "Fore"):
    assert ops.armature.bendy_set(bone=name) == {'FINISHED'}
line("Curve", rig, deform="CURVE", chain_end="Fore")
doc.auto_key = True
doc.frame_current = 10
rig.bone_set("Upper", angle=0.3)
rig.bone_set("Fore", angle=-0.8)
applied_same(doc, rig, ["Curve"])

print("apply rest curve: ok")
