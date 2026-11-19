"""Attached To (a layer's Bones tab, with a regular Parent Bone): Body follows the whole bone (its squash and stretch
too); Head or Tail follows only that end, the layer moving as a whole there, never squashed or skewed (a joint's round
cap); Turn says how it turns there: With Bone, Halfway (with the connected bone meeting it there) or Never.

Run with:  OpenAnimate --background --python tests/test_bone_attach.py
"""

import math
import os
import tempfile

import oanim

ops, wm = oanim.ops, oanim.wm
R2 = math.sqrt(0.5)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def near(a, b, what, tol=1e-4):
    assert dist(a, b) < tol, (what, a, b)


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def scene():
    """Upper (0,0)-(1,0) with Fore connected on to (2,0), and a pin; a cap round the elbow, a mark on its right."""
    global doc, layers, rig, cap
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail, parent in (("Upper", (0, 0), (1, 0), ""), ("Fore", (1, 0), (2, 0), "Upper"),
                                     ("Pin", (3, 3), (3.5, 3), "")):
        assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                     tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
        ops.armature.select_none()
    assert ops.armature.bone_relations_set(bone="Fore", connected="1") == {'FINISHED'}
    for name in ("Upper", "Fore"):
        ops.armature.bone_relations_set(bone=name, keep_end_distance="0")
    rig.select_bone("Pin")
    assert ops.armature.bone_convert(type="PIN") == {'FINISHED'}
    ops.layer.new()
    layers.active.name = "Cap"
    layers.active.add_curve([(1.2, 0.0), (1.0, 0.2), (0.8, 0.0), (1.0, -0.2)], closed=True, fill=True)
    ops.layer.move_to_group(group=str(rig.id))
    cap = find("Cap")
    layers.active = cap
    assert ops.layer.parent_bone_set(bone="Upper", deform="LAYER") == {'FINISHED'}
    doc.auto_key = True


def attach(at, turn=None):
    doc.frame_current = 0
    layers.active = cap
    args = {"attached_to": at}
    if turn:
        args["turn"] = turn
    return ops.layer.parent_bone_set(**args)


def pose(upper=0.0, fore=0.0, stretch=1.0):
    """Upper turned and stretched along its length; Fore turned against it."""
    doc.frame_current = 10
    rig.bone_set("Upper", angle=upper, scale=(1.0, stretch))
    rig.bone_set("Fore", angle=fore)
    doc.frame_current = 10


def shown(p):
    return find("Cap").to_document(p)


def mark():
    """Where the cap's middle and its mark (0.2 to its right on Setup) show."""
    return shown((1.0, 0.0)), shown((1.2, 0.0)), shown((1.0, 0.2))


# --- Body (as before): the whole bone's move, its stretch squashing the cap ---------------------------------------------
scene()
assert cap.parent_bone_attached_to == "BODY" and cap.parent_bone_turn == "BONE"
pose(upper=math.pi / 2, stretch=2.0)
mid, right, top = mark()
near(mid, (0, 2), "on the stretched tip")
assert abs(dist(mid, top) - 0.2) > 0.05 or abs(dist(mid, right) - 0.2) > 0.05, ("Body squashes it", mid, right, top)

# --- Tail: on the tip, round however far the bone stretches, turned with the bone ---------------------------------------
scene()
assert attach("TAIL") == {'FINISHED'}
assert cap.parent_bone_attached_to == "TAIL"
pose(upper=math.pi / 2, stretch=2.0)
mid, right, top = mark()
near(mid, (0, 2), "on the stretched tip")
near(right, (0, 2.2), "turned with the bone, not squashed")
near(top, (-0.2, 2), "round: as wide across as along")
doc.frame_current = 0
near(shown((1.2, 0.0)), (1.2, 0.0), "Setup: where it was drawn")

# Deform said Points: attached to an end it is Rigid, moving as a whole, as round; Points again back on Body.
scene()
doc.frame_current = 0
layers.active = cap
assert ops.layer.parent_bone_set(deform="POINTS") == {'FINISHED'}
assert attach("TAIL") == {'FINISHED'}
assert cap.parent_bone_deform == "RIGID"
pose(upper=math.pi / 2, stretch=2.0)
mid, right, top = mark()
near(mid, (0, 2), "Points: on the stretched tip")
near(top, (-0.2, 2), "Points: as round")
assert attach("BODY") == {'FINISHED'}
assert cap.parent_bone_deform == "POINTS", "Deform kept for when it is Body again"

# Apply Pose as Rest (which leaves stretches out of the rest): the cap shows where it did, on Setup and on the frame
# posed.
scene()
assert attach("TAIL", "HALF") == {'FINISHED'}
pose(upper=0.4, fore=0.6)
before = mark()
layers.active = rig
assert ops.armature.select_all() == {'FINISHED'}
assert ops.armature.apply_pose_as_rest() == {'FINISHED'}
doc.frame_current = 0
for a, b in zip(before, mark()):
    near(a, b, "Setup shows the pose applied")
doc.frame_current = 10
for a, b in zip(before, mark()):
    near(a, b, "and the frame it was on")

# --- Turn: Never keeps its angle; Halfway turns half the bend at a connected joint -------------------------------------
scene()
assert attach("TAIL", "NONE") == {'FINISHED'}
pose(upper=math.pi / 2, stretch=2.0)
mid, right, top = mark()
near(mid, (0, 2), "on the tip")
near(right, (0.2, 2), "Never: its angle kept")
scene()
assert attach("TAIL", "HALF") == {'FINISHED'}
assert cap.parent_bone_turn == "HALF"
pose(upper=0.0, fore=math.pi / 2)
mid, right, top = mark()
near(mid, (1, 0), "the elbow stays")
near(right, (1 + 0.2 * R2, 0.2 * R2), "Halfway: half the elbow's bend")
pose(upper=math.pi / 2, fore=0.0)
mid, right, top = mark()
near(right, (0, 1.2), "a straight arm turned: the cap turns with it whole")

# --- Head: on Fore's head (the elbow), Halfway with its parent Upper ---------------------------------------------------
scene()
doc.frame_current = 0
layers.active = cap
assert ops.layer.parent_bone_set(bone="Fore", attached_to="HEAD", turn="HALF") == {'FINISHED'}
pose(upper=0.0, fore=math.pi / 2, stretch=1.5)
mid, right, top = mark()
near(mid, (1.5, 0), "on Fore's head, where the stretched Upper ends")
near(right, (1.5 + 0.2 * R2, 0.2 * R2), "halfway between Upper and Fore")
assert attach("HEAD", "BONE") == {'FINISHED'}
pose(upper=0.0, fore=math.pi / 2, stretch=1.5)
near(mark()[1], (1.5, 0.2), "With Bone: turned as Fore")

# --- Pressed twice changes nothing; one undo step; Setup only; a pin has no ends apart ----------------------------------
scene()
assert attach("TAIL") == {'FINISHED'}
assert attach("TAIL") == {'CANCELLED'}, "the same again changes nothing"
ops.ed.undo()
assert cap.parent_bone_attached_to == "BODY", "one undo step takes it back"
doc.frame_current = 10
layers.active = cap
assert ops.layer.parent_bone_set(attached_to="TAIL") == {'CANCELLED'}, "Setup only"
assert attach("ELBOW") == {'CANCELLED'}
assert attach("TAIL", "SIDEWAYS") == {'CANCELLED'}
assert attach("TAIL") == {'FINISHED'}
doc.frame_current = 0
assert ops.layer.parent_bone_set(bone="Pin") == {'FINISHED'}
assert cap.parent_bone_attached_to == "BODY", "a pin's layer follows it whole again"
assert attach("TAIL") == {'CANCELLED'}, "a pin has no head and tail apart"

# --- Saved and opened ------------------------------------------------------------------------------------------------
scene()
assert attach("TAIL", "HALF") == {'FINISHED'}
pose(upper=0.3, fore=0.8, stretch=1.7)
before = mark()
path = os.path.join(tempfile.mkdtemp(), "attach.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
cap = find("Cap")
rig = next(l for l in oanim.data.layers.all() if l.name == rig.name)
doc = oanim.data.document
doc.frame_current = 10
assert (cap.parent_bone_attached_to, cap.parent_bone_turn) == ("TAIL", "HALF")
for a, b in zip(before, mark()):
    near(a, b, "shows the same after opening")

print("bone attach: ok")
