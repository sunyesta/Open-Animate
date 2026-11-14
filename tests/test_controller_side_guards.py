"""A 2 Axis Controller's side never ends up holding a bone's own action (an action named after a bone, or one and " 2"),
whatever path leads there: New Controller Action with a bone of its name, a bone renamed or added with a side's action's
name, a controller made Regular whose name a side's action has, Symmetrize, Mirror Controller Side (which never makes or
replaces an action it then refuses), and the conversion of older files' links on opening (which must not convert again
on the next open). Convert To the type a bone has already is CANCELLED.

Run with:  OpenAnimate --background --python tests/test_controller_side_guards.py
"""

import json
import os
import tempfile
import zipfile

import oanim

ops, layers = oanim.ops, oanim.data.layers
OUT = tempfile.mkdtemp()


def doc():
    return oanim.data.document


def rig_new(names):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_freeze_keys = False
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    for i, n in enumerate(names):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=n, head_x=str(i * 2.0), head_y="0", tail_x=str(i * 2.0 + 1.0),
                                     tail_y="0") == {'FINISHED'}
    return rig


def fresh(rig_id):
    return next(l for l in layers.all() if l.id == rig_id)


def bone(rig, n):
    return next(b for b in fresh(rig.id).bones if b["name"] == n)


def controller(rig, n):
    ops.armature.select_none()
    fresh(rig.id).select_bone(n)
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}


def ordinary(name):
    assert ops.anim.action_new(name=name) == {'FINISHED'}, name
    got = doc().action
    assert ops.anim.action_set(name="") == {'FINISHED'}
    return got


def sides(rig):
    return {b["name"]: dict(b["controller_actions"]) for b in fresh(rig.id).bones if b["type"] == "CONTROLLER_2D"}


def own_held(rig):
    """Sides holding a bone's own action."""
    regs = {b["name"] for b in fresh(rig.id).bones if b["type"] != "CONTROLLER_2D"}
    return [(k, s, a) for k, ss in sides(rig).items() for s, a in ss.items()
            if a and (a in regs or (a.endswith(" 2") and a[:-2] in regs))]


def reopened_sides(rig, path=None):
    """Saved and opened again: the sides as they come back."""
    if path is None:
        path = os.path.join(OUT, "again.oanim")
        assert ops.wm.save_copy(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
    return sides(rig)


def steps():
    return oanim.wm.undo_history()[1]


def keys_in(rig, path, action):
    """`path`'s keys in `action`."""
    layers.active = fresh(rig.id)
    assert ops.anim.action_set(name=action, layer=str(rig.id)) == {'FINISHED'}, action
    out = [(k["frame"], k["value"]) for k in fresh(rig.id).keyframes(path)]
    assert ops.anim.action_set(name="") == {'FINISHED'}
    return out


# --- New Controller Action with a bone named "K Right": the side's action is named so it stays ordinary ----------------
rig = rig_new(["K", "K Right"])
controller(rig, "K")
assert ops.armature.controller_action_new(side="RIGHT") == {'FINISHED'}
assert ops.anim.action_set(name="") == {'FINISHED'}
assert sides(rig)["K"]["RIGHT"] == "K Right.001", sides(rig)
held = sides(rig)
assert not own_held(rig) and reopened_sides(rig) == held

# --- A bone renamed, or added, with the name of a side's action: refused, or named apart -------------------------------
rig = rig_new(["K2", "B"])
controller(rig, "K2")
ordinary("wave")
fresh(rig.id).select_bone("K2")
assert ops.armature.controller_side(side="UP", action="wave") == {'FINISHED'}
for to in ("wave",):
    try:
        fresh(rig.id).bone_set("B", name=to)
        raise AssertionError(("renamed onto a side's action", to))
    except ValueError:
        pass
assert [b["name"] for b in fresh(rig.id).bones] == ["K2", "B"]
ops.armature.select_none()
assert ops.armature.bone_add(name="wave", head_x="6", head_y="0", tail_x="7", tail_y="0") == {'FINISHED'}
assert "wave" not in [b["name"] for b in fresh(rig.id).bones], [b["name"] for b in fresh(rig.id).bones]
held = sides(rig)
assert not own_held(rig) and held["K2"]["UP"] == "wave" and reopened_sides(rig) == held

# --- A controller made Regular while another knob's side plays an action of its name: refused, it stays a controller ----
rig = rig_new(["K3", "X"])
controller(rig, "K3")
controller(rig, "X")
ordinary("X")
fresh(rig.id).select_bone("K3")
assert ops.armature.controller_side(side="RIGHT", action="X") == {'FINISHED'}
for to in ("REGULAR", "PIN"):
    ops.armature.select_none()
    fresh(rig.id).select_bone("X")
    at = steps()
    assert ops.armature.bone_convert(type=to) == {'CANCELLED'}, to
    assert bone(rig, "X")["type"] == "CONTROLLER_2D" and steps() == at
held = sides(rig)
assert not own_held(rig) and held["K3"]["RIGHT"] == "X" and reopened_sides(rig) == held

# --- Symmetrize a knob whose side's mirrored action is a bone's own: never that; mirroring actions, a new one ----------
for mirror in ("0", "1"):
    rig = rig_new(["Knob_L", "spin_R"])
    fresh(rig.id).select_bone("spin_R")
    assert ops.anim.action_new(name="spin_R", action_bone="1") == {'FINISHED'}
    doc().frame_current = 10
    fresh(rig.id).bone_set("spin_R", angle=bone(rig, "spin_R")["setup_angle"] + 0.8)
    doc().frame_current = 11
    doc().frame_current = 0
    assert ops.anim.action_set(name="") == {'FINISHED'}
    spin_keys = keys_in(rig, 'bones["spin_R"].angle', "spin_R")
    assert len(spin_keys) == 2, spin_keys
    ordinary("spin_L")
    controller(rig, "Knob_L")
    assert ops.armature.controller_side(side="LEFT", action="spin_L") == {'FINISHED'}
    ops.armature.select_none()
    fresh(rig.id).select_bone("Knob_L")
    assert ops.armature.symmetrize(action_bone_actions=mirror) == {'FINISHED'}
    assert not own_held(rig), own_held(rig)
    assert sides(rig)["Knob_R"]["RIGHT"] == ("Knob_R Right" if mirror == "1" else ""), (mirror, sides(rig))
    assert keys_in(rig, 'bones["spin_R"].angle', "spin_R") == spin_keys, "spin_R's own action was mirrored over"
    held = sides(rig)
    assert reopened_sides(rig) == held

# --- Mirror Controller Side into a bone's name: a new action named after the side, never the bone's own -----------------
rig = rig_new(["K5", "Look_R"])
ordinary("Look_L")
controller(rig, "K5")
assert ops.armature.controller_side(side="RIGHT", action="Look_L") == {'FINISHED'}
at = steps()
assert ops.armature.controller_mirror(side="LEFT") == {'FINISHED'}
assert steps() == at + 1
assert sides(rig)["K5"]["LEFT"] == "K5 Left" and "Look_R" not in [a["name"] for a in fresh(rig.id).actions], sides(rig)
assert not own_held(rig)

# --- Mirror Controller Side whose mirrored action is another knob's side: that knob keeps it, its keys untouched --------
rig = rig_new(["K5", "K2", "arm"])
controller(rig, "K5")
controller(rig, "K2")
ordinary("Look_L")
assert ops.anim.action_new(name="Look_R") == {'FINISHED'}
doc().frame_current = 10
fresh(rig.id).bone_set("arm", angle=bone(rig, "arm")["setup_angle"] + 1.0)
doc().frame_current = 11
doc().frame_current = 0
assert ops.anim.action_set(name="") == {'FINISHED'}
look_r = keys_in(rig, 'bones["arm"].angle', "Look_R")
assert len(look_r) == 2, look_r
ops.armature.select_none()
fresh(rig.id).select_bone("K2")
assert ops.armature.controller_side(side="UP", action="Look_R") == {'FINISHED'}
ops.armature.select_none()
fresh(rig.id).select_bone("K5")
assert ops.armature.controller_side(side="RIGHT", action="Look_L") == {'FINISHED'}
assert ops.armature.controller_mirror(side="LEFT") == {'FINISHED'}
assert sides(rig)["K2"]["UP"] == "Look_R" and sides(rig)["K5"]["LEFT"] == "K5 Left", sides(rig)
assert keys_in(rig, 'bones["arm"].angle', "Look_R") == look_r

# --- An older file's link converted on opening into a name a bone has: converted once, the same on the next open --------
rig = rig_new(["K2", "B", "K2 Up"])
controller(rig, "K2")
ordinary("wave")
fresh(rig.id).select_bone("K2")
assert ops.armature.controller_side(side="UP", action="wave") == {'FINISHED'}
path = os.path.join(OUT, "linked.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    members = {n: z.read(n) for n in z.namelist()}
d = json.loads(members["document.json"])
for lay in d["document"]["layers"]:
    for b in lay.get("bones", []):
        if b["name"] == "B":
            b["name"] = "wave"  # as an older file, its side playing bone wave's own action
members["document.json"] = json.dumps(d).encode()
with zipfile.ZipFile(path, "w") as z:
    for n, data in members.items():
        z.writestr(n, data)
first = reopened_sides(rig, path)
assert first["K2"]["UP"] not in ("wave", "K2 Up"), first
assert not own_held(rig)
assert reopened_sides(rig) == first

# --- Convert To the type a bone has already: CANCELLED, no undo step ---------------------------------------------------
rig = rig_new(["A", "K", "P"])
controller(rig, "K")
ops.armature.select_none()
fresh(rig.id).select_bone("P")
assert ops.armature.bone_convert(type="PIN") == {'FINISHED'}
for name, to in (("A", "REGULAR"), ("K", "CONTROLLER_2D"), ("P", "PIN")):
    ops.armature.select_none()
    fresh(rig.id).select_bone(name)
    at = steps()
    assert ops.armature.bone_convert(type=to) == {'CANCELLED'}, (name, to)
    assert steps() == at

print("Controller side guards tests passed")
