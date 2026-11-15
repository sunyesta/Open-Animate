"""The timeline's Only Selected shows a bone picked in a sub bone group while the bone layer around it is the one worked
in: its bones are picked from there (TopTeeth_X, picked in Mouth_Closed_X from Character, showed no row). A bone left
picked in a bone layer outside the one worked in still shows nothing.

Run with:  OpenAnimate --background --python tests/test_timeline_sub_group_bones.py
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


def bone(rig, name, x):
    layers.active = fresh(rig)
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1",
                                 parent="") == {'FINISHED'}


other = rig_in("Other")
bone(other, "arm", 5)
outer = rig_in("Character")
bone(outer, "head", 0)
inner = rig_in("Mouth", outer)
bone(inner, "teeth", 2)
fresh(inner).sub_bone_group = True
assert fresh(other).parent is None and fresh(outer).parent is None

# Each bone keyed on frame 10.
doc.auto_key = True
doc.frame_current = 10
for rig, name in ((outer, "head"), (inner, "teeth"), (other, "arm")):
    fresh(rig).bone_set(name, angle=0.3)
    assert ops.anim.keyframe_insert() in ({'FINISHED'}, {'CANCELLED'})
for rig, name in ((outer, "head"), (inner, "teeth"), (other, "arm")):
    assert any(k for k in fresh(rig).keyframes('bones["%s"].angle' % name) if k["frame"] == 10), name

doc.timeline_only_selected = True
for l in layers.all():
    l.selected = False


def rows():
    return [r["name"] for r in wm.timeline_row_details(as_shown=False)]


# The teeth picked in the mouth group, Character worked in (the active layer), as clicking them in the viewport leaves
# it: their row shows, under the mouth group's.
fresh(other).select_bone("arm")
fresh(inner).select_bone("teeth")
fresh(outer).select_bone("")
for l in layers.all():
    l.selected = False
layers.active = fresh(outer)
assert [b["name"] for b in fresh(inner).bones if b["selected"]] == ["teeth"]
r = rows()
assert "teeth" in r, ("the sub bone group's picked bone shows", r)
assert "Mouth" in r and r.index("Mouth") < r.index("teeth"), r
assert "head" not in r, ("Character's bones aren't picked", r)
assert "arm" not in r and "Other" not in r, ("a bone left picked outside the rig worked in shows nothing", r)

# Its keyed channel under it, red as picked.
teeth_row = next(x for x in wm.timeline_row_details(as_shown=False) if x["name"] == "teeth")
assert teeth_row["red"], teeth_row
assert "Angle" in r[r.index("teeth") + 1:], r

# Working in the other rig instead: its bone shows, the mouth's doesn't.
layers.active = fresh(other)
r = rows()
assert "arm" in r and "teeth" not in r, r

print("timeline sub group bones: ok")
