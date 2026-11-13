"""Guards from a fuzzer sweep: a Surface Smooth stroke over a segment far shorter than the brush keeps its points (the
smoothing's strength grew past what the solve could hold, 1e17, and wrote NaN into them); a look target's Depth, never
keyed, changed on a posed frame, the eyes measured from where they rested; a controller's look target moved by the Bone
panel's fields, the knob's actions played again; a Whole Drawing fit that can't fit worked out once a frame, not once
for every layer shown. Each section failed on the build before.

Run with:  OpenAnimate --background --python tests/test_sweep_fuzz_guards.py
"""

import math

import oanim

ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers
D = lambda: oanim.data.document


def finite(layer):
    return all(math.isfinite(c) for p in layer.points for c in p[:2])


def knob_rig():
    """A controller "eye" whose box hangs from "box" and whose knob rides "center"; a plain pupil "ref" hanging from
    "center_ref", rigged at the same place; both Look At "look"."""
    ops.wm.read_homefile()
    D().auto_key = True
    D().frame_current = 0
    ops.layer.new_bone()
    rig = L.active
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
    pupil = L.active
    ops.layer.move_to_group(group=str(rig.id))
    pupil.add_curve([(0.0, 0.0), (0.02, 0.0)])
    assert ops.layer.parent_bone_set(bone="eye") == {'FINISHED'}
    for name, to in (("eye_r", (0.12, 0.0)), ("eye_l", (-0.1, 0.0)), ("eye_u", (0.02, 0.1)), ("eye_d", (0.02, -0.1))):
        L.active = pupil
        assert ops.anim.action_new(name=name) == {'FINISHED'}
        D().frame_current = 40
        pupil.set_point(1, to)
        D().frame_current = 41
        D().frame_current = 40
        D().action = ""
        D().frame_current = 0
    ops.layer.new()
    white = L.active
    ops.layer.move_to_group(group=str(rig.id))
    white = next(x for x in L.all() if x.id == white.id)
    white.add_curve([(0.2 * math.cos(2 * math.pi * i / 32), 0.2 * math.sin(2 * math.pi * i / 32)) for i in range(32)],
                    closed=True, fill=True)
    L.active = rig
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
    return rig, next(x for x in L.all() if x.id == pupil.id)


def eye_rig():
    assert ops.wm.read_homefile() == {'FINISHED'}
    D().frame_current = 0
    D().auto_key = True
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = L.active
    for name, hx, hy, tx, ty, parent in (("head", 0, 0, 0, 2, ""), ("eye_L", 0.3, 1, 0.3, 1.05, "head"),
                                         ("eye_R", -0.3, 1, -0.3, 1.05, "head"), ("look", 0, 1, 0, 1.1, "")):
        assert ops.armature.bone_add(name=name, head_x=str(hx), head_y=str(hy), tail_x=str(tx), tail_y=str(ty),
                                     parent=parent) == {'FINISHED'}

    def drawing(cx, rx, ry, bone_name):
        ops.layer.new()
        l = L.active
        assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
        l = next(x for x in L.all() if x.id == l.id)
        l.add_curve([(cx + rx * math.cos(math.pi * k / 8), 1.0 + ry * math.sin(math.pi * k / 8)) for k in range(16)],
                    closed=True, fill=True)
        L.active = l
        assert ops.layer.parent_bone_set(bone=bone_name) == {'FINISHED'}
        return next(x for x in L.all() if x.id == l.id)

    whites = {"eye_L": drawing(0.3, 0.2, 0.1, "head"), "eye_R": drawing(-0.3, 0.2, 0.1, "head")}
    drawing(0.3, 0.03, 0.03, "eye_L")
    drawing(-0.3, 0.03, 0.03, "eye_R")
    L.active = rig
    for eye, white in whites.items():
        rig.select_bone(eye)
        assert ops.armature.constraint_add(type="LOOK_AT", bone=eye) == {'FINISHED'}
        rig.bone_constraint_set(eye, 0, target="look", shape_layer=white.name, fit="CENTER")
    return rig


# --- Surface Smooth over a tiny curve and a tiny segment between two points: every point stays a number
assert ops.wm.read_homefile() == {'FINISHED'}
assert ops.wm.tool_sculpt() == {'FINISHED'}
ops.layer.new()
lay = L.active
lay.add_curve([(0.0, 0.0), (0.0036, 0.0005)])
lay.add_curve([(-0.05, 0.02), (0.0, 0.03), (0.0036, 0.031), (0.05, 0.02)])
ops.mesh.select_none()
before = [tuple(p[:2]) for p in lay.points]
path = ";".join("%r,%r" % (0.001 * k, 0.005) for k in range(5))
assert ops.sculpt.stroke(amount="1.0", brush="SURFACE_SMOOTH", falloff="SPHERE", radius="0.08", sensitivity="4.0",
                         strength="1.0", path=path) == {'FINISHED'}
assert finite(lay), [tuple(p[:2]) for p in lay.points]
assert all(math.dist(a, tuple(b[:2])) < 0.05 for a, b in zip(before, lay.points)), "smoothed, not thrown away"

# --- A look target's Depth, never keyed, changed on a posed frame: the eyes look from where they rested, as the frame
# shows once reached again (the rest took the new Depth until the edit was keyed, so the eyes barely moved, then jumped)
rig = eye_rig()
head = lambda name: next(b for b in rig.bones if b["name"] == name)["head"]
D().frame_current = 20
assert not rig.keyframes('bones["look"].depth')
rig.bone_set("look", depth=0.4)
wm.frame_sync_playing(20, 0)
shown = (head("eye_L"), head("eye_R"))
D().frame_current = 21
D().frame_current = 20
again = (head("eye_L"), head("eye_R"))
off = max(math.dist(a, b) for a, b in zip(shown, again))
assert off < 1e-5, ("the eyes shown while Depth changed, against the frame reached again", shown, again, off)
assert shown[0][0] < 0.3 - 0.01 and shown[1][0] > -0.3 + 0.01, ("brought close, the eyes cross", shown)

# --- A controller's Look At target moved by the Bone panel's fields: the knob's actions play again on that frame, as
# they do for a target dragged (only the knob's own position was watched, so the drawing kept its old blend)
rig, pupil = knob_rig()
D().frame_current = 10
rig.bone_set("look", position=(0.3, -0.4))
D().frame_current = 11
D().frame_current = 10
wm.frame_sync_playing(10, 0)  # the frame settled, as the main loop leaves it
rig.bone_set("look", position=(-0.2, 0.3))
for _ in range(3):
    wm.frame_sync_playing(10, 0)
shown = pupil.shown()[0]
D().frame_current = 11
D().frame_current = 10
again = pupil.shown()[0]
off = max(math.dist(a, b) for a, b in zip(shown, again))
assert off < 1e-5, ("the knob's drawing shown after its target moved, against the frame reached again", off)

# --- Pupils bigger than their eyes, fitted Whole Drawing: a frame works each fit out once, not once for every layer
# the rig bends (each took the slow way, fifty passes over the pupil against the eye: the fuzzed eye file took 11 s to
# show its layers, a test's checks never finished)
rig = eye_rig()
for eye_name in ("eye_L", "eye_R"):
    rig.bone_constraint_set(eye_name, 0, fit="WHOLE")
for p in [l for l in L.all() if l.type == "VECTOR"][2:4]:
    for idx, q in enumerate(p.points):
        cx = 0.3 if q[0] > 0 else -0.3
        p.set_point(idx, (cx + (q[0] - cx) * 12, 1.0 + (q[1] - 1.0) * 12))
for k in range(20):
    ops.layer.new()
    lay = L.active
    assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
    lay = next(x for x in L.all() if x.id == lay.id)
    lay.add_curve([(0.1 * k, 0.0), (0.1 * k + 0.05, 0.1), (0.1 * k + 0.1, 0.0)])
    L.active = lay
    assert ops.layer.parent_bone_set(bone="head") == {'FINISHED'}
L.active = rig
D().frame_current = 10
rig.bone_set("look", position=(0.5, 1.4))
D().frame_current = 11
wm.deform_counts_clear()
D().frame_current = 10
assert wm.deform_counts()["shape_fits"] > 0, "the frame fits the pupils"
wm.deform_counts_clear()
for lay in L.all():
    lay.shown()
fits = wm.deform_counts()["shape_fits"]
print("shape fits", fits)
assert fits <= 8, ("each layer shown worked the eyes' fits out again", fits)

print("test_sweep_fuzz_guards: all passed")
