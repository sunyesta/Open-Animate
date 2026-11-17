"""A fix named by itself stays named after the actions playing where it ends: once a knob's side takes another action
it is named again at once, and a file saved with a name out of date (as one whose linked controller sides were made
ordinary actions on opening) opens with it named right, so going into the fix and out again changes nothing.

Run with:  OpenAnimate --background --python tests/test_bone_fix_names.py
"""

import os
import tempfile
import zipfile

import oanim

ops, layers = oanim.ops, oanim.data.layers


def doc():
    return oanim.data.document


def build():
    """A knob with ordinary actions on Right and Up, a face drawing they move, and a fix ending up and right."""
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc().auto_key = True
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    rig.name = "Rig"
    ops.armature.bone_add(name="Bone", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
    ops.layer.new()
    face = layers.active
    face.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    ops.layer.move_to_group(group=str(rig.id))
    for name, i, moved in (("Bone Right", 0, (2.0, 0.0)), ("Bone Up", 1, (1.0, 1.0)), ("Bone Push", 0, (3.0, 0.0))):
        layers.active = rig_of(rig.id)
        assert ops.anim.action_new(name=name) == {'FINISHED'}
        doc().frame_current = 24
        next(l for l in layers.all() if l.id == face.id).set_point(i, moved)
        doc().frame_current = 25
        mainline()
    layers.active = rig_of(rig.id)
    rig_of(rig.id).select_bone("Bone")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    assert ops.armature.controller_side(side="RIGHT", action="Bone Right") == {'FINISHED'}
    assert ops.armature.controller_side(side="UP", action="Bone Up") == {'FINISHED'}
    knob(rig.id, 0.0, 24.0)
    rig_of(rig.id).select_bone("Bone")
    assert ops.armature.bone_fix_new() == {'FINISHED'}
    doc().frame_current = 30
    rig_of(rig.id).bone_set("Bone", knob=(24.0, 24.0))
    settle()
    mainline()
    assert fix_names(rig.id) == ["Bone Up and Right"], fix_names(rig.id)
    return rig.id


def rig_of(rid):
    return next(l for l in layers.all() if l.id == rid)


def fix_names(rid):
    return [f["name"] for f in rig_of(rid).bone_fixes]


def mainline():
    assert ops.anim.action_set(name="") in ({'FINISHED'}, {'CANCELLED'})
    doc().frame_current = 0


def settle():
    doc().frame_current = doc().frame_current + 1
    doc().frame_current = doc().frame_current - 1


def knob(rid, x, y, frame=5):
    doc().frame_current = frame
    rig_of(rid).select_bone("Bone")
    rig_of(rid).bone_set("Bone", knob=(x, y))
    settle()


def in_and_out(rid):
    """Going into the fix and straight out again: its name after."""
    name = fix_names(rid)[0]
    assert ops.anim.action_set(name=name) == {'FINISHED'}
    mainline()
    return fix_names(rid)


# --- A side taking another action: the fix following its knob is named after it at once -------------------------------
rid = build()
assert ops.armature.controller_side(side="RIGHT", action="Bone Push") == {'FINISHED'}
assert fix_names(rid) == ["Bone Up and Push"], fix_names(rid)
assert in_and_out(rid) == ["Bone Up and Push"], "going in and out changes nothing"

# --- A file saved with a fix's name out of date opens with it named after its sides ------------------------------------
rid = build()
path = os.path.join(tempfile.mkdtemp(), "stale.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
with zipfile.ZipFile(path) as z:
    members = {n: z.read(n) for n in z.namelist()}
with zipfile.ZipFile(path, "w") as z:
    for n, data in members.items():
        z.writestr(n, data.replace(b'"Bone Up and Right"', b'"Old Up and Old Right"') if n.endswith(".json") else data)
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
assert fix_names(rid) == ["Bone Up and Right"], fix_names(rid)
assert in_and_out(rid) == ["Bone Up and Right"], "going in and out changes nothing"

# --- Renamed by hand: left as it is, on opening and when a side changes ------------------------------------------------
rid = build()
assert ops.anim.action_rename(name="Bone Up and Right", to="Look") == {'FINISHED'}
assert ops.armature.controller_side(side="RIGHT", action="Bone Push") == {'FINISHED'}
assert fix_names(rid) == ["Look"], fix_names(rid)
path = os.path.join(tempfile.mkdtemp(), "hand.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
assert fix_names(rid) == ["Look"], fix_names(rid)

# --- An action a side plays deleted, or the knob: named again at once, so saving and opening changes nothing ----------
def saved_and_opened(rid, name):
    path = os.path.join(tempfile.mkdtemp(), name)
    assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
    return fix_names(rid)


rid = build()
layers.active = rig_of(rid)
assert ops.anim.action_delete(name="Bone Right") == {'FINISHED'}
now = fix_names(rid)
assert now != ["Bone Up and Right"], ("named again when the action it names goes", now)
assert saved_and_opened(rid, "deleted_action.oanim") == now

rid = build()
layers.active = rig_of(rid)
ops.armature.select_none()
rig_of(rid).select_bone("Bone")
assert ops.armature.bone_delete() == {'FINISHED'}
now = fix_names(rid)
assert now != ["Bone Up and Right"], ("named again when its bone goes", now)
assert saved_and_opened(rid, "deleted_bone.oanim") == now

# --- Two fixes named again to the same name (the knob made a Pin: neither has its sides now): each its own at once ------
rid = build()
layers.active = rig_of(rid)
ops.armature.select_none()
rig_of(rid).select_bone("Bone")
knob(rid, 0.0, 24.0)
rig_of(rid).select_bone("Bone")
assert ops.armature.bone_fix_new() == {'FINISHED'}
doc().frame_current = 30
rig_of(rid).bone_set("Bone", knob=(24.0, 24.0))
settle()
mainline()
assert len(fix_names(rid)) == 2 and all(n.startswith("Bone Up and Right") for n in fix_names(rid)), fix_names(rid)
layers.active = rig_of(rid)
ops.armature.select_none()
rig_of(rid).select_bone("Bone")
assert ops.armature.bone_convert(type="PIN") == {'FINISHED'}
now = fix_names(rid)
assert len(set(now)) == 2 and not any("Up" in n or "Right" in n for n in now), ("both named again at once", now)
assert saved_and_opened(rid, "two_renamed.oanim") == now, "opening names them as they were"

print("Fix names tests passed")
