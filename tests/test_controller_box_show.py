"""A 2 Axis Controller's Show Box (Bone tab > Viewport Display): Always (the default), When Selected or Never. Only the
box goes (its spots, which then take no clicks, and its rings); the knob always shows. On the setup frame a picked
controller's box shows whatever it says, as its corners size it there. Saved with the file, copied by Symmetrize, and
in Python as controller_box_show.

Run with:  OpenAnimate --background --python tests/test_controller_box_show.py
"""

import os
import tempfile

import oanim

ops, layers, wm = oanim.ops, oanim.data.layers, oanim.wm


def doc():
    return oanim.data.document


def fresh(rig_id):
    return next(l for l in layers.all() if l.id == rig_id)


def bone(rig, n):
    return next(b for b in fresh(rig.id).bones if b["name"] == n)


def pick(rig, n=None):
    layers.active = fresh(rig.id)
    ops.armature.select_none()
    if n:
        fresh(rig.id).select_bone(n)


def rig_new():
    assert ops.wm.read_homefile() == {'FINISHED'}
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    for i, n in enumerate(("Knob_L", "arm")):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=n, head_x=str(i * 3.0 + 1.0), head_y="0", tail_x=str(i * 3.0 + 2.0),
                                     tail_y="0") == {'FINISHED'}
    pick(rig, "Knob_L")
    assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
    return rig


# --- Always by default; When Selected shows only while picked; Never hides it on posed frames --------------------------
rig = rig_new()
assert bone(rig, "Knob_L")["controller_box_show"] == "ALWAYS"
doc().frame_current = 5
for show, picked_shows, unpicked_shows in (("ALWAYS", True, True), ("SELECTED", True, False), ("NEVER", False, False)):
    fresh(rig.id).bone_set("Knob_L", controller_box_show=show)
    assert bone(rig, "Knob_L")["controller_box_show"] == show
    pick(rig, "Knob_L")
    assert wm.controller_boxes_shown(rig) == {"Knob_L": picked_shows}, (show, "picked")
    pick(rig)
    assert wm.controller_boxes_shown(rig) == {"Knob_L": unpicked_shows}, (show, "not picked")

# --- On the setup frame a picked controller's box shows whatever it says (its corners size it) --------------------------
doc().frame_current = 0
pick(rig, "Knob_L")
assert wm.controller_boxes_shown(rig) == {"Knob_L": True}, "Never, picked on the setup frame"
pick(rig)
assert wm.controller_boxes_shown(rig) == {"Knob_L": False}, "Never, not picked on the setup frame"

# --- Saved with the file; Symmetrize copies it, onto a new knob and onto one there already ------------------------------
for show in ("SELECTED", "NEVER", "ALWAYS"):
    rig = rig_new()
    fresh(rig.id).bone_set("Knob_L", controller_box_show=show)
    path = os.path.join(tempfile.mkdtemp(), "box.oanim")
    assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
    assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
    assert bone(rig, "Knob_L")["controller_box_show"] == show, ("back as saved", show)
    pick(rig, "Knob_L")
    assert ops.armature.symmetrize() == {'FINISHED'}
    assert bone(rig, "Knob_R")["controller_box_show"] == show, ("a new mirrored knob", show)
    fresh(rig.id).bone_set("Knob_R", controller_box_show="ALWAYS" if show != "ALWAYS" else "NEVER")
    pick(rig, "Knob_L")
    assert ops.armature.symmetrize() == {'FINISHED'}
    assert bone(rig, "Knob_R")["controller_box_show"] == show, ("onto the knob there already", show)

# --- Python: only a controller's, and only the three --------------------------------------------------------------------
for name, value in (("arm", "NEVER"), ("Knob_L", "SOMETIMES")):
    try:
        fresh(rig.id).bone_set(name, controller_box_show=value)
        raise AssertionError(("taken", name, value))
    except ValueError:
        pass
assert "controller_box_show" not in bone(rig, "arm")

print("Controller Show Box tests passed")
