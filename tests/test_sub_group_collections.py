"""A drawing or bone inside a sub bone group, worked with the bone layer around it, shows only while every collections
panel on the way shows it: the one of the bone layer worked in and each sub bone group's down to its own. Hiding a
collection in the outer panel hides the inner group's drawings in it (the Tongue in Secondary, hidden in Character's
panel, kept its wire while the mouth group's own panel showed All; so did the Tongue_X bone).

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


# --- Bones: the mouth group's bones in Secondary hide with it on Character's panel ---------------------------------
layers.active = fresh(outer)
assert ops.armature.collection_set(collection="Secondary", solo="0") == {'FINISHED'}
assert ops.armature.collection_set(collection="Secondary", visible="1") == {'FINISHED'}
layers.active = fresh(inner)
assert ops.armature.bone_add(name="tongue_b", head_x="3", head_y="0", tail_x="3", tail_y="1", parent="") == {'FINISHED'}
for b, c in (("jaw", "Main"), ("tongue_b", "Secondary")):
    assert ops.armature.bone_collection_link(armature=str(inner.id), bone=b, collection=c, on="1") == {'FINISHED'}
assert ops.armature.bone_collection_link(armature=str(outer.id), bone="head", collection="Main", on="1") == {'FINISHED'}


def picked():
    return sorted(b["name"] for l in (outer, inner) for b in fresh(l).bones if b["selected"])


def select_all():
    layers.active = fresh(outer)
    ops.armature.select_none()
    assert ops.armature.select_all() == {'FINISHED'}
    return picked()


assert select_all() == ["head", "jaw", "tongue_b"], select_all()

# Picked, then Secondary hidden on Character's panel: the tongue bone lets go, as a hidden bone of Character's would.
assert ops.armature.collection_set(collection="Secondary", visible="0") == {'FINISHED'}
assert picked() == ["head", "jaw"], ("hiding lets go of the inner bone", picked())

# A and a box from Character leave it alone while hidden.
assert select_all() == ["head", "jaw"], select_all()
layers.active = fresh(outer)
ops.armature.select_none()
fresh(inner).box_select_bones((-10, -10), (10, 10), whole=True)
assert picked() == ["jaw"], ("a box", picked())

# Worked in on its own, the mouth group's panel alone decides (Secondary shows there).
layers.active = fresh(inner)
ops.armature.select_none()
assert ops.armature.select_all() == {'FINISHED'}
assert sorted(b["name"] for b in fresh(inner).bones if b["selected"]) == ["jaw", "tongue_b"]

# Shown again on Character's panel: back in A.
layers.active = fresh(outer)
assert ops.armature.collection_set(collection="Secondary", visible="1") == {'FINISHED'}
assert select_all() == ["head", "jaw", "tongue_b"], select_all()


# --- In no collection: always shown, with All hidden on every panel (as Blender shows bones in no collection) ---------
layers.active = fresh(inner)
assert ops.armature.bone_add(name="teeth_b", head_x="4", head_y="0", tail_x="4", tail_y="1", parent="") == {'FINISHED'}
assert ops.armature.bone_add(name="lips_b", head_x="5", head_y="0", tail_x="5", tail_y="1", parent="") == {'FINISHED'}
assert ops.armature.bone_collection_link(armature=str(inner.id), bone="lips_b", collection="Lips", on="1") == {'FINISHED'}
assert ops.armature.collection_set(collection="All", visible="0") == {'FINISHED'}
layers.active = fresh(outer)
assert ops.armature.collection_set(collection="Secondary", visible="0") == {'FINISHED'}
layers.active = fresh(outer)
assert ops.layer.new() == {'FINISHED'}
loose = layers.active
loose.name = "Loose"
loose.add_curve([(0.0, 5.0), (1.0, 5.0)])
assert ops.layer.move_to_group(group=str(inner.id)) == {'FINISHED'}
fresh(loose).edit_with_bones = True
# teeth_b is in no collection; lips_b is in Lips, a collection Character's panel doesn't have, so only the mouth's
# panel (Lips shown there) decides for it.
assert select_all() == ["head", "jaw", "lips_b", "teeth_b"], select_all()
for l in (tongue, lip, brow, loose):  # A above picked the points it reached then; clear them all
    fresh(l).select_points(range(len(fresh(l).points)), False)
layers.active = fresh(outer)
ops.mesh.select_all(action="SELECT")
assert any(p[2] for p in fresh(loose).points), "a drawing in no collection is edited with All hidden"
assert not any(p[2] for p in fresh(tongue).points), "the Tongue, in Secondary, still hides"
ops.mesh.select_none()
# Lips hidden on the mouth's panel hides lips_b; teeth_b still shows.
layers.active = fresh(inner)
assert ops.armature.collection_set(collection="Lips", visible="0") == {'FINISHED'}
assert select_all() == ["head", "jaw", "teeth_b"], select_all()

print("sub group collections OK")
