"""Move to Layer and Move to Bone Group with what binds drawings to bones. Points moved into a drawing keep its own keys
(the moved points' channels came still marked as last keyed with their old drawing, so each of the target's keyed frames
they missed read as a key deleted, from every channel). Points moved out of a drawing that follows a bone by Parent
Bone, into one moved by its weights, go all on that bone, looking as they did. A drawing following the moving bone by
Parent Bone isn't tied to the bones that stay by old weights Parent Bone overrides. A switch whose drawings all follow
the moving bone goes along whole, its drawings still in it. A drawing carried into a turned and scaled bone group with
its own place keyed looks as it did on its keys' frames too.

Run with:  OpenAnimate --background --python tests/test_move_bindings.py
"""

import os
import tempfile

import oanim

ops = oanim.ops
SAVE = os.path.join(tempfile.gettempdir(), "oa_test_move_bindings_%d.oanim" % os.getpid())


def doc():
    return oanim.data.document


def layers():
    return oanim.data.layers


def by_name(name):
    return next(l for l in layers().all() if l.name == name)


def reopen():
    ops.wm.save_copy(filepath=SAVE)
    assert ops.wm.open_mainfile(filepath=SAVE) == {'FINISHED'}


def worst(a, b):
    return max(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q))


def shown(name):
    return [tuple(p[:2]) for p in by_name(name).shown()[0]]


def pick(layer, *names):
    layers().active = by_name(layer)
    by_name(layer).select_bone("")
    for i, n in enumerate(names):
        by_name(layer).select_bone(n, extend=i > 0)


def bone_add(name, head, tail, parent=""):
    assert ops.armature.bone_add(name=name, head_x=repr(head[0]), head_y=repr(head[1]), tail_x=repr(tail[0]),
                                 tail_y=repr(tail[1]), parent=parent) == {'FINISHED'}
    ops.armature.select_none()


def drawing_in(group, name, points):
    layers().active = by_name(group)
    assert ops.layer.new() == {'FINISHED'}
    l = layers().active
    l.name = name
    assert ops.layer.move_to_group(group=str(by_name(group).id)) == {'FINISHED'}
    by_name(name).add_curve(points)
    return by_name(name)


def new_rig(name):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_freeze_keys = False
    doc().frame_current = 0
    assert ops.layer.new_bone() == {'FINISHED'}
    layers().active.name = name


# --- the target keeps its own keys
assert ops.wm.read_homefile() == {'FINISHED'}
assert ops.layer.new() == {'FINISHED'}
layers().active.name = "A"
by_name("A").add_curve([(3.0, 0.0), (4.0, 0.0), (4.0, 1.0), (3.0, 1.0)], closed=True, fill=True)
assert ops.layer.new() == {'FINISHED'}
layers().active.name = "B"
by_name("B").add_curve([(-2.0, -2.0), (-1.0, -2.0), (-1.5, -1.0)], closed=True, fill=True)
doc().auto_key = True
doc().frame_current = 12
by_name("B").set_point(0, (-2.5, -2.0))
doc().frame_current = 0
reopen()
keys = by_name("B").key_frames
layers().active = by_name("A")
ops.mesh.select_none()
by_name("A").select_points([0, 1, 2, 3])
assert ops.mesh.move_to_layer(target="B") == {'FINISHED'}
assert by_name("B").key_frames == keys, ("the target's keys", keys, by_name("B").key_frames)
doc().frame_current = 12
p = by_name("B").points[0]
assert abs(p[0] + 2.5) < 1e-4 and abs(p[1] + 2.0) < 1e-4, ("its key on 12 still moves its point", p)

# --- out of a Parent Bone drawing into a weighted one
new_rig("R")
bone_add("Bone", (0, 0), (3, 0))
bone_add("Bone2", (3, 0), (5, 1), "Bone")
drawing_in("R", "Art", [(3.2, 0.2), (4.0, 0.6), (4.6, 0.9)])
layers().active = by_name("Art")
assert ops.layer.parent_bone_set(bone="Bone2") == {'FINISHED'}
same = drawing_in("R", "Same", [(0.5, -0.5), (1.5, -0.5), (2.5, -0.5)])
same.edit_with_bones = True
bone_id = next(b["id"] for b in by_name("R").bones if b["name"] == "Bone")
for i in range(3):
    ops.weight.point_set(layer=str(same.id), point=str(i), bone=str(bone_id), weight="1")
doc().auto_key = True
doc().frame_current = 5
by_name("R").bone_set("Bone2", angle=by_name("R").bones[1]["angle"] + 0.8)
doc().frame_current = 0
reopen()
seen = {}
for f in (0, 5):
    doc().frame_current = f
    seen[f] = shown("Art")
doc().frame_current = 0
had = by_name("Same").point_count
layers().active = by_name("Art")
ops.mesh.select_none()
by_name("Art").select_points([0, 1, 2])
assert ops.mesh.move_to_layer(target="Same") == {'FINISHED'}
for f in (0, 5):
    doc().frame_current = f
    off = worst(shown("Same")[had:], seen[f])
    assert off < 1e-4, ("points out of a Parent Bone drawing look as they did", f, off)

# --- old weights under Parent Bone tie a drawing to nothing
new_rig("Body")
bone_add("A", (0, 0), (1, 0))
bone_add("B", (0, 1), (1, 1.3))
art = drawing_in("Body", "Art", [(0.1, 0.1), (0.5, 0.2), (0.9, 0.1)])
art.edit_with_bones = True
a_id = next(b["id"] for b in by_name("Body").bones if b["name"] == "A")
for i in range(3):
    ops.weight.point_set(layer=str(art.id), point=str(i), bone=str(a_id), weight="1")
layers().active = by_name("Art")
assert ops.layer.parent_bone_set(bone="B") == {'FINISHED'}
reopen()
pick("Body", "B")
assert ops.armature.move_to_group(target="NEW") == {'FINISHED'}, "Art follows only B"
assert by_name("Art").parent.name != "Body", "Art went with B"

# --- a switch whose drawings all follow the moving bone goes whole
new_rig("Body")
bone_add("A", (0, 0), (1, 0))
bone_add("B", (0, 1), (1, 1.3))
assert ops.layer.new_switch() == {'FINISHED'}
layers().active.name = "Box"
assert ops.layer.move_to_group(group=str(by_name("Body").id)) == {'FINISHED'}
for name, pts in (("N1", [(0.1, 1.1), (0.5, 1.3), (0.9, 1.1)]), ("N2", [(0.1, 0.9), (0.5, 0.7), (0.9, 0.9)])):
    drawing_in("Box", name, pts)
    layers().active = by_name(name)
    assert ops.layer.parent_bone_set(bone="B") == {'FINISHED'}
assert ops.layer.switch_set(layer="Box", child="N1") == {'FINISHED'}
reopen()
drawn = [n for n in oanim.data.draw_order if n in ("N1", "N2")]
kids = [c.name for c in by_name("Box").children]
pick("Body", "B")
assert ops.armature.move_to_group(target="NEW") == {'FINISHED'}
assert [c.name for c in by_name("Box").children] == kids, ("the switch keeps its drawings",
                                                            [c.name for c in by_name("Box").children])
assert [n for n in oanim.data.draw_order if n in ("N1", "N2")] == drawn, "the switch still shows one"
assert by_name("Box").parent.name != "Body", "the switch went with B"

# --- a carried drawing's keyed place, into a turned and scaled bone group
new_rig("Body")
bone_add("Leg", (1, 0), (2, 0.2))
bone_add("Foot", (2, 0.2), (2.5, 0.8), "Leg")
assert ops.layer.new_bone() == {'FINISHED'}
layers().active.name = "Inner"
assert ops.layer.move_to_group(group=str(by_name("Body").id)) == {'FINISHED'}
inner = by_name("Inner")
inner.location_x, inner.location_y, inner.rotation = 0.3, -0.4, 25.0
inner.scale_x = inner.scale_y = 1.5
art = drawing_in("Body", "Art", [(1.2, 0.1), (1.8, 0.2), (2.2, 0.5)])
art.edit_with_bones = True
foot = next(b["id"] for b in by_name("Body").bones if b["name"] == "Foot")
for i in range(3):
    ops.weight.point_set(layer=str(art.id), point=str(i), bone=str(foot), weight="1")
doc().auto_key = True
art = by_name("Art")
art.keyframe_insert("position", 0)
art.keyframe_insert("rotation", 0)
doc().frame_current = 5
art.location_x = 0.8
art.rotation = 20.0
art.keyframe_insert("position", 5)
art.keyframe_insert("rotation", 5)
doc().frame_current = 0
reopen()
seen = {}
for f in (0, 5, 3):
    doc().frame_current = f
    seen[f] = shown("Art")
doc().frame_current = 0
pick("Body", "Foot")
assert ops.armature.move_to_group(target="Inner") == {'FINISHED'}
assert by_name("Art").parent.name == "Inner"
for f in (0, 5, 3):
    doc().frame_current = f
    off = worst(shown("Art"), seen[f])
    assert off < 1e-4, ("the carried drawing looks as it did", f, off)
print("test_move_bindings passed")
