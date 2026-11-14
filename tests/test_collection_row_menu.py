"""A Collections row's right-click menu (Armature tab): Assign Selected and Unassign Selected put the selected bones,
and the drawings shown with the bones (Editable in Bone Group) that are picked or have points selected, in that row's
collection or take them out, each showing what it would change ("2 bones, 1 drawing", greyed when nothing); Unassign
takes every bone and layer out of it and keeps it on the panel, empty.

Run with:  OpenAnimate --background --python tests/test_collection_row_menu.py
"""

import oanim

doc = oanim.data.document
layers = oanim.data.layers
ops = oanim.ops.armature
wm = oanim.wm
doc.frame_current = 0

oanim.ops.layer.new_bone()
rig = layers.active
for i, name in enumerate(["jaw", "brow", "ear"]):
    ops.bone_add(name=name, head_x=str(i), head_y="0", tail_x=str(i), tail_y="1", parent="")


def drawing(name, editable):
    oanim.ops.layer.new()
    layer = layers.active
    layer.name = name
    layer.add_curve([(0.0, 2.0), (1.0, 2.0)])
    oanim.ops.layer.move_to_group(group=str(rig.id))
    layer.edit_with_bones = editable
    return layer


mouth = drawing("mouth", True)
shade = drawing("shade", False)


def fresh(layer):
    return next(l for l in layers.all() if l.id == layer.id)


def bone(name):
    return next(b for b in fresh(rig).bones if b["name"] == name)


def pick(bones, drawings):
    """The bones selected in the rig, and the drawings picked in the Layers editor, the rig active."""
    layers.active = fresh(rig)
    ops.select_none()
    for i, n in enumerate(bones):
        fresh(rig).select_bone(n, extend=i > 0)
    for l in (mouth, shade):
        fresh(l).select = l in drawings


def change(assign=True):
    return wm.collection_selected_change(rig, "Eyes", assign)


layers.active = rig
assert ops.collection_add(collection="Eyes") == {'FINISHED'}
assert [c["name"] for c in fresh(rig).bone_collections] == ["All", "Eyes"]

# --- Assign Selected: what it would put in, then puts it in ------------------------------------------------------------
pick(["jaw", "brow"], [mouth, shade])
assert change() == "2 bones, 1 drawing", ("a drawing not shown with the bones can't go in", change())
assert change(False) == "", "nothing selected is in it: Unassign Selected greyed"
assert ops.collection_assign(collection="Eyes") == {'FINISHED'}
assert bone("jaw")["collections"] == ["Eyes"] and bone("brow")["collections"] == ["Eyes"]
assert fresh(mouth).collections == ["Eyes"] and fresh(shade).collections == []
assert bone("ear")["collections"] == [], "not selected"
assert change() == "", "everything selected is in it: Assign Selected greyed"
assert change(False) == "2 bones, 1 drawing"

# Only what would change is counted.
pick(["jaw", "ear"], [])
assert change() == "1 bone" and change(False) == "1 bone", (change(), change(False))

# --- Unassign Selected --------------------------------------------------------------------------------------------------
pick(["jaw"], [mouth])
assert change(False) == "1 bone, 1 drawing", change(False)
assert ops.collection_unassign(collection="Eyes") == {'FINISHED'}
assert bone("jaw")["collections"] == [] and fresh(mouth).collections == []
assert bone("brow")["collections"] == ["Eyes"], "not selected: still in it"

# --- Unassign: empty everywhere, kept on the panel ----------------------------------------------------------------------
pick(["jaw", "ear"], [mouth])
assert ops.collection_assign(collection="Eyes") == {'FINISHED'}
assert ops.collection_unassign_all(collection="Eyes") == {'FINISHED'}
assert all(b["collections"] == [] for b in fresh(rig).bones), [(b["name"], b["collections"]) for b in fresh(rig).bones]
assert fresh(mouth).collections == []
assert "Eyes" in oanim.data.collections, "the collection stays"
assert [c["name"] for c in fresh(rig).bone_collections] == ["All", "Eyes"], "on its panel"
assert ops.collection_unassign_all(collection="Eyes") == {'CANCELLED'}, "nothing in it"
oanim.ops.ed.undo()
assert bone("jaw")["collections"] == ["Eyes"] and fresh(mouth).collections == ["Eyes"], "undone in one step"

print("collection row menu: ok")
