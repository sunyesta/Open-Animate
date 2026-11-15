"""Alt click in a timeline row with the Motion Path tool, one path shown: a row whose path is traced but hidden (another
bone's shown) shows that path, the one its name shows (a bone's Transform row its head), and picks its stretch there
(Pupil_L's row, Pupil_R's head shown, said "No path traced in this row"). A row with no path traced still picks
nothing and leaves the path shown as it was. Shift Alt click adds: the paths shown stay shown beside the new one,
their picks kept (each Shift Alt click on the other pupil's row picked it alone), each stretch teal and the latest
active; a timing edit to the active one reaches the other bone's; a plain pick, or another path chosen, lets the
extra path go.

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

# --- Shift Alt click on the other bone's row adds its stretch: both paths shown, both picked ----------------------------
assert ops.anim.timeline_stretch_pick(frame="15", **row("leg")) == {'FINISHED'}
assert wm.motion_path_active() == "leg head"
assert ops.anim.timeline_stretch_pick(frame="15", extend="1", **row("arm")) == {'FINISHED'}
assert sorted(p["label"] for p in wm.motion_paths()) == ["arm head", "leg head"], wm.motion_paths()
dots = wm.motion_path_dots()
assert len({d["bone"] for d in dots}) == 2 and [d["frame"] for d in dots] == [15, 15], dots
h = wm.timeline_key_header()
assert h["mode"] == "PATH" and h["label"] == "2 paths  10-20", ("the same frames on both: one stretch on two paths", h)
panel = wm.motion_path_timing_panel()
assert (panel["start"], panel["end"]) == (10, 20), panel
assert sorted(t["label"] for t in wm.motion_path_timing()) == ["arm head", "leg head"], wm.motion_path_timing()
teal = [s for r in wm.timeline_row_details(as_shown=False) if r["name"] == "Transform" for s in r["teal_spans"]]
assert teal == [(10, 20, True), (10, 20, True)], ("both bones' rows teal", teal)

# Shift again back on the first one's row: still both, the first active again.
assert ops.anim.timeline_stretch_pick(frame="12", extend="1", **row("leg")) == {'FINISHED'}
assert len(wm.motion_path_dots()) == 3 and len(wm.motion_paths()) == 2, (wm.motion_path_dots(), wm.motion_paths())


def key(bone, frame):
    return next(k for k in rig.keyframes('bones["%s"].position' % bone) if k["frame"] == frame)


# A timing edit to the active stretch reaches the other bone's.
assert ops.anim.timeline_stretch_pick(frame="15", extend="1", **row("arm")) == {'FINISHED'}
assert ops.anim.motion_path_stretch_shape(shape="EASE_IN", frame="15", layer=str(rig_id), bone="arm",
                                          head="1") == {'FINISHED'}
assert key("arm", 20)["interp"] == "CUSTOM" and key("leg", 20)["interp"] == "CUSTOM", (key("arm", 20), key("leg", 20))
assert key("arm", 20)["timing"] == key("leg", 20)["timing"]

# A plain Alt click picks one alone; the other path, nothing on it picked now, hidden again.
assert ops.anim.timeline_stretch_pick(frame="15", **row("arm")) == {'FINISHED'}
assert [p["label"] for p in wm.motion_paths()] == ["arm head"], wm.motion_paths()
# Another path chosen lets the extra one go too.
assert ops.anim.timeline_stretch_pick(frame="15", extend="1", **row("leg")) == {'FINISHED'}
assert len(wm.motion_paths()) == 2
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="leg") == {'FINISHED'}
assert [p["label"] for p in wm.motion_paths()] == ["leg tip"], wm.motion_paths()
assert wm.motion_path_dots() == [], wm.motion_path_dots()

print("stretch pick hidden path: ok")
