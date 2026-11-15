"""Alt click in a timeline row with the Motion Path tool, one path shown: a row whose path is traced but hidden (another
bone's shown) shows that path, the one its name shows (a bone's Transform row its head), and picks its stretch there
(Pupil_L's row, Pupil_R's head shown, said "No path traced in this row"). A row with no path traced still picks
nothing and leaves the path shown as it was.

Run with:  OpenAnimate --background --python tests/test_stretch_pick_hidden_path.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

assert ops.wm.read_homefile() == {'FINISHED'}
doc = oanim.data.document
doc.auto_key = True
doc.auto_freeze_keys = False
doc.motion_paths = True
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig_id = rig.id
for name, x in (("arm", 0.0), ("leg", 3.0), ("tail", 6.0)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1", parent="") == {'FINISHED'}
for f, a in ((10, 0.5), (20, -0.3)):
    doc.frame_current = f
    rig.bone_set("arm", angle=a, position=(0.2 * a, 0.1))
    rig.bone_set("leg", angle=-a, position=(3.0, 0.2 * a))
    rig.bone_set("tail", angle=a, position=(6.0, 0.3 * a))
doc.frame_current = 5
assert ops.wm.tool_motion_path() == {'FINISHED'}

# arm and leg picked, leg active: leg's path shown.
rig.select_bone("arm")
rig.select_bone("leg", extend=True)
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="leg", head="1") == {'FINISHED'}
assert wm.motion_path_active() == "leg head"


def row(bone):
    return dict(layers=str(rig_id), path='bones["%s"].position' % bone, kinds="304")


# --- arm's Transform row, its path hidden: shown (its head) and its stretch picked --------------------------------------
assert ops.anim.timeline_stretch_pick(frame="15", **row("arm")) == {'FINISHED'}
assert wm.motion_path_active() == "arm head", wm.motion_path_active()
assert [p["label"] for p in wm.motion_paths()] == ["arm head"]
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (10, 20), panel
assert [d["frame"] for d in wm.motion_path_dots()] == [15], wm.motion_path_dots()
assert doc.frame_current == 15

# The shown row's own Alt click as before: leg shown again by its row, its stretch the one picked.
assert ops.anim.timeline_stretch_pick(frame="5", **row("leg")) == {'FINISHED'}
assert wm.motion_path_active() == "leg head"
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (0, 10), panel

# --- tail isn't picked, so nothing of it is traced: nothing picked, the path shown stays -------------------------------
assert ops.anim.timeline_stretch_pick(frame="15", **row("tail")) == {'CANCELLED'}
assert wm.motion_path_active() == "leg head"
assert [d["frame"] for d in wm.motion_path_dots()] == [5], wm.motion_path_dots()

print("stretch pick hidden path: ok")
