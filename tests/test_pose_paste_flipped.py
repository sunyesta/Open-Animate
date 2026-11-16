"""Paste Pose Flipped (Ctrl Shift V over the viewport off the setup frame), as Blender's: the copied pose mirrored left
to right. An _L bone's pose goes on its _R partner and the other way, a bone with no side takes its own mirrored; a
drawing's points go on their mirror images (in its _L / _R partner, else in itself), handles onto the image's handle
reaching for the image of what they reached for. The mirror is across the bone layer's (or the drawings') vertical axis.

Run with:  OpenAnimate --background --python tests/test_pose_paste_flipped.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm


def close(a, b, eps=1e-3):
    return all(abs(x - y) < eps for x, y in zip(a, b))


def flip(p):
    return (-p[0], p[1])


def fresh():
    global doc, layers
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.auto_freeze_keys = False
    doc.frame_current = 0


def find(layer_id):
    return next(l for l in layers.all() if l.id == layer_id)


def at(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def last_step():
    names, index = wm.undo_history()
    return names[index]


# --- Bones: _L onto _R and the other way, a bone with no side onto itself, mirrored ------------------------------------
fresh()
assert ops.layer.new_bone() == {'FINISHED'}
rig_id = layers.active.id
rig = lambda: find(rig_id)
for name, hx, hy, tx, ty in (("Spine", 0, 0, 0, 1), ("Arm_L", 0.5, 0.8, 1.5, 0.6), ("Arm_R", -0.5, 0.8, -1.5, 0.6)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(hx), head_y=str(hy), tail_x=str(tx), tail_y=str(ty),
                                 parent="") == {'FINISHED'}
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
doc.auto_key = True
at(10)
rig().bone_set("Arm_L", angle=bone("Arm_L")["setup_angle"] + 0.7, position=(0.7, 1.1))
rig().bone_set("Spine", angle=bone("Spine")["setup_angle"] - 0.4, position=(0.3, -0.2))
at(10)
shown10 = {n: (tuple(bone(n)["head"]), tuple(bone(n)["tail"])) for n in ("Spine", "Arm_L", "Arm_R")}
layers.active = rig()
rig().select_bone("Arm_L")
rig().select_bone("Spine", extend=True)
assert ops.pose.copy() == {'FINISHED'}
at(20)
arm_l20 = (tuple(bone("Arm_L")["head"]), tuple(bone("Arm_L")["tail"]))
assert wm.event_simulate("V", ctrl=True, shift=True, area="Viewport")
assert last_step() == "Paste Pose Flipped", last_step()
op = wm.last_operation()
assert op and op[0] == "pose.paste_flipped" and op[1].get("flipped") == "1", op
for name, source in (("Arm_R", "Arm_L"), ("Spine", "Spine")):
    head, tail = shown10[source]
    assert close(bone(name)["head"], flip(head)) and close(bone(name)["tail"], flip(tail)), \
        (name, bone(name)["head"], bone(name)["tail"], "should mirror", source, head, tail)
assert close(bone("Arm_L")["head"], arm_l20[0]) and close(bone("Arm_L")["tail"], arm_l20[1]), \
    "Arm_L wasn't pasted onto: Arm_R was copied from nothing"
at(20)
assert close(bone("Arm_R")["tail"], flip(shown10["Arm_L"][1])), "keyed"
# Plain Paste Pose puts them back as copied, not mirrored.
assert ops.pose.paste() == {'FINISHED'}
assert close(bone("Arm_L")["tail"], shown10["Arm_L"][1])

# --- A drawing with no side: each point onto its mirror image, handles too ---------------------------------------------
fresh()
assert ops.layer.new() == {'FINISHED'}
art_id = layers.active.id
art = lambda: find(art_id)
art().add_curve([(-0.5, 0.0), (0.0, 0.3), (0.5, 0.0)])
doc.auto_key = True
at(10)
art().set_point(0, (-0.7, 0.2))
art().place_handle(0, 0, "OUT", (-0.55, 0.45))
at(10)
points10, curves10 = art().shown()
layers.active = art()
ops.mesh.select_none()
art().select_points([0])
assert ops.pose.copy() == {'FINISHED'}
at(20)
p0_20 = art().shown()[0][0]
assert ops.pose.paste_flipped() == {'FINISHED'}
points, curves = art().shown()
assert close(points[2], flip(points10[0])), (points[2], flip(points10[0]))
assert close(points[0], p0_20), "the point copied isn't pasted onto: its image is"
# Its out handle reached for the middle point: on the image it is the in handle, which reaches for it.
out10 = curves10[0][0][0][2]
in_now = curves[0][0][2][1]
assert close(in_now, flip(out10)), (in_now, flip(out10))

# --- An _L drawing's pose onto its _R partner --------------------------------------------------------------------------
fresh()
ids = {}
for name, sign in (("Eye_L", 1), ("Eye_R", -1)):
    assert ops.layer.new() == {'FINISHED'}
    layers.active.name = name
    ids[name] = layers.active.id
    find(ids[name]).add_curve([(sign * 0.5, 0.0), (sign * 0.8, 0.2), (sign * 1.1, 0.0)])
doc.auto_key = True
at(10)
find(ids["Eye_L"]).set_point(1, (0.9, 0.5))
at(10)
left10 = find(ids["Eye_L"]).shown()[0]
for l in layers.all():
    l.selected = l.id == ids["Eye_L"]
layers.active = find(ids["Eye_L"])
ops.mesh.select_none()
find(ids["Eye_L"]).select_points([1])
assert ops.pose.copy() == {'FINISHED'}
at(20)
left20 = find(ids["Eye_L"]).shown()[0]
assert ops.pose.paste_flipped() == {'FINISHED'}
right = find(ids["Eye_R"]).shown()[0]
assert close(right[1], flip(left10[1])), (right[1], flip(left10[1]))
assert close(find(ids["Eye_L"]).shown()[0][1], left20[1]), "Eye_L stays"

print("pose paste flipped: ok")
