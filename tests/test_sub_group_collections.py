"""A drawing inside a sub bone group, worked with the bone layer around it, shows only while every collections
panel on the way shows it: the one of the bone layer worked in and each sub bone group's down to its own. Hiding a
collection in the outer panel hides the inner group's drawings in it (the Tongue in Secondary, hidden in Character's
panel, kept its wire while the mouth group's own panel showed All).

Run with:  OpenAnimate --background --python tests/test_sub_group_collections.py
"""

import oanim

doc, layers, ops, wm = oanim.data.document, oanim.data.layers, oanim.ops, oanim.wm
doc.frame_current = 0


def fresh(l):
    return next(x for x in layers.all() if x.id == l.id)


def rig_in(name, parent=None):
    if parent:
        layers.active = parent
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    rig.name = name
    if parent:
        assert ops.layer.move_to_group(group=str(parent.id)) == {'FINISHED'}
        layers.active = fresh(rig)
    return fresh(rig)


def drawing_in(name, parent, y, collection):
    layers.active = fresh(parent)
    assert ops.layer.new() == {'FINISHED'}
    d = layers.active
    d.name = name
    d.add_curve([(0.0, y), (1.0, y)])
    assert ops.layer.move_to_group(group=str(parent.id)) == {'FINISHED'}
    d = fresh(d)
    d.edit_with_bones = True
    assert ops.layer.collection_link(layer=str(d.id), collection=collection, on="1") == {'FINISHED'}
    return fresh(d)


outer = rig_in("Character")
layers.active = outer
assert ops.armature.bone_add(name="head", head_x="0", head_y="0", tail_x="0", tail_y="1", parent="") == {'FINISHED'}
inner = rig_in("Mouth", outer)
layers.active = inner
assert ops.armature.bone_add(name="jaw", head_x="2", head_y="0", tail_x="2", tail_y="1", parent="") == {'FINISHED'}
fresh(inner).sub_bone_group = True
tongue = drawing_in("Tongue", inner, 2.0, "Secondary")
lip = drawing_in("Lip", inner, 3.0, "Main")
brow = drawing_in("Brow", outer, 4.0, "Secondary")

layers.active = fresh(outer)
# Linking a drawing to a collection puts it on its own bone layer's panel; Main goes on Character's by hand.
assert ops.armature.collection_add(collection="Main") == {'FINISHED'}
assert ops.armature.collection_set(collection="All", visible="0") == {'FINISHED'}
assert ops.armature.collection_set(collection="Secondary", visible="0") == {'FINISHED'}
assert ops.armature.collection_set(collection="Main", visible="1") == {'FINISHED'}
shown = {c["name"]: c["shown"] for c in fresh(outer).bone_collections}
assert shown == {"All": False, "Main": True, "Secondary": False}, shown
assert all(c["shown"] for c in fresh(inner).bone_collections), "the mouth's own panel shows them all"


def edited():
    """The drawings whose points Select All reaches with Character worked in: those whose wires show."""
    layers.active = fresh(outer)
    ops.mesh.select_none()
    ops.mesh.select_all(action="SELECT")
    out = sorted(l.name for l in (fresh(tongue), fresh(lip), fresh(brow)) if any(p[2] for p in l.points))
    ops.mesh.select_none()
    return out


# Secondary hidden in Character's panel: the Tongue (in the mouth group) goes with the Brow; the Lip in Main shows.
assert edited() == ["Lip"], edited()

# Secondary shown again: both come back.
layers.active = fresh(outer)
assert ops.armature.collection_set(collection="Secondary", visible="1") == {'FINISHED'}
assert edited() == ["Brow", "Lip", "Tongue"], edited()

# The inner panel still hides its own: All and Secondary hidden there hide the Tongue, not the Brow outside it.
layers.active = fresh(inner)
assert ops.armature.collection_set(collection="All", visible="0") == {'FINISHED'}
assert ops.armature.collection_set(collection="Secondary", visible="0") == {'FINISHED'}
assert edited() == ["Brow", "Lip"], edited()
layers.active = fresh(inner)
assert ops.armature.collection_set(collection="Secondary", visible="1") == {'FINISHED'}
assert ops.armature.collection_set(collection="All", visible="1") == {'FINISHED'}

# Solo in the outer panel: only the soloed collection's drawings, the inner group's included.
layers.active = fresh(outer)
assert ops.armature.collection_set(collection="Secondary", solo="1") == {'FINISHED'}
assert edited() == ["Brow", "Tongue"], edited()

print("sub group collections OK")
