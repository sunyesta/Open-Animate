"""Motion paths: Edit Timing's G and box. G slides the dots picked along their paths (each by the mouse's move, the
keys staying on their frames; dots never pass each other, so one held back by the next gets there once that has
moved). A box dragged from empty space picks the dots inside (never a key, nor a frame outside every stretch); Ctrl
takes them out.

Run with:  OpenAnimate --background --python tests/test_motion_path_dots_grab.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

doc.motion_paths = True
doc.path_before, doc.path_after = 3, 3
doc.auto_key = False
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING", proportional="0") == {'FINISHED'}


def close(a, b, eps=2e-3):
    return abs(a - b) < eps


def where(layer, frame):
    shown = doc.frame_current
    doc.frame_current = frame
    x = layer.location_x
    doc.frame_current = shown
    return x


# A layer going evenly from (0, 0) on 10 to (1, 0) on 20: 0.1 a frame.
ops.layer.new()
l = layers.active
l.add_curve([(0.0, 0.0), (0.1, 0.0)])
doc.frame_current = 0
l.location_x, l.location_y = -5.0, -5.0
for other in layers:
    other.selected = other.id == l.id
layers.active = l
for f, x in ((10, 0.0), (20, 1.0)):
    assert ops.anim.motion_path_move(frame=str(f), x=str(x), y="0", layer=str(l.id)) == {'FINISHED'}
    l.keyframe_set("position", f, interp="LINEAR")
assert ops.anim.motion_path_move(frame="20", x="1", y="0", layer=str(l.id)) == {'FINISHED'}
doc.frame_current = 15
assert close(where(l, 14), 0.4) and close(where(l, 15), 0.5)


def picked():
    return sorted(d["frame"] for d in wm.motion_path_dots())


# --- The box ---------------------------------------------------------------------------------------------------
assert ops.anim.motion_path_select(frame="10", layer=str(l.id)) == {'FINISHED'}
assert any(k["selected"] for k in l.keyframes("position"))
assert ops.anim.motion_path_select_box(box="0.25,-0.1,0.45,0.1") == {'FINISHED'}
assert picked() == [13, 14], picked()
assert not any(k["selected"] for k in l.keyframes("position")), "a box on its own lets the keys go"
assert ops.anim.motion_path_select_box(box="0.55,-0.1,0.65,0.1", extend="1") == {'FINISHED'}
assert picked() == [13, 14, 16], picked()
assert ops.anim.motion_path_select_box(box="0.35,-0.1,0.65,0.1", deselect="1") == {'FINISHED'}
assert picked() == [13], picked()
# Around the key on 10 (and the frames before it, held there): no dot of a stretch.
assert ops.anim.motion_path_select_box(box="-0.05,-0.1,0.05,0.1") == {'FINISHED'}
assert picked() == [], picked()
assert ops.anim.motion_path_select_box(box="0.25,0.45") == {'CANCELLED'}

# --- G -----------------------------------------------------------------------------------------------------------
assert not wm.event_simulate("G", area="Viewport"), "nothing picked to slide"
assert ops.anim.motion_path_select_box(box="0.35,-0.1,0.55,0.1") == {'FINISHED'}
assert picked() == [14, 15], picked()
assert ops.anim.motion_path_brush_set(brush="EDIT") == {'FINISHED'}
assert not ops.anim.motion_path_dots_grab.poll(), "Edit Path's G is the keys'"
assert ops.anim.motion_path_brush_set(brush="EDIT_TIMING") == {'FINISHED'}
assert ops.anim.motion_path_dots_grab.poll()
assert wm.event_simulate("G", area="Viewport"), "G slides the dots picked"

# Both on by 0.2: 14 pushes 15 along (never past it), and 15 then goes on to its own place.
assert ops.anim.motion_path_dots_slide(x="0.2", y="0") == {'FINISHED'}
assert close(where(l, 14), 0.6, 0.01) and close(where(l, 15), 0.7, 0.01), (where(l, 14), where(l, 15))
assert close(where(l, 13), 0.3, 0.01), "without O the others stay"
assert close(where(l, 10), 0.0) and close(where(l, 20), 1.0), "the keys stay"
assert doc.frame_current == 15, "the frame shown stays"
assert ops.ed.undo() == {'FINISHED'}
assert close(where(l, 14), 0.4) and close(where(l, 15), 0.5), "one undo step"

# With proportional editing: the dots around go too, by the falloff, but each picked dot still lands where it is
# taken (15's slide moving 14 along again is put right).
assert ops.anim.motion_path_dots_slide(x="0.2", y="0", proportional="1", size="3") == {'FINISHED'}
assert close(where(l, 14), 0.6, 0.005) and close(where(l, 15), 0.7, 0.005), (where(l, 14), where(l, 15))
assert where(l, 13) > 0.35 and where(l, 16) > 0.65, (where(l, 13), where(l, 16))
assert ops.ed.undo() == {'FINISHED'}

ops.anim.motion_path_select(none="1")
assert ops.anim.motion_path_dots_slide.poll() is False

print("test_motion_path_dots_grab: ok")
