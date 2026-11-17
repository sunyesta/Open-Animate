"""Alt G, Alt R and Alt S clear the picked bones of the sub bone groups inside the active bone layer too, as G, R and S
move them (the teeth's bone picked in a mouth group stayed where it was: only the active bone layer's were cleared, and
with none picked there Alt G went to the points).

Run with:  OpenAnimate --background --python tests/test_clear_sub_group_bones.py
"""

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0

assert ops.layer.new_bone() == {'FINISHED'}
rig_id = layers.active.id
assert ops.armature.bone_add(name="Head", head_x="0", head_y="0", tail_x="0", tail_y="1", parent="") == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
mouth_id = layers.active.id
assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}


def layer(i):
    return next(l for l in layers.all() if l.id == i)


layers.active = layer(mouth_id)
assert ops.armature.bone_add(name="Teeth", head_x="0", head_y="-0.5", tail_x="0.3", tail_y="-0.5", parent="") == \
    {'FINISHED'}
layer(mouth_id).sub_bone_group = True


def teeth():
    return next(b for b in layer(mouth_id).bones if b["name"] == "Teeth")


def head():
    return next(b for b in layer(rig_id).bones if b["name"] == "Head")


rest_pos, rest_angle, rest_scale = teeth()["position"], teeth()["angle"], teeth()["scale"]
head_rest = head()["position"]


def close(a, b, eps=1e-5):
    if isinstance(a, (tuple, list)):
        return all(abs(x - y) < eps for x, y in zip(a, b))
    return abs(a - b) < eps


def posed():
    """Frame 10, the teeth moved, turned and scaled and picked with nothing else (the bone layer around them active),
    the head moved but not picked."""
    doc.frame_current = 10
    layer(mouth_id).bone_set("Teeth", position=(rest_pos[0] + 0.2, rest_pos[1] - 0.1), angle=rest_angle + 0.4,
                             scale=(rest_scale[0] * 1.5, rest_scale[1] * 1.5))
    layer(rig_id).bone_set("Head", position=(head_rest[0] + 0.3, head_rest[1]))
    doc.frame_current = 11
    doc.frame_current = 10
    layers.active = layer(rig_id)
    ops.armature.select_none()
    layer(mouth_id).select_bone("Teeth")
    assert not any(b["selected"] for b in layer(rig_id).bones)
    assert not close(teeth()["position"], rest_pos)


# --- Alt G: the sub group's picked bone back where it rests; the head, not picked, left alone -------------------------
posed()
assert ops.armature.clear_location() == {'FINISHED'}, "a sub bone group's picked bone is cleared"
assert close(teeth()["position"], rest_pos), (teeth()["position"], rest_pos)
assert close(teeth()["angle"], rest_angle + 0.4), "only its location"
assert close(head()["position"], (head_rest[0] + 0.3, head_rest[1])), "the head isn't picked"
assert oanim.wm.undo_history()[0][-1] == "Clear Location", oanim.wm.undo_history()[0][-1]
ops.ed.undo()

# --- Alt R and Alt S ----------------------------------------------------------------------------------------------------
posed()
assert ops.armature.clear_rotation() == {'FINISHED'}
assert close(teeth()["angle"], rest_angle), (teeth()["angle"], rest_angle)
ops.ed.undo()
posed()
assert ops.armature.clear_scale() == {'FINISHED'}
assert close(teeth()["scale"], rest_scale), (teeth()["scale"], rest_scale)
ops.ed.undo()

# --- Nothing picked anywhere: nothing to clear ------------------------------------------------------------------------
posed()
layers.active = layer(mouth_id)
ops.armature.select_none()
layers.active = layer(rig_id)
ops.armature.select_none()
assert not any(b["selected"] for l in (layer(rig_id), layer(mouth_id)) for b in l.bones)
assert ops.armature.clear_location() == {'CANCELLED'}

print("clear sub group bones ok")
