"""A point actions move (a lip a head turn's knob reshapes): its Own Motion path quick to edit.

Its path was worked out frame by frame on whole copies of the document, every action of the rig played on each, every
time its handles moved. What the actions add to it on each frame is now kept (as for a bone actions move), with the
document it came from: while that stays the same but for the point's own keys (and the copies of them references of
its layer hold), its path comes from its keys and what was kept, no frame worked out. Worked out, its frames go values
only where its actions play from bones' own values. Either way it comes out as working everything out does; a knob
that plays where it is posed (swinging on a hair with dynamics) is worked out in full.

Run with:  OpenAnimate --background --python tests/test_motion_path_point_actions_fast.py
"""

import math

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def go(frame):
    """Settle on `frame` (setting the frame it is already on doesn't work it out again)."""
    doc.frame_current = frame + 1
    doc.frame_current = frame


def build(reference=False, knob_on_hair=False, kept_inside=False):
    ops.wm.read_homefile()
    doc.auto_key = True
    go(0)
    ops.layer.new_bone()
    rig = layers.active
    if knob_on_hair:
        assert ops.armature.bone_add(name="Hair", head_x="-3", head_y="0", tail_x="-3", tail_y="2") == {'FINISHED'}
        ops.armature.select_none()
    assert ops.armature.bone_add(name="eye", head_x="0", head_y="0", tail_x="1", tail_y="0",
                                 parent="Hair" if knob_on_hair else "") == {'FINISHED'}
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    ops.layer.new()
    art = layers.active
    art.key_whole_drawing = False
    art.key_together = False
    ops.layer.move_to_group(group=str(rig.id))
    art.add_curve([(2.0, 2.0), (2.5, 2.0), (2.5, 2.5)])
    # The knob's action reshapes the drawing: point 1 moved at its end.
    layers.active = art
    assert ops.anim.action_new(name="go_r") == {'FINISHED'}
    doc.frame_current = 40
    art.set_point(1, (2.9, 2.3))
    go(40)
    doc.action = ""
    go(0)
    layers.active = rig
    ops.armature.select_none()
    rig.select_bone("eye")
    assert ops.armature.controller_side(side="RIGHT", action="go_r") == {'FINISHED'}
    if knob_on_hair:
        # Played where it is posed: where the hair, swinging, takes it.
        assert ops.armature.bone_relations_set(bone="eye", knob_independent="1") == {'FINISHED'}
    for f, x in ((10, 0.0), (30, 40.0), (50, 12.0)):
        doc.frame_current = f
        rig.bone_set("eye", knob=(x, 0.0))
        go(f)
    if knob_on_hair:
        ops.armature.select_none()
        rig.select_bone("Hair")
        for f, turn in ((0, 0.0), (8, 1.2), (14, -0.4)):
            doc.frame_current = f
            rig.bone_set("Hair", angle=math.pi / 2 + turn)
            go(f)
        assert ops.armature.constraint_add(type="DYNAMICS", bone="Hair") == {'FINISHED'}
    # The point's own keys on the mainline.
    layers.active = art
    doc.frame_current = 20
    art.set_point(1, (2.4, 2.4))
    go(20)
    if reference:
        assert ops.layer.make_reference() == {'FINISHED'}
        assert layers.active.reference_source is not None
        copy = layers.active
        if kept_inside:
            # A bone kept inside the reference (Limit Shape): the point's keys, and the reference's copies of them,
            # then count.
            go(0)
            layers.active = rig
            ops.armature.select_none()
            assert ops.armature.bone_add(name="lid", head_x="2.2", head_y="2.2", tail_x="2.3",
                                         tail_y="2.2") == {'FINISHED'}
            assert ops.armature.constraint_add(type="LIMIT_SHAPE", bone="lid") == {'FINISHED'}
            rig.bone_constraint_set("lid", len(rig.bone_constraints("lid")) - 1, shape_layer=copy.name, fit="CENTER")
            go(20)
        layers.active = art
    doc.auto_key = False
    doc.motion_paths = True
    doc.path_own_motion = True
    doc.path_all = True
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    art.select_points([1])
    go(20)
    point = art.point_ids[1]
    assert point != 0
    assert ops.anim.motion_path_select(frame="20", layer=str(art.id), point=str(point)) == {'FINISHED'}
    return art, point


def edit(shortcuts, **kw):
    """The point's path and handles after its handle is moved a few times, and the places' counts for the moves."""
    art, point = build(**kw)
    wm.motion_path_own_from_keys(shortcuts)
    paths = wm.motion_paths()
    assert len(paths) == 1 and paths[0]["own_motion"], paths
    start = next(h for h in paths[0]["handles"] if h["frame"] == 20)
    tip = start["in"]
    wm.motion_path_places_clear()
    for i in range(1, 4):
        assert ops.anim.motion_path_handle(layer=str(art.id), point=str(point), frame="20", side="IN",
                                           x=str(tip[0] - 0.05 * i), y=str(tip[1] + 0.03 * i)) == {'FINISHED'}
        paths = wm.motion_paths()
    counts = wm.motion_path_places()
    wm.motion_path_own_from_keys(True)
    return paths[0], counts


def worst(a, b):
    assert len(a["points"]) == len(b["points"]) and len(a["points"]) > 40, (len(a["points"]), len(b["points"]))
    gap = max(math.dist(p, q) for p, q in zip(a["points"], b["points"]))
    for h, k in zip(a["handles"], b["handles"]):
        assert h["frame"] == k["frame"], (a["handles"], b["handles"])
        for side in ("in", "out"):
            if h[side] or k[side]:
                gap = max(gap, math.dist(h[side], k[side]))
    return gap


def moved(path):
    """How far the actions take the point at most (so a path that left them out shows)."""
    return max(math.dist(p, path["points"][0]) for p in path["points"])


for reference, kept_inside in ((False, False), (True, False), (True, True)):
    fast, counts = edit(True, reference=reference, kept_inside=kept_inside)
    full, full_counts = edit(False, reference=reference, kept_inside=kept_inside)
    assert moved(full) > 0.3, ("the knob's action moves the point", moved(full))
    gap = worst(fast, full)
    assert gap < 1e-4, ("as working everything out", reference, gap)
    # Every frame of the path after each move from its keys and what the actions add, kept: none worked out.
    assert counts["frames"] > 0 and counts["offsets"] == counts["frames"], (reference, counts)
    assert full_counts["offsets"] == 0, full_counts

# Played where it is posed (on a hair with dynamics): worked out in full, as working everything out has it.
fast, counts = edit(True, knob_on_hair=True)
full, full_counts = edit(False, knob_on_hair=True)
gap = worst(fast, full)
assert gap < 1e-4, ("a knob played where it is posed", gap)
assert counts["offsets"] == 0, counts

print("Point actions fast path tests passed")
