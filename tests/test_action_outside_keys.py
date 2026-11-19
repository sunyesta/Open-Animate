"""While an action of a bone layer is edited, the keys of layers outside it can't be edited: they are the mainline's,
which the action doesn't hold. Edits there aren't auto-keyed, I and Alt I key nothing on them, their rows aren't
shown, and the timeline's key operators (select, delete, move, insert in row, the key buttons) leave them alone. The
bone layer and the layers inside it are keyed as ever.

Run with:  OpenAnimate --background --python tests/test_action_outside_keys.py
"""

import oanim

ops = oanim.ops
L = oanim.data.layers


def scene():
    """A bone layer with a drawing inside it, and a drawing outside keyed on frames 0 and 10; the action "wave" open."""
    ops.wm.read_homefile(confirmed="1")
    doc = oanim.data.document
    doc.auto_key = True
    doc.frame_current = 0
    outside = L.active
    outside.name = "Outside"
    ops.layer.new_bone()
    rig = L.active
    assert ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="") == {'FINISHED'}
    ops.layer.new()
    inside = L.active
    inside.name = "Inside"
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    doc.frame_current = 10
    L.active = outside
    outside.location_x = 3.0
    doc.frame_current = 0
    assert frames(outside) == [0, 10], frames(outside)
    L.active = rig
    assert ops.anim.action_new(name="wave") == {'FINISHED'} and doc.action == "wave"
    return doc, rig, inside, outside


def frames(layer, path="position"):
    return [k["frame"] for k in layer.keyframes(path)]


# --- Edited in the action, a layer outside isn't keyed; one inside is ---------------------------------------------
doc, rig, inside, outside = scene()
L.active = outside
doc.frame_current = 5
outside.location_x = 0.7
doc.frame_current = 6
assert frames(outside) == [0, 10], ("outside it the mainline's keys stay as they were", frames(outside))
L.active = inside
doc.frame_current = 5
inside.location_x = 2.0
doc.frame_current = 6
assert frames(inside) == [0, 5], ("inside the bone layer it keys", frames(inside))
assert ops.anim.action_set(name="") == {'FINISHED'}
assert frames(outside) == [0, 10], frames(outside)

# --- I and Alt I key nothing outside ------------------------------------------------------------------------------
doc, rig, inside, outside = scene()
doc.frame_current = 5
L.active = outside
assert ops.anim.keyframe_insert() == {'CANCELLED'}
assert frames(outside) == [0, 10], frames(outside)
doc.frame_current = 10
assert ops.anim.keyframe_delete() == {'CANCELLED'}
assert frames(outside) == [0, 10], frames(outside)
assert ops.anim.keyframe_toggle(layer=str(outside.id), paths="position") == {'CANCELLED'}
assert frames(outside) == [0, 10], frames(outside)
L.active = inside
doc.frame_current = 5
assert ops.anim.keyframe_insert() == {'FINISHED'} and 5 in frames(inside), frames(inside)

# --- The timeline's key operators leave its keys alone -------------------------------------------------------------
doc, rig, inside, outside = scene()
doc.timeline_only_selected = False
L.active = outside
ops.anim.keys_select(frame_start="10", layers=str(outside.id), path="position")
assert ops.anim.keys_delete() == {'CANCELLED'}
assert frames(outside) == [0, 10], ("not deleted", frames(outside))
ops.anim.keys_select_all()
ops.anim.keys_offset(offset="3")
assert frames(outside) == [0, 10], ("not moved", frames(outside))
assert ops.anim.keys_insert(frame="7", layers=str(outside.id)) == {'CANCELLED'}
assert frames(outside) == [0, 10], ("none put in", frames(outside))
rows = [r["layer"] for r in oanim.wm.timeline_row_details()]
assert outside.id not in rows, ("its row isn't shown", rows)
# Back on the mainline they are its to edit again.
assert ops.anim.action_set(name="") == {'FINISHED'}
L.active = outside
doc.frame_current = 5
assert ops.anim.keyframe_insert() == {'FINISHED'} and frames(outside) == [0, 5, 10], frames(outside)

print("action outside keys: ok")
