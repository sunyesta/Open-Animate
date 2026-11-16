"""The Layer tab's Bone Group panel, on a drawing inside a bone layer: Editable in Bone Group and Bone Color (the colour
its wires and points are drawn in while edited with the bones), greyed while Editable in Bone Group is off but still
settable. Edits go to the active drawing and every other drawing inside a bone layer picked in the Layers editor.

Run with:  OpenAnimate --background --python tests/test_layer_bone_group_panel.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm

assert ops.wm.read_homefile() == {'FINISHED'}
doc, layers = oanim.data.document, oanim.data.layers
doc.frame_current = 0


def find(name):
    return next(l for l in layers.all() if l.name == name)


def pick(*names):
    for l in layers.all():
        l.selected = l.name in names
    layers.active = find(names[0])


# A drawing outside any bone layer: no panel.
assert ops.layer.new() == {'FINISHED'}
layers.active.name = "Loose"
pick("Loose")
assert wm.layer_bone_group_panel() is None, "only drawings inside a bone layer have it"

# Three drawings inside a bone layer.
assert ops.layer.new_bone() == {'FINISHED'}
layers.active.name = "Rig"
rig_id = layers.active.id
for name in ("Arm", "Hand", "Leg"):
    assert ops.layer.new() == {'FINISHED'}
    layers.active.name = name
    assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}

pick("Arm")
panel = wm.layer_bone_group_panel()
assert panel is not None, "a drawing inside a bone layer has the panel"
assert panel["drawings"] == ["Arm"], panel
assert panel["color_active"] is False, ("Bone Color greyed while Editable in Bone Group is off", panel)

# Greyed is still settable: the colour is kept while off.
assert ops.layer.color_set(color_set="THEME04", layers=str(find("Arm").id)) == {'FINISHED'}
assert find("Arm").color_set == "THEME04"

# Picked with others: the active one first, then the others inside a bone layer; Loose isn't one.
pick("Hand", "Arm", "Loose")
panel = wm.layer_bone_group_panel()
assert panel["drawings"][0] == "Hand" and sorted(panel["drawings"]) == ["Arm", "Hand"], panel

# The toggle goes to them all, as one undo step, and lights Bone Color.
assert ops.layer.edit_with_bones_set(on="1") == {'FINISHED'}
assert find("Hand").edit_with_bones and find("Arm").edit_with_bones and not find("Leg").edit_with_bones
assert not find("Loose").edit_with_bones, "a drawing outside a bone layer isn't touched"
assert wm.layer_bone_group_panel()["color_active"] is True
names, index = wm.undo_history()
assert names[index] == "Editable in Bone Group", names[index]
assert ops.layer.edit_with_bones_set(on="1") == {'CANCELLED'}, "already on: nothing to do"
assert ops.ed.undo() == {'FINISHED'}
assert not find("Hand").edit_with_bones and not find("Arm").edit_with_bones

# The colour goes to them all too, the way the panel sends it.
ids = ",".join(str(find(n).id) for n in panel["drawings"])
assert ops.layer.color_set(color_set="THEME07", layers=ids) == {'FINISHED'}
assert find("Hand").color_set == "THEME07" and find("Arm").color_set == "THEME07"
assert find("Leg").color_set == "DEFAULT"

print("layer bone group panel: ok")
