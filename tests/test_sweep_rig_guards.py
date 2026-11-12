"""Rig edits a sweep found going wrong: entering an action the bone has no path in and leaving keeps the mainline's On
Path (it was dropped, and the bone moved on the mainline); a fix leaves a bone it follows as it is, whatever of the bone
is keyed in it (only its traced channel was left out); a reference of a group shows what is inside as the original
does, where a deform's shape is inside a group with deforms of its own (the reference took those twice).

Run with:  OpenAnimate --background --python tests/test_sweep_rig_guards.py
"""

import math

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm


def settle():
    doc.frame_current = doc.frame_current + 1
    doc.frame_current = doc.frame_current - 1


def rig_with_knob():
    """A rig whose knob plays an action carrying the ear across."""
    ops.wm.read_homefile()
    doc.auto_key = True
    ops.layer.new_bone()
    rig_id = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
    ops.armature.select_none()
    ops.armature.bone_add(name="Ear", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
    ops.armature.select_none()
    assert ops.anim.action_new(name="Knob Right") == {'FINISHED'}
    doc.frame_current = 24
    p = next(b for b in rig().bones if b["name"] == "Ear")["position"]
    rig().bone_set("Ear", position=(p[0] - 0.6, p[1] - 0.2))
    doc.frame_current = 25
    ops.anim.action_set(name="")
    doc.frame_current = 0
    rig().select_bone("Knob")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Knob Right") == {'FINISHED'}
    return rig_id, rig


# --- Into an action the bone has no path in and out: On Path stays ---------------------------------------------------
rig_id, rig = rig_with_knob()
for f, knob in ((6, (2.0, 0.0)), (30, (24.0, 0.0))):
    doc.frame_current = f
    rig().bone_set("Knob", knob=knob)
    settle()
doc.auto_key = False
doc.motion_paths = True
doc.path_all = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
layers.active = rig()
rig().select_bone("Ear")
doc.frame_current = 18
args = dict(bone="Ear", head="1", layer=str(rig_id))


def ear_path():
    return next(p for p in wm.motion_paths(kept=False) if p["label"] == "Ear head")


def ear_heads():
    out = []
    for f in (12, 18, 40):
        doc.frame_current = f
        out.append(tuple(next(b for b in rig().bones if b["name"] == "Ear")["head"]))
    doc.frame_current = 18
    return out


assert ops.anim.motion_path_on_path(on="1", **args) == {'FINISHED'}
assert ear_path()["on_path"] is True
before = ear_heads()
doc.frame_current = 0
assert ops.anim.action_new(name="Blink") == {'FINISHED'} and doc.action == "Blink"
assert ops.anim.action_set(name="") == {'FINISHED'} and doc.action == ""
doc.frame_current = 18
assert ear_path()["on_path"] is True, "into an action and out dropped the mainline's On Path"
off = max(math.dist(a, b) for a, b in zip(before, ear_heads()))
assert off < 1e-5, ("the ear moved on the mainline", off)
# And in an action with keys of its own on the ear, the mainline's stays too.
assert ops.anim.action_set(name="Knob Right", layer=str(rig_id)) == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
assert ear_path()["on_path"] is True

# --- A fix leaves a bone it follows as it is, its place keyed in it too ------------------------------------------------
rig_id, rig = rig_with_knob()
ops.armature.select_none()
ops.armature.bone_add(name="Nose", head_x="0.0", head_y="-2.0", tail_x="1.0", tail_y="-2.0")
ops.armature.select_none()
doc.frame_current = 0
rig().select_bone("Knob")
assert ops.armature.bone_fix_new(bones="Knob") == {'FINISHED'}
fix = doc.action
doc.frame_current = 30
rig().bone_set("Knob", knob=(24.0, 24.0))
nose = next(b for b in rig().bones if b["name"] == "Nose")
rig().bone_set("Nose", position=(nose["position"][0] + 0.3, nose["position"][1] + 0.2), angle=nose["angle"] + 0.4)
settle()
assert ops.anim.action_set(name="") == {'FINISHED'}
fix = next(f["name"] for f in rig().bone_fixes)
layers.active = rig()
assert ops.armature.bone_fix_follow(name=fix, bones="Nose", follow="1") == {'FINISHED'}
assert "Nose" in next(f for f in rig().bone_fixes if f["name"] == fix)["follows"]
# On the mainline the knob and the nose where the fix's line ends: it plays whole there.
doc.frame_current = 20
rig().bone_set("Knob", knob=(24.0, 24.0))
rig().bone_set("Nose", position=(nose["position"][0] + 0.3, nose["position"][1] + 0.2), angle=nose["angle"] + 0.4)
settle()
doc.auto_key = False


def nose_now():
    b = next(b for b in rig().bones if b["name"] == "Nose")
    return (b["angle"],) + tuple(b["position"])


assert next(f for f in rig().bone_fixes if f["name"] == fix)["strength"] > 0.5, rig().bone_fixes
playing = nose_now()
assert ops.anim.action_play_set(name=fix, layer=str(rig_id), mute="1") == {'FINISHED'}
settle()
muted = nose_now()
assert ops.anim.action_play_set(name=fix, layer=str(rig_id), mute="0") == {'FINISHED'}
gap = max(abs(a - b) for a, b in zip(playing, muted))
assert gap < 1e-5, ("the fix moved a bone it follows", playing, muted)

# --- A reference of a group: inside, as the original, a deform's shape in a group with deforms ----------------------
ops.wm.read_homefile()
doc.auto_key = True
doc.frame_current = 0
anchor = layers.active


def new_layer(name, box=None, points=None):
    layers.active = anchor
    ops.layer.new()
    layer = layers.active
    layer.name = name
    if box:
        assert layer.add_primitive("BOX", box)
    if points:
        layer.add_curve(points)
    return layer


def new_group(name, *children):
    layers.active = anchor
    assert ops.layer.new_group() == {'FINISHED'}
    group = layers.active
    group.name = name
    for child in children:
        layers.active = child
        assert ops.layer.move_to_group(group=str(group.id)) == {'FINISHED'}
    return group


def add_cage(group, cage):
    layers.active = group
    assert ops.object.modifier_add(type="CAGE_DEFORM") == {'FINISHED'}
    index = len(group.modifiers) - 1
    group.modifier_set(index, layer=cage.name, shape=cage.shapes[0][0], cage_method="MEAN_VALUE", resample_self=False)


outer_cage = new_layer("Outer Cage", box=[(-2, -2), (2, 2)])
warp = new_layer("Warp", box=[(-1, -1), (1, 1)])
art = new_layer("Art", points=[(0.5, 0.0), (0.0, 0.3), (-0.4, -0.2)])
base = new_group("Base", art)
eye = new_group("Eye", warp, base)
add_cage(base, warp)
add_cage(eye, outer_cage)
for layer, i, pos in ((outer_cage, 2, (2.6, 2.4)), (warp, 0, (-1.3, -0.8))):
    doc.frame_current = 10
    layer.set_point(i, pos)
    settle()
doc.frame_current = 0
old = {l.id for l in layers.all()}
layers.active = eye
assert ops.layer.make_reference() == {'FINISHED'}
copy = next(l for l in layers.all() if l.id not in old and l.reference_source is not None and
            l.reference_source.id == art.id)
for f in (5, 10):
    doc.frame_current = f
    moved = max(math.dist(p, q[:2]) for p, q in zip(art.shown()[0], art.points))
    assert moved > 0.05, ("the deforms bend the original", f, moved)
    gap = max(math.dist(p, q) for p, q in zip(copy.shown()[0], art.shown()[0]))
    assert gap < 1e-4, ("the group's reference shows off its original", f, gap)

print("test_sweep_rig_guards: ok")
