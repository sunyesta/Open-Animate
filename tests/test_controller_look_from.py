"""Look At on a 2 Axis Controller whose knob rides a Knob Parent: the eye it moves in rides there, not with the box, so
it looks from where the knob rests on its Knob Parent, as a pupil bone hanging from that parent would. (The eye file's
Pupil_L: its box on Eye_Camera_Center_L, its knob on Pupil_Center_L, looked from the box and turned half as far as
Pupil_R toward a target below once the head had turned up.)

Run with:  OpenAnimate --background --python tests/test_controller_look_from.py
"""

import math

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers


def close(a, b, eps=1e-4):
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(close(x, y, eps) for x, y in zip(a, b))
    return abs(a - b) < eps


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def scene():
    """A controller "eye" whose box hangs from "box" and whose knob rides "center"; a plain pupil "ref" hanging from
    "center_ref", rigged at the same place; both Look At "look"."""
    ops.wm.read_homefile()
    doc.auto_key = True
    doc.frame_current = 0
    ops.layer.new_bone()
    rig = layers.active
    for name, head, tail in (("box", (0, 0), (0.1, 0)), ("center", (0, 0), (0.1, 0)), ("center_ref", (0, 0), (0.1, 0)),
                             ("look", (0, 0), (0, 0.1))):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(head[0]), head_y=str(head[1]), tail_x=str(tail[0]),
                                     tail_y=str(tail[1])) == {'FINISHED'}
    for name, parent in (("eye", "box"), ("ref", "center_ref")):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x="0", head_y="0", tail_x="0", tail_y="0.05",
                                     parent=parent) == {'FINISHED'}
    ops.layer.new()
    pupil = layers.active
    ops.layer.move_to_group(group=str(rig.id))
    pupil.add_curve([(0.0, 0.0), (0.02, 0.0)])
    assert ops.layer.parent_bone_set(bone="eye") == {'FINISHED'}
    for name, to in (("eye_r", (0.12, 0.0)), ("eye_l", (-0.1, 0.0)), ("eye_u", (0.02, 0.1)), ("eye_d", (0.02, -0.1))):
        layers.active = pupil
        assert ops.anim.action_new(name=name) == {'FINISHED'}
        doc.frame_current = 40
        pupil.set_point(1, to)
        doc.frame_current = 41
        doc.frame_current = 40
        doc.action = ""
        doc.frame_current = 0
    ops.layer.new()
    white = layers.active
    ops.layer.move_to_group(group=str(rig.id))
    white = next(x for x in layers.all() if x.id == white.id)
    white.add_curve([(0.2 * math.cos(2 * math.pi * i / 32), 0.2 * math.sin(2 * math.pi * i / 32)) for i in range(32)],
                    closed=True, fill=True)
    layers.active = rig
    ops.armature.select_none()
    rig.select_bone("eye")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    for side, action in (("RIGHT", "eye_r"), ("LEFT", "eye_l"), ("UP", "eye_u"), ("DOWN", "eye_d")):
        assert ops.armature.controller_side(side=side, action=action) == {'FINISHED'}
    assert ops.armature.bone_relations_set(bone="eye", knob_independent="1") == {'FINISHED'}
    assert ops.armature.bone_relations_set(bone="eye", knob_parent="center") == {'FINISHED'}
    rig.bone_set("eye", contain_knob=False)
    for name in ("eye", "ref"):
        assert ops.armature.constraint_add(type="LOOK_AT", bone=name) == {'FINISHED'}
        rig.bone_constraint_set(name, 0, target="look", shape_layer=white.name, fit="CENTER")
    return rig, white


def bone(rig, name):
    return next(b for b in rig.bones if b["name"] == name)


def go(frame):
    doc.frame_current = frame + 1
    doc.frame_current = frame


def look_shift(rig, frame):
    """How far the Look At moves the controller's knob and the plain pupil, in the picture."""
    out = []
    for influence in (1.0, 0.0):
        for name in ("eye", "ref"):
            rig.bone_constraint_set(name, 0, influence=influence)
        go(frame)
        out.append((bone(rig, "eye")["knob_head"], bone(rig, "ref")["head"], bone(rig, "eye")["knob_shown"]))
    for name in ("eye", "ref"):
        rig.bone_constraint_set(name, 0, influence=1.0)
    go(frame)
    (eye1, ref1, shown1), (eye0, ref0, shown0) = out
    return sub(eye1, eye0), sub(ref1, ref0), sub(shown1, shown0)


# --- With an Eye Shape: the box carried away from the eye, the knob looks as the plain pupil does --------------------
rig, white = scene()
doc.frame_current = 10
rig.bone_set("look", position=(0.3, -0.4))
rig.bone_set("box", position=(0.0, -0.15))
go(10)
assert close(bone(rig, "box")["head"], (0, -0.15)), bone(rig, "box")["head"]
eye, ref, _ = look_shift(rig, 10)
assert abs(ref[0]) > 0.01 and ref[1] < -0.01, ("the plain pupil looks right and down", ref)
assert close(eye, ref), ("the knob looks from where it rides, not from the box", eye, ref)

# Its Knob Parent turned: it looks as a pupil hanging from that parent would.
doc.frame_current = 10
rig.bone_set("center", angle=0.6)
rig.bone_set("center_ref", angle=0.6)
go(10)
eye, ref, _ = look_shift(rig, 10)
assert close(eye, ref), ("turned with its Knob Parent", eye, ref)

# --- Without one: the box is the eye, and the look is the same wherever the box has been carried --------------------
rig, white = scene()
for name in ("eye", "ref"):
    rig.bone_constraint_set(name, 0, shape_layer="")
doc.frame_current = 10
rig.bone_set("look", position=(0.3, -0.4))
go(10)
_, _, still = look_shift(rig, 10)
assert abs(still[0]) > 1.0 and still[1] < -1.0, ("looking right and down", still)
doc.frame_current = 10
rig.bone_set("box", position=(0.0, -0.15))
go(10)
_, _, carried = look_shift(rig, 10)
assert close(carried, still, 1e-3), ("the box carried away, the knob still looks from the eye", carried, still)

print("controller look from: all passed")
