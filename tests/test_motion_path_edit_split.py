"""Motion paths: Edit Path and Edit Timing, the tool's two clicking brushes.

Edit Path (brush EDIT) takes the keys, handles and control points: where the path goes. Its dots take no clicks (only
Alt's, adding on the path, and a double click going to their frame). Edit Timing (EDIT_TIMING) takes only the dots:
when the path gets there; its keys and handles take no clicks, and Alt adds nothing. G R S, V and X are Edit Path's,
O (proportional editing of dots) Edit Timing's.

Run with:  OpenAnimate --background --python tests/test_motion_path_edit_split.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

doc.motion_paths = True
doc.auto_key = False
assert ops.wm.tool_motion_path() == {'FINISHED'}

# The brushes: Edit Path (still EDIT, as scripts have it) and Edit Timing, neither with a circle of its own.
assert wm.path_brush_settings()["brush"] == "EDIT"
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
s = wm.path_brush_settings()
assert s["brush"] == "EDIT_TIMING", s
assert "EDIT" not in s["brushes"] and "EDIT_TIMING" not in s["brushes"], s["brushes"]

# What a press on the path is each one's to take.
assert wm.motion_path_press_taken("EDIT", True, False), "Edit Path takes a key"
assert not wm.motion_path_press_taken("EDIT", False, False), "Edit Path leaves a dot"
assert wm.motion_path_press_taken("EDIT", False, True), "Edit Path's Alt adds on the path"
assert wm.motion_path_press_taken("EDIT_TIMING", False, False), "Edit Timing takes a dot"
assert not wm.motion_path_press_taken("EDIT_TIMING", True, False), "Edit Timing leaves a key"
assert not wm.motion_path_press_taken("EDIT_TIMING", False, True), "Edit Timing adds nothing"

# A layer keyed on 10 and 20, its key on 20 selected.
ops.layer.new()
l = layers.active
l.add_curve([(0.0, 0.0), (0.1, 0.0)])
for other in layers:
    other.selected = other.id == l.id
layers.active = l
for f, (x, y) in {10: (0.0, 0.0), 20: (1.0, 0.0)}.items():
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y=str(y), layer=str(l.id)) == {'FINISHED'}
doc.frame_current = 15
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
assert ops.anim.motion_path_select(frame="20", layer=str(l.id)) == {'FINISHED'}

# G R S, V and X on the keys: Edit Path's, not Edit Timing's.
for idname in ("motion_path_keys_grab", "motion_path_handles_menu", "motion_path_keys_delete"):
    assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
    assert not getattr(ops.anim, idname).poll(), idname + " with Edit Timing"
    assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
    assert getattr(ops.anim, idname).poll(), idname + " with Edit Path"

# Edit Path's double click on a dot: only its frame, nothing picked.
assert ops.anim.motion_path_select(none="1") == {'FINISHED'}
assert ops.anim.motion_path_select(frame="13", layer=str(l.id), go="1", pick="0") == {'FINISHED'}
assert doc.frame_current == 13
assert not wm.motion_path_dots(), wm.motion_path_dots()
assert not any(k["selected"] for k in l.keyframes("position")), "nothing picked"

# Dots are Edit Timing's: Edit Path lets go of those picked (it neither shows nor picks them); keys stay picked.
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
assert ops.anim.motion_path_select(frame="13", layer=str(l.id)) == {'FINISHED'}
assert ops.anim.motion_path_select(frame="20", layer=str(l.id), extend="1") == {'FINISHED'}
assert [d["frame"] for d in wm.motion_path_dots()] == [13], wm.motion_path_dots()
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
assert not wm.motion_path_dots(), "Edit Path picks no dots"
assert any(k["selected"] and k["frame"] == 20 for k in l.keyframes("position")), "the key stays picked"
assert ops.anim.motion_path_select(none="1") == {'FINISHED'}

# Edit Path's dots are the path's own colour, whatever the dot colours say; Edit Timing's show the timing.
doc.path_dot_colors = "TIMING_ALL"
p = next(p for p in wm.motion_paths() if p["layer"] == l.id)
assert all(all(abs(a - b) < 1e-4 for a, b in zip(c[:3], p["color"])) for c in p["dot_colors"]), "Edit Path"
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
p = next(p for p in wm.motion_paths() if p["layer"] == l.id)
assert not all(all(abs(a - b) < 1e-4 for a, b in zip(c[:3], p["color"])) for c in p["dot_colors"]), "Edit Timing"
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
doc.path_dot_colors = "TIMING_CURRENT"

# O, proportional editing of the dots: Edit Timing's.
ops.layer.new()
empty = layers.active
for other in layers:
    other.selected = other.id == empty.id
assert ops.anim.motion_path_brush_set(brush="EDIT", proportional="0") == {'FINISHED'}
assert not oanim.wm.event_simulate("O", area="Viewport"), "Edit Path has no dots to slide"
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
assert oanim.wm.event_simulate("O", area="Viewport")
assert wm.path_brush_settings()["proportional"]

print("test_motion_path_edit_split: ok")
