"""G, R and S with bones and points picked together (A on a bone layer picks the points of the drawings edited with
its bones too) move them all: each picked point lands as far from where it showed as the move takes it, once, whether
the bones bend it or not (only the bones moved, and the points the bones don't bend stayed behind).

Run with:  OpenAnimate --background --python tests/test_move_bones_and_points.py
"""

import math

import oanim

doc = oanim.data.document
layers = oanim.data.layers
wm = oanim.wm
doc.frame_current = 0


def close(a, b, eps=1e-4):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def shown(layer):
    points, _, _ = layer.evaluated()
    return [layer.to_document(p[:2]) for p in points]


def fresh(layer):
    return next(l for l in layers.all() if l.id == layer.id)


assert oanim.ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
oanim.ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="")


def drawing(name, curve):
    oanim.ops.layer.new()
    layer = layers.active
    layer.name = name
    layer.add_curve(curve)
    assert oanim.ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    layer = fresh(layer)
    layer.edit_with_bones = True
    return layer


# The arm's skin, bent by the bone; and a mark the bone doesn't bend (the lips under a face bone, say).
skin = drawing("skin", [(0.2, 0.1), (0.6, 0.2), (0.9, -0.1)])
layers.active = skin
assert oanim.ops.weight.automatic() == {'FINISHED'}
mark = drawing("mark", [(-1.0, 1.0), (-0.5, 1.5), (0.0, 1.0)])
layers.active = rig


def arm():
    return next(b for b in rig.bones if b["name"] == "arm")


def moved(before, fn):
    return [fn(p) for p in before]


def turned(p, degrees, about=(0.0, 0.0)):
    a = math.radians(degrees)
    x, y = p[0] - about[0], p[1] - about[1]
    return (about[0] + x * math.cos(a) - y * math.sin(a), about[1] + x * math.sin(a) + y * math.cos(a))


for frame in (10, 0):
    doc.frame_current = frame
    posing = "1" if frame else "0"
    assert oanim.ops.armature.select_all() == {'FINISHED'}
    assert all(p[2] for p in skin.points) and all(p[2] for p in mark.points), "A picks the points too"
    skin_before, mark_before = shown(skin), shown(mark)

    # G: everything by the same amount, the bent points once (not with the bone and again by themselves).
    assert oanim.ops.armature.translate(move_x="0.3", move_y="0.1", posing=posing) == {'FINISHED'}
    assert wm.undo_history()[0][-1] == "Move Bones"
    want = lambda p: (p[0] + 0.3, p[1] + 0.1)
    assert all(close(a, want(b)) for a, b in zip(shown(mark), mark_before)), (frame, shown(mark), mark_before)
    assert all(close(a, want(b)) for a, b in zip(shown(skin), skin_before)), (frame, shown(skin), skin_before)
    # Changed in the panel: from where it began, not added.
    assert wm.redo_last(move_x="0.5", move_y="0", posing=posing) == "FINISHED"
    want = lambda p: (p[0] + 0.5, p[1])
    assert all(close(a, want(b)) for a, b in zip(shown(mark), mark_before)), (frame, shown(mark))
    assert all(close(a, want(b)) for a, b in zip(shown(skin), skin_before)), (frame, shown(skin))
    oanim.ops.ed.undo()
    assert all(close(a, b) for a, b in zip(shown(mark), mark_before)), "undone"

    # R: about the bones' middle (the arm's head here), the skin with its bone.
    assert oanim.ops.armature.rotate(angle="30", posing=posing) == {'FINISHED'}
    assert abs(math.degrees(arm()["angle"]) - 30.0) < 1e-3, arm()["angle"]
    assert all(close(a, turned(b, 30)) for a, b in zip(shown(mark), mark_before)), (frame, shown(mark))
    assert all(close(a, turned(b, 30)) for a, b in zip(shown(skin), skin_before)), (frame, shown(skin))
    oanim.ops.ed.undo()

    # S: the mark scaled about the same middle.
    assert oanim.ops.armature.resize(scale="1.5", posing=posing) == {'FINISHED'}
    assert all(close(a, (b[0] * 1.5, b[1] * 1.5)) for a, b in zip(shown(mark), mark_before)), (frame, shown(mark))
    oanim.ops.ed.undo()

    # Bones alone picked: the drawings' points stay where the bones put them, as before.
    assert oanim.ops.armature.select_none() == {'FINISHED'}
    rig.select_bone("arm")
    assert oanim.ops.armature.translate(move_x="0.3", move_y="0.1", posing=posing) == {'FINISHED'}
    assert all(close(a, b) for a, b in zip(shown(mark), mark_before)), "an unpicked mark stays"
    oanim.ops.ed.undo()

print("ok")
