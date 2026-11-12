"""Editing one path keeps what actions add to the other paths shown (a lip edited beside an ear a head turn moves).

What the actions add to a bone or a point is kept with the document it came from, and used while that stays the same
but for the target's own keys. Every other path shown missed it whenever a drawing's keys changed: the lip's handle
moved, the ear's path was worked out frame by frame, side by side on copies, every step of the drag. A drawing no bone
is posed from (no Limit Shape, Look At eye shape, Follow Point or driver reads it, nor anything made from it) changes
neither the actions bones play nor what they add, so its keys, and a reference's copy of them, no longer count. One a
bone is kept inside still does: there the ear's path is worked out again, as working everything out has it.

Run with:  OpenAnimate --background --python tests/test_motion_path_offsets_other_paths.py
"""

import math

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def go(frame):
    """Settle on `frame` (setting the frame it is already on doesn't work it out again)."""
    doc.frame_current = frame + 1
    doc.frame_current = frame


def build(reference=False, limit_shape=False):
    ops.wm.read_homefile()
    doc.auto_key = True
    go(0)
    ops.layer.new_bone()
    rig = layers.active
    assert ops.armature.bone_add(name="ear", head_x="3", head_y="0", tail_x="4", tail_y="0") == {'FINISHED'}
    ops.armature.select_none()
    assert ops.armature.bone_add(name="eye", head_x="0", head_y="0", tail_x="1", tail_y="0") == {'FINISHED'}
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    ops.layer.new()
    art = layers.active
    art.key_whole_drawing = False
    art.key_together = False
    ops.layer.move_to_group(group=str(rig.id))
    art.add_curve([(2.0, 2.0), (2.5, 2.0), (2.5, 2.5), (2.0, 2.5)], closed=True)
    # The knob's action reshapes the drawing and turns the ear.
    layers.active = rig
    assert ops.anim.action_new(name="go_r") == {'FINISHED'}
    doc.frame_current = 40
    rig.bone_set("ear", angle=0.9)
    go(40)
    layers.active = art
    art.set_point(1, (2.9, 2.3))
    go(40)
    doc.action = ""
    go(0)
    layers.active = rig
    ops.armature.select_none()
    rig.select_bone("eye")
    assert ops.armature.controller_side(side="RIGHT", action="go_r") == {'FINISHED'}
    for f, x in ((10, 0.0), (30, 40.0), (50, 12.0)):
        doc.frame_current = f
        rig.bone_set("eye", knob=(x, 0.0))
        go(f)
    if limit_shape:
        # The ear's tip kept inside the drawing: its keys pose the ear.
        assert ops.armature.constraint_add(type="LIMIT_SHAPE", bone="ear") == {'FINISHED'}
        rig.bone_constraint_set("ear", len(rig.bone_constraints("ear")) - 1, shape_layer=art.name, fit="CENTER")
    # The point's own keys on the mainline.
    layers.active = art
    doc.frame_current = 20
    art.set_point(1, (2.4, 2.4))
    go(20)
    if reference:
        assert ops.layer.make_reference() == {'FINISHED'}
        assert layers.active.reference_source is not None
        layers.active = art
    doc.auto_key = False
    doc.motion_paths = True
    doc.path_own_motion = True
    doc.path_all = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    # The ear's paths shown beside the point's: its layer picked, the ear selected.
    ops.armature.select_none()
    rig.select_bone("ear")
    rig.selected = True
    art.select_points([1])
    go(20)
    point = art.point_ids[1]
    assert ops.anim.motion_path_select(frame="20", layer=str(art.id), point=str(point)) == {'FINISHED'}
    return art, point


def edit(shortcuts, **kw):
    """Every path shown after the point's key and handle are moved a few times, and the places' counts for the moves."""
    art, point = build(**kw)
    wm.motion_path_own_from_keys(shortcuts)
    paths = wm.motion_paths()
    labels = [p["label"] for p in paths]
    assert len(paths) == 3 and all(p["own_motion"] for p in paths), labels
    mine = next(p for p in paths if p["layer"] == art.id)
    tip = next(h for h in mine["handles"] if h["frame"] == 20)["in"]
    dot = mine["points"][20 - mine["first"]]
    wm.motion_path_places_clear()
    for i in range(1, 4):
        # Its key on the frame shown dragged (the point moves there, and in the reference's copy), then a handle.
        assert ops.anim.motion_path_move(layer=str(art.id), point=str(point), frame="20", x=str(dot[0] + 0.04 * i),
                                         y=str(dot[1] - 0.03 * i)) == {'FINISHED'}
        paths = wm.motion_paths()
        assert ops.anim.motion_path_handle(layer=str(art.id), point=str(point), frame="20", side="IN",
                                           x=str(tip[0] - 0.05 * i), y=str(tip[1] + 0.03 * i)) == {'FINISHED'}
        paths = wm.motion_paths()
    counts = wm.motion_path_places()
    wm.motion_path_own_from_keys(True)
    return paths, counts


def worst(a, b):
    gap = 0.0
    for p, q in zip(a, b):
        assert p["label"] == q["label"] and len(p["points"]) == len(q["points"]) > 40, (p["label"], q["label"])
        gap = max([gap] + [math.dist(x, y) for x, y in zip(p["points"], q["points"])])
    return gap


def moved(path):
    return max(math.dist(p, path["points"][0]) for p in path["points"])


for reference in (False, True):
    fast, counts = edit(True, reference=reference)
    full, full_counts = edit(False, reference=reference)
    # (The point and the ear's tip; its head stays where it turns about.)
    assert sum(moved(p) > 0.3 for p in full) == 2, ("the knob's action moves them", [moved(p) for p in full])
    gap = worst(fast, full)
    assert gap < 1e-4, ("as working everything out", reference, gap)
    # Every frame of every path after each move from keys and what the actions add, kept: none worked out.
    assert counts["frames"] > 0 and counts["offsets"] == counts["frames"], (reference, counts)

# The ear kept inside the drawing: the point's keys pose it, so its path is worked out again, as in full.
fast, counts = edit(True, limit_shape=True)
full, full_counts = edit(False, limit_shape=True)
gap = worst(fast, full)
assert gap < 1e-4, ("a bone kept inside the drawing", gap)
assert counts["offsets"] < counts["frames"], counts

print("Motion path offsets of other paths tests passed")
