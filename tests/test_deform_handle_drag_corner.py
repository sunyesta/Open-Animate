"""Dragging a handle on a drawing bent by a Cage Deform, at a corner of the cage: the handle's end goes where it is taken
and the outline moves about as far as the drag. At a corner the deform bends a handle differently each way it points,
so a handle settled by the point's one stretch overshot (a 0.006 drag stored a handle turned most of a right angle, the
outline moving 0.035). With a Resample before the deform the handles shown and dragged are the drawing's own, bent at
their points, not the point's stretch of them.

Run with:  OpenAnimate --background --python tests/test_deform_handle_drag_corner.py
"""

import math

import oanim

ops, wm = oanim.ops, oanim.wm

# A pants leg's front, its corner point 2 pulled up on frame 10; the back drawn the same, bent by the front as a cage.
REST = [(0.078526, -0.473149), (0.093325, -0.542029), (0.004325, -0.562576), (0.002528, -0.494025)]
REST_HANDLES = [((0.061020, -0.413261), (0.082125, -0.485462)), ((0.094006, -0.529625), (0.092865, -0.550406)),
                ((0.021257, -0.565898), (0.002946, -0.562306)), ((0.002569, -0.508485), (0.002358, -0.434261))]
POSE_2 = (0.007282, -0.527301)
POSE_HANDLES = {1: ((0.086995, -0.509393), (0.082620, -0.522501)), 2: ((0.024736, -0.488556), (0.006705, -0.528582))}


def find(name):
    return next(l for l in oanim.data.layers.all() if l.name == name)


def scene(resample):
    ops.wm.read_homefile(confirmed="1")
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0
    for name in ("Front", "Back"):
        ops.layer.new()
        layers.active.name = name
        layers.active.add_curve(REST, closed=True, fill=True)
        for i, (h_in, h_out) in enumerate(REST_HANDLES):
            layers.active.place_handle(0, i, "IN", h_in, keep_other=True)
            layers.active.place_handle(0, i, "OUT", h_out, keep_other=True)
    front, back = find("Front"), find("Back")
    layers.active = back
    if resample:
        assert ops.object.modifier_add(type="RESAMPLE") == {'FINISHED'}
        back.modifier_set(0, split="COUNT", pieces=4)
    assert ops.object.modifier_add(type="CAGE_DEFORM") == {'FINISHED'}
    back.modifier_set(len(back.modifiers) - 1, layer="Front", shape=front.shapes[0][0], cage_method="ENVELOPE")
    doc.auto_key = True
    doc.frame_current = 10
    layers.active = front
    front.set_point(2, POSE_2)
    for i, (h_in, h_out) in POSE_HANDLES.items():
        front.place_handle(0, i, "IN", h_in, keep_other=True)
        front.place_handle(0, i, "OUT", h_out, keep_other=True)
    doc.frame_current = 11
    doc.frame_current = 10
    layers.active = back
    return front, back


def far(a, b):
    return max(min(math.dist(p, q) for q in b) for p in a)


def drags(resample):
    front, back = scene(resample)
    on = far(back.evaluated_outline(0, 32)[0], front.evaluated_outline(0, 32)[0])
    assert on < 0.005, ("the back sits on its cage", resample, on)
    for idx, side, move in ((1, "OUT", (-0.006, 0.0)), (1, "OUT", (0.0, -0.006)), (2, "IN", (0.006, 0.0)),
                            (2, "IN", (0.0, 0.006))):
        front, back = scene(resample)
        before = back.evaluated_outline(0, 32)[0]
        end = wm.handle_ends_shown(back)[idx][0 if side == "IN" else 1]
        ops.mesh.select_none()
        back.select_handle(0, idx, side)
        assert ops.mesh.translate(move_x=repr(move[0]), move_y=repr(move[1])) == {'FINISHED'}
        after = back.evaluated_outline(0, 32)[0]
        now = wm.handle_ends_shown(back)[idx][0 if side == "IN" else 1]
        want = (end[0] + move[0], end[1] + move[1])
        off = math.dist(now, want)
        moved = max(far(after, before), far(before, after))
        assert off < 0.002, ("the handle's end where it was taken", resample, idx, side, move, off)
        assert moved < 0.006, ("the outline moved about as far as the drag", resample, idx, side, move, moved)


# --- Cage Deform alone: a handle dragged at the cage's corner lands where it is taken ----------------------------------
drags(False)

# --- A Resample before the Cage Deform: the handles shown are the drawing's own, bent at their points ------------------
drags(True)

print("deform handle drag corner: ok")
