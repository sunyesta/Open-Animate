"""Keys moved in the timeline: a move left past frame 1 stops there with the keys' spacing kept (each held at frame 1
on its own, two landed on one frame and one was lost), and so do copies; a key dragged in the timeline shows the
frame as its keys now have it; undo leaves the timeline's filters and Lock as they are (they're set with no undo
step); an edit that changes nothing pushes no undo step on another frame either.

Run with:  OpenAnimate --background --python tests/test_timeline_key_moves.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def scene(keys=((5, 1.0), (10, 2.0), (20, 3.0))):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc.auto_key = True
    ops.layer.new()
    lay = layers.active
    for f, x in keys:
        doc.frame_current = f
        lay.location_x = x
    doc.frame_current = 0
    return lay


def keys(lay):
    return [(k['frame'], round(k['value'][0], 4)) for k in lay.keyframes('position')]


# --- Moved left past frame 1: they stop there together ---------------------------------------------------------------
lay = scene()
assert ops.anim.keys_select(frame_start="5", frame_end="10", layers=str(lay.id), path="position") == {'FINISHED'}
assert ops.anim.keys_offset(frames="-10") == {'FINISHED'}
assert keys(lay) == [(0, 0.0), (1, 1.0), (6, 2.0), (20, 3.0)], keys(lay)
# Already there: a move further left changes nothing, no undo step.
steps = wm.undo_history()[1]
assert ops.anim.keys_offset(frames="-3") == {'CANCELLED'}
assert wm.undo_history()[1] == steps
assert keys(lay) == [(0, 0.0), (1, 1.0), (6, 2.0), (20, 3.0)], keys(lay)
# Scaled down past it too.
lay = scene()
assert ops.anim.keys_select(frame_start="5", frame_end="20", layers=str(lay.id), path="position") == {'FINISHED'}
doc.frame_current = 30
assert ops.anim.keys_scale(factor="2") == {'FINISHED'}
assert [f for f, _ in keys(lay)] == [0, 1, 11, 31], keys(lay)

# --- Copies past frame 1 ---------------------------------------------------------------------------------------------
lay = scene()
assert ops.anim.keys_select(frame_start="5", frame_end="10", layers=str(lay.id), path="position") == {'FINISHED'}
assert ops.anim.keys_duplicate(frames="-10") == {'FINISHED'}
assert keys(lay) == [(0, 0.0), (1, 1.0), (5, 1.0), (6, 2.0), (10, 2.0), (20, 3.0)], keys(lay)

# --- A key dragged in the timeline: the frame shown as its keys have it -----------------------------------------------
lay = scene(((10, 1.0), (30, 3.0)))
for l in layers.all():
    l.selected = l.id == lay.id
layers.active = lay
doc.frame_current = 20
assert abs(lay.location_x - 2.0) < 1e-4, lay.location_x
rows = wm.timeline_row_details(as_shown=True)
row = next(i for i, r in enumerate(rows) if 30 in r['frames'] and r['label'] == lay.name)
assert wm.timeline_key_press(row, 30, 25)
assert 25 in [k['frame'] for k in lay.keyframes('position')]
shown = lay.location_x
doc.frame_current = 21
doc.frame_current = 20
assert abs(shown - lay.location_x) < 1e-5 and abs(shown - 2.0) > 0.01, ("the frame shown after the drag", shown,
                                                                          lay.location_x)

# --- Undo leaves the timeline's filters and Lock ---------------------------------------------------------------------
lay = scene()
doc.frame_current = 10
assert ops.anim.keyframe_insert() == {'FINISHED'}
assert ops.anim.timeline_filter(only_selected="0", show="ALL", search="loc") == {'FINISHED'}
assert ops.anim.timeline_lock(lock="1") == {'FINISHED'}
set_to = (doc.timeline_only_selected, doc.timeline_lock, len(wm.timeline_rows()))
doc.frame_current = 15
assert ops.anim.keyframe_insert() == {'FINISHED'}
assert ops.ed.undo() == {'FINISHED'}
assert (doc.timeline_only_selected, doc.timeline_lock, len(wm.timeline_rows())) == set_to
assert ops.ed.redo() == {'FINISHED'}
assert (doc.timeline_only_selected, doc.timeline_lock, len(wm.timeline_rows())) == set_to

# --- Nothing changed on another frame: no undo step -------------------------------------------------------------------
lay = scene()
assert ops.anim.keys_select(frame_start="10", layers=str(lay.id), path="position") == {'FINISHED'}
assert ops.anim.keys_interpolation_set(interp="LINEAR") == {'FINISHED'}
doc.frame_current = 15
steps = wm.undo_history()[1]
assert ops.anim.keys_interpolation_set(interp="LINEAR") == {'FINISHED'}
assert wm.undo_history()[1] == steps, "a key type it already has, on another frame: no step"
# A real change there still is one, and undoes.
assert ops.anim.keys_interpolation_set(interp="STEP") == {'FINISHED'}
assert wm.undo_history()[1] == steps + 1
assert ops.ed.undo() == {'FINISHED'}
assert [k['interp'] for k in lay.keyframes('position') if k['frame'] == 10] == ['LINEAR']

print("test_timeline_key_moves: ok")
