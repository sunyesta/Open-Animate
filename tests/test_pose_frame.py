"""A pose's thumbnail frame: Save Pose shows a square in the viewport, at first round what the pose moves; dragging inside
moves it, a corner resizes it (square, the corner across staying); saved with the pose (poselib.pose_new's frame_x,
frame_y, frame_size) its thumbnail is framed on it, kept in the file; Fit to Pose leaves it round what it moves; Edit
Frame (poselib.frame_set) frames a saved pose again, frame_size=0 back round what it moves. The frame holds the points
that were inside it: with the character moved, scaled or on another frame it goes and scales with them, in the
thumbnail and in the viewport, grown to hold them if they spread (it was kept in document space and stayed put, the
thumbnail showing only the skin beside the mouth).

Run with:  OpenAnimate --background --python tests/test_pose_frame.py
"""

import math
import os
import tempfile

import _oanim
import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-4):
    if isinstance(a, (int, float)):
        return abs(a - b) < eps
    return all(abs(x - y) < eps for x, y in zip(a, b))


def scene():
    """A bone layer with Arm_L, Arm_R and Leg, a drawing whose points Arm_L moves. Frame 10: the arm raised, a point
    pulled out; frame 20: the arm lowered. Auto Keying on."""
    global doc, layers, rig_id, art_id
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    assert ops.armature.bone_add(name="Arm_L", head_x="0.5", head_y="0", tail_x="1.5", tail_y="0", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Arm_R", head_x="-0.5", head_y="0", tail_x="-1.5", tail_y="0",
                                 parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="Leg", head_x="0", head_y="-1", tail_x="0", tail_y="-2", parent="") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.layer.new() == {'FINISHED'}
    art_id = layers.active.id
    art().name = "hand"
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}
    art().add_curve([(1.2, 0.1), (1.4, 0.3), (1.1, 0.5)])
    assert ops.layer.parent_bone_set(bone="Arm_L", deform="POINTS") == {'FINISHED'}
    art().edit_with_bones = True
    doc.auto_key = True
    doc.frame_current = 10
    rig().bone_set("Arm_L", angle=0.7)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] + 0.3)
    art().set_point(0, (1.3, 0.0))
    doc.frame_current = 20
    rig().bone_set("Arm_L", angle=-0.4)
    rig().bone_set("Leg", angle=bone("Leg")["setup_angle"] - 0.5)
    art().set_point(0, (1.6, 0.4))
    at(10)
    # (An undo step of its own, so undoing an operator leaves the scene's Python edits in.)
    layers.active = art()
    assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
    assert ops.object.modifier_remove(index="0") == {'FINISHED'}


def rig():
    return next(l for l in layers.all() if l.id == rig_id)


def art():
    return next(l for l in layers.all() if l.id == art_id)


def bone(name):
    return next(b for b in rig().bones if b["name"] == name)


def stored():
    return [tuple(p[:2]) for p in art().points]


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def select_bones(*names):
    layers.active = rig()
    ops.armature.select_none()
    for i, n in enumerate(names):
        rig().select_bone(n, extend=i > 0)


def select_points(picked):
    layers.active = art()
    ops.mesh.select_none()
    art().select_points(picked)


def select_nothing():
    layers.active = rig()
    ops.armature.select_none()
    layers.active = art()
    ops.mesh.select_none()


def poses():
    return _oanim.poses()


def pose(name):
    return next(p for p in poses() if p["name"] == name)


# --- Save Pose: the frame starts round what the pose moves --------------------------------------------------------------
scene()
select_bones("Arm_L")
wm.pose_frame_open()
start = wm.pose_frame()
assert start is not None, "Save Pose shows a frame"
assert ops.poselib.pose_new(name="Auto", new_collection="Arms") == {'FINISHED'}
auto = wm.pose_thumbnail_frame(pose("Auto")["id"])
assert close(auto, start), (auto, start)

# --- Dragging inside moves it; a corner resizes it, square, the corner across staying ------------------------------------
x, y, s = start
assert wm.pose_frame_drag((x, y), (x + 0.5, y - 0.25))
assert close(wm.pose_frame(), (x + 0.5, y - 0.25, s)), wm.pose_frame()
x, y, s = wm.pose_frame()
assert wm.pose_frame_drag((x + s / 2, y + s / 2), (x + s / 2 + 0.4, y + s / 2 + 0.1), reach=0.01)
lo = (x - s / 2, y - s / 2)
assert close(wm.pose_frame(), (lo[0] + (s + 0.4) / 2, lo[1] + (s + 0.4) / 2, s + 0.4)), wm.pose_frame()
assert not wm.pose_frame_drag((x + 50.0, y + 50.0), (0.0, 0.0)), "a press off the frame isn't taken"
wm.pose_frame_open(-1)
assert wm.pose_frame() is None, "closed: no frame"

# --- Saved with a frame: its thumbnail is framed on it, kept in the file --------------------------------------------------
assert ops.poselib.pose_new(name="Framed", collection="Arms", frame_x="0.25", frame_y="-0.5", frame_size="3") == {'FINISHED'}
framed = pose("Framed")["id"]
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), wm.pose_thumbnail_frame(framed)
path = os.path.join(tempfile.gettempdir(), "oa_pose_frame_%d.oanim" % os.getpid())
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
os.remove(path)
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), "kept in the file"
assert close(wm.pose_thumbnail_frame(pose("Auto")["id"]), auto), "one without a frame still fits what it moves"

# --- Edit Frame: shown as given, set again, then back round what it moves ------------------------------------------------
wm.pose_frame_open(framed)
assert close(wm.pose_frame(), (0.25, -0.5, 3.0)), wm.pose_frame()
wm.pose_frame_open(-1)
wm.pose_frame_open(pose("Auto")["id"])
assert close(wm.pose_frame(), auto), "a pose framed on what it moves shows that"
wm.pose_frame_open(-1)
assert ops.poselib.frame_set(pose=str(framed), frame_x="1", frame_y="1", frame_size="0.5") == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), (1.0, 1.0, 0.5))
assert ops.ed.undo() == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), (0.25, -0.5, 3.0)), "an undo step"
assert ops.poselib.frame_set(pose=str(framed), frame_size="0") == {'FINISHED'}
assert close(wm.pose_thumbnail_frame(framed), auto), "frame_size=0: round what it moves again"
assert ops.poselib.frame_set(pose=str(framed), frame_size="0") == {'CANCELLED'}, "nothing to change"
assert ops.poselib.frame_set(pose=str(framed), frame_x="1", frame_y="1", frame_size="-2") == {'CANCELLED'}

# --- The frame holds what was inside it: it goes and scales with those points, grown to hold them if they spread ------
def inside(frame, pts, eps=1e-4):
    x, y, s = frame
    return all(abs(p[0] - x) <= s / 2 + eps and abs(p[1] - y) <= s / 2 + eps for p in pts)


def middle(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


scene()
select_bones("Arm_L")
assert ops.poselib.pose_new(name="Whole", new_collection="Arms") == {'FINISHED'}
whole = pose("Whole")["id"]
p0, p1, p2 = art().shown()[0]
mx, my = middle([p0, p1])
s = max(abs(p0[0] - p1[0]), abs(p0[1] - p1[1])) * 1.5
assert inside((mx, my, s), [p0, p1]) and not inside((mx, my, s), [p2]), "the square holds two of the hand's three points"
assert ops.poselib.pose_new(name="Kept", collection="Arms", frame_x=repr(mx), frame_y=repr(my),
                            frame_size=repr(s)) == {'FINISHED'}
kept = pose("Kept")["id"]
assert close(wm.pose_thumbnail_frame(kept), (mx, my, s)), wm.pose_thumbnail_frame(kept)
assert ops.poselib.frame_set(pose=str(kept), frame_x=repr(mx), frame_y=repr(my), frame_size=repr(s)) == {'CANCELLED'}, \
    "the same square again: nothing to change"

# The whole character moved: the thumbnail's frame and the one shown go with it.
rig().location_x = rig().location_x + 2.0
assert close(wm.pose_thumbnail_frame(kept), (mx + 2.0, my, s)), ("the thumbnail's frame went too", wm.pose_thumbnail_frame(kept))
wm.pose_frame_open(kept)
assert close(wm.pose_frame(), (mx + 2.0, my, s)), ("so did the frame shown", wm.pose_frame())
wm.pose_frame_open(-1)

# Twice as big: so is the frame, still round the same two points.
rig().scale_x = 2.0
rig().scale_y = 2.0
held = art().shown()[0][:2]
f = wm.pose_thumbnail_frame(kept)
assert close(f, middle(held) + (2.0 * s,)), ("scaled with them", f, middle(held), 2.0 * s)

# Another frame with Edit Frame open: it holds them where they show there (the arm lowered).
at(20)
held = art().shown()[0][:2]
wm.pose_frame_open(kept)
assert inside(wm.pose_frame(), held), (wm.pose_frame(), held)
wm.pose_frame_open(-1)
# A pose framed on what it moves: the frame shown is round the hand where it shows there, not where the pose puts it.
wm.pose_frame_open(whole)
assert close(wm.pose_frame()[:2], middle(art().shown()[0])), (wm.pose_frame(), middle(art().shown()[0]))
wm.pose_frame_open(-1)

# --- Points spreading the other way (a mouth opened wide) past a frame off their middle: it grows to hold them -------
scene()
select_bones("Arm_L")
p0, p1, p2 = art().shown()[0]
lo = (min(p0[0], p1[0]), min(p0[1], p1[1]))
hi = (max(p0[0], p1[0]), max(p0[1], p1[1]))
w, h = hi[0] - lo[0], hi[1] - lo[1]
side = max(w, h)
short = 1 if h < w else 0
# The frame shifted along the box's short way, just big enough for both.
c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2]
c[short] += 0.3 * side
half = max(abs(q[k] - c[k]) for q in (p0, p1) for k in (0, 1)) * 1.01
assert not inside((c[0], c[1], 2 * half), [p2]), "the square holds two of the hand's three points"
assert ops.poselib.pose_new(name="Spread", new_collection="Arms", frame_x=repr(c[0]), frame_y=repr(c[1]),
                            frame_size=repr(2 * half)) == {'FINISHED'}
spread = pose("Spread")["id"]
off = ((c[0] - (lo[0] + hi[0]) / 2) / side, (c[1] - (lo[1] + hi[1]) / 2) / side)
ratio = 2 * half / side
# Point 1 pulled the other way along the short side, in the drawing's own space (Arm_L turns it by 0.7 here).
d = [0.0, 0.0]
d[short] = -2.0 * side if p1[short] < p0[short] else 2.0 * side
a = -0.7
local = art().points[1]
art().set_point(1, (local[0] + d[0] * math.cos(a) - d[1] * math.sin(a), local[1] + d[0] * math.sin(a) + d[1] * math.cos(a)))
held = art().shown()[0][:2]
lo2 = (min(q[0] for q in held), min(q[1] for q in held))
hi2 = (max(q[0] for q in held), max(q[1] for q in held))
side2 = max(hi2[0] - lo2[0], hi2[1] - lo2[1])
kept_only = ((lo2[0] + hi2[0]) / 2 + off[0] * side2, (lo2[1] + hi2[1]) / 2 + off[1] * side2, ratio * side2)
assert not inside(kept_only, held), ("the same frame scaled wouldn't hold them", kept_only, held)
f = wm.pose_thumbnail_frame(spread)
assert inside(f, held), ("grown to hold them", f, held)
assert f[2] > kept_only[2], (f, kept_only)

print("test_pose_frame: OK")
