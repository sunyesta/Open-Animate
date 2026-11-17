"""Paste Pose on the setup frame and On Selected Only: Same Look and Same Place on frame 0 put the copied change on the
setup once (their second pass, after the first was recorded into the setup, put it on again); Paste Pose Flipped as
Same Look or Same Place onto points on frame 0 pastes (its second pass found no mirror images in the moved setup and
returned CANCELLED over a changed file); On Selected Only counts the selection across the bone layer and its sub bone
groups (an unselected bone in a sub bone group was pasted); pasted again on frame 0 a pose changes nothing (each press
put the copied change on the setup again).

Run with:  OpenAnimate --background --python tests/test_pose_paste_setup.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm


def fresh():
    assert ops.wm.read_homefile(confirmed="1") == {'FINISHED'}
    oanim.data.document.frame_current = 0
    return oanim.data.document, oanim.data.layers


# --- Same Look and Same Place on frame 0: the copied change on the setup once, as Keys -------------------------------
doc, layers = fresh()
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
assert ops.armature.bone_add(name="Arm", head_x="1", head_y="0.5", tail_x="1.6", tail_y="1.3", parent="") == \
    {'FINISHED'}
doc.auto_key = True


def arm():
    return next(b for b in rig.bones if b["name"] == "Arm")


setup = arm()["setup_angle"]
setup_head = arm()["position"]
doc.frame_current = 10
rig.bone_set("Arm", angle=setup + 0.3, position=(setup_head[0] + 0.2, setup_head[1] - 0.1))
doc.frame_current = 11
doc.frame_current = 10
ops.armature.select_none()
rig.select_bone("Arm")
assert ops.pose.copy() == {'FINISHED'}
for as_ in ("KEYS", "LOOK", "PLACE"):
    doc.frame_current = 0
    assert ops.pose.paste(paste_as=as_, keep_poses="0") == {'FINISHED'}
    got = arm()["setup_angle"] - setup
    assert abs(got - 0.3) < 1e-4, (as_, "the setup turned by the copied change once", got)
    head = arm()["position"]
    assert abs(head[0] - setup_head[0] - 0.2) < 1e-4 and abs(head[1] - setup_head[1] + 0.1) < 1e-4, \
        (as_, "moved by it once", head, setup_head)
    ops.ed.undo()
print("SECTION 1 PASS")

# --- Paste Pose Flipped as Same Look or Same Place onto points on frame 0: pasted, as Keys ---------------------------
results = {}
for as_ in ("KEYS", "LOOK", "PLACE"):
    doc, layers = fresh()
    assert ops.layer.new() == {'FINISHED'}
    art = layers.active
    art.add_curve([(-0.3, 1.5), (0.0, 1.8), (0.3, 1.5)])  # symmetric about x = 0
    doc.frame_current = 1
    doc.frame_current = 0
    doc.auto_key = True
    doc.frame_current = 10
    art.select_points(range(3), False)
    art.select_points([0, 1])
    assert ops.mesh.translate(move_x="0.1", move_y="0.05") == {'FINISHED'}
    art.select_points(range(3))
    assert ops.pose.copy() == {'FINISHED'}
    doc.frame_current = 0
    step = wm.undo_history()[1]
    assert ops.pose.paste_flipped(paste_as=as_) == {'FINISHED'}, as_
    assert wm.undo_history()[1] != step, (as_, "an undo step")
    doc.frame_current = 1
    doc.frame_current = 0
    results[as_] = [tuple(p[:2]) for p in art.points]
want = [(-0.3, 1.5), (-0.1, 1.85), (0.2, 1.55)]
for as_, got in results.items():
    assert all(abs(a - b) < 1e-4 for p, q in zip(got, want) for a, b in zip(p, q)), (as_, got, want)
print("SECTION 2 PASS")

# --- On Selected Only: the selection counted across the bone layer and its sub bone groups ---------------------------
doc, layers = fresh()
assert ops.layer.new_bone() == {'FINISHED'}
rig_id = layers.active.id
assert ops.armature.bone_add(name="Arm", head_x="1", head_y="0.5", tail_x="1.6", tail_y="1.3", parent="") == \
    {'FINISHED'}
ops.armature.select_none()
assert ops.armature.bone_add(name="Leg", head_x="0", head_y="-1", tail_x="0", tail_y="-2", parent="") == {'FINISHED'}
assert ops.layer.new_bone() == {'FINISHED'}
mouth_id = layers.active.id
assert ops.layer.move_to_group(group=str(rig_id)) == {'FINISHED'}


def lay(i):
    return next(l for l in layers.all() if l.id == i)


def bone(i, n):
    return next(b for b in lay(i).bones if b["name"] == n)


layers.active = lay(mouth_id)
assert ops.armature.bone_add(name="Teeth", head_x="0.3", head_y="-0.6", tail_x="0.7", tail_y="-0.4", parent="") == \
    {'FINISHED'}
lay(mouth_id).sub_bone_group = True
doc.auto_key = True
for f, k in ((10, 1), (20, -1)):
    doc.frame_current = f
    for i, n in ((rig_id, "Arm"), (rig_id, "Leg"), (mouth_id, "Teeth")):
        lay(i).bone_set(n, angle=bone(i, n)["setup_angle"] + 0.4 * k)
doc.frame_current = 11
doc.frame_current = 10
layers.active = lay(rig_id)
ops.armature.select_all()
lay(mouth_id).select_bone("Teeth", extend=True)
assert ops.pose.copy() == {'FINISHED'}
assert ops.poselib.pose_new(name="All", new_collection="Body") == {'FINISHED'}
pid = str(next(p for p in oanim._oanim.poses() if p["name"] == "All")["id"])


def pick(i, n):
    layers.active = lay(mouth_id)
    ops.armature.select_none()
    layers.active = lay(rig_id)
    ops.armature.select_none()
    lay(i).select_bone(n)


for name, run in (("paste", lambda: ops.pose.paste(selected_mask="1")),
                  ("library", lambda: ops.poselib.apply(pose=pid, selected_only="1"))):
    for picked, left in (((rig_id, "Arm"), (mouth_id, "Teeth")), ((mouth_id, "Teeth"), (rig_id, "Arm"))):
        doc.frame_current = 20
        was_picked, was_left = bone(*picked)["angle"], bone(*left)["angle"]
        was_leg = bone(rig_id, "Leg")["angle"]
        pick(*picked)
        assert run() == {'FINISHED'}, name
        assert abs(bone(*picked)["angle"] - was_picked - 0.8) < 1e-4, (name, picked, "the picked bone pasted")
        assert abs(bone(*left)["angle"] - was_left) < 1e-6, (name, left, "the other layer's unpicked bone left alone")
        assert abs(bone(rig_id, "Leg")["angle"] - was_leg) < 1e-6, (name, "Leg left alone")
        ops.ed.undo()
print("SECTION 3 PASS")

# --- Pasted twice on frame 0: the second press changes nothing ---------------------------------------------------------
for as_ in ("KEYS", "LOOK", "PLACE"):
    doc, layers = fresh()
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    assert ops.armature.bone_add(name="Arm", head_x="1", head_y="0.5", tail_x="1.6", tail_y="1.3", parent="") ==         {'FINISHED'}
    assert ops.layer.new() == {'FINISHED'}
    art = layers.active
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    art.add_curve([(-0.3, 1.5), (0.0, 1.8), (0.3, 1.5)])
    doc.frame_current = 1
    doc.frame_current = 0
    doc.auto_key = True
    arm = lambda: next(b for b in rig.bones if b["name"] == "Arm")
    setup = (arm()["setup_angle"], arm()["position"])
    doc.frame_current = 10
    rig.bone_set("Arm", angle=setup[0] + 0.3, position=(setup[1][0] + 0.2, setup[1][1]))
    art.set_point(1, (0.1, 1.9))
    doc.frame_current = 11
    doc.frame_current = 10
    layers.active = rig
    ops.armature.select_none()
    rig.select_bone("Arm")
    art.selected = True  # the drawing picked beside the bone layer, so its points are copied with the bones
    art.select_points(range(3))
    assert ops.pose.copy() == {'FINISHED'}
    doc.frame_current = 0
    assert ops.pose.paste(paste_as=as_, keep_poses="0") == {'FINISHED'}
    once = (arm()["setup_angle"], arm()["position"], [tuple(p[:2]) for p in art.points])
    assert abs(once[0] - setup[0] - 0.3) < 1e-4, (as_, once[0], setup[0])
    assert abs(once[2][1][0] - 0.1) < 1e-4 and abs(once[2][1][1] - 1.9) < 1e-4, (as_, once[2])
    assert ops.pose.paste(paste_as=as_, keep_poses="0") == {'FINISHED'}
    twice = (arm()["setup_angle"], arm()["position"], [tuple(p[:2]) for p in art.points])
    assert abs(twice[0] - once[0]) < 1e-5, (as_, "the setup turned again", once[0], twice[0])
    assert all(abs(a - b) < 1e-5 for a, b in zip(twice[1], once[1])), (as_, "the setup moved again", once[1], twice[1])
    assert all(abs(a - b) < 1e-5 for p, q in zip(twice[2], once[2]) for a, b in zip(p, q)),         (as_, "the points moved again", once[2], twice[2])
print("SECTION 4 PASS")

print("pose paste setup ok")
