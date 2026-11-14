"""One motion path at a time (Show All Paths off, the default): of everything traced only the active path shows, and
the tool, its operators and the timing chart see only it. The active path is the one chosen ([ and ], the header's
list, the popover's, a timeline row's name) while the active bone stays the same; else the active bone's tip (a
pin's head), else the active layer's first. Show All Paths shows them all again, and is saved with the file.

Run with:  OpenAnimate --background --python tests/test_motion_path_one.py
"""

import os
import tempfile

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

assert ops.wm.read_homefile() == {'FINISHED'}
doc = oanim.data.document
assert doc.path_show_all is False, "one path at a time by default"
doc.auto_key = True
doc.auto_freeze_keys = False
doc.motion_paths = True
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig_id = rig.id
for name, x in (("arm", 0.0), ("leg", 3.0)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1", parent="") == {'FINISHED'}
# Both turn and move between 0 and 10.
for f, a in ((10, 0.5), (20, -0.3)):
    doc.frame_current = f
    rig.bone_set("arm", angle=a, position=(0.2 * a, 0.1))
    rig.bone_set("leg", angle=-a, position=(3.0, 0.2 * a))
doc.frame_current = 5


def shown():
    return [p["label"] for p in wm.motion_paths()]


# --- Both bones picked, leg active: four paths traced, only the active bone's tip shown --------------------------------
rig.select_bone("arm")
rig.select_bone("leg", extend=True)
assert sorted(wm.motion_paths_traced()) == ["arm head", "arm tip", "leg head", "leg tip"], wm.motion_paths_traced()
assert shown() == ["leg tip"], shown()
assert wm.motion_path_active() == "leg tip"

# --- [ and ] in the Motion Path tool step through them, round ---------------------------------------------------------
assert ops.wm.tool_motion_path() == {'FINISHED'}
order = wm.motion_paths_traced()
at = order.index("leg tip")
assert wm.event_simulate("RIGHT_BRACKET", area="Viewport")
assert shown() == [order[(at + 1) % 4]], (shown(), order)
assert wm.event_simulate("LEFT_BRACKET", area="Viewport")
assert wm.event_simulate("LEFT_BRACKET", area="Viewport")
assert shown() == [order[(at - 1) % 4]], (shown(), order)
assert ops.anim.motion_path_active_next() == {'FINISHED'}
assert shown() == ["leg tip"]

# --- Chosen by name; it stays while the active bone does, picking another bone follows that one ----------------------
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="arm", head="1") == {'FINISHED'}
assert shown() == ["arm head"]
doc.frame_current = 15
assert shown() == ["arm head"], "a frame change keeps it"
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="nope") == {'CANCELLED'}
rig.select_bone("arm", extend=True)  # arm made active
assert shown() == ["arm tip"], ("the newly active bone's", shown())
rig.select_bone("leg", extend=True)
assert shown() == ["leg tip"], ("leg active again: its tip, the choice let go", shown())
ops.armature.select_none()
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="arm") == {'CANCELLED'}, "arm isn't traced"
rig.select_bone("arm")
rig.select_bone("leg", extend=True)

# --- The timing chart and its operators see only the path shown --------------------------------------------------------
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="arm") == {'FINISHED'}
assert [t["label"] for t in wm.motion_path_timing()] == ["arm tip"], wm.motion_path_timing()
assert ops.anim.motion_path_active_set(layer=str(rig_id), bone="leg", head="1") == {'FINISHED'}
assert [t["label"] for t in wm.motion_path_timing()] == ["leg head"], wm.motion_path_timing()

# --- A timeline row's name shows its path: a bone's Transform row its head, its Angle row and its own row its tip -------
rows = [r[1] for r in wm.timeline_rows(False)]
arm = rows.index("arm")
assert rows[arm + 1:arm + 3] == ["Transform", "Angle"], rows
assert wm.timeline_row_path_show(arm + 1) and shown() == ["arm head"], shown()
assert wm.timeline_row_path_show(arm + 2) and shown() == ["arm tip"], shown()
leg = rows.index("leg")
assert wm.timeline_row_path_show(leg + 1) and shown() == ["leg head"], shown()
assert wm.timeline_row_path_show(leg) and shown() == ["leg tip"], shown()
assert wm.timeline_row_path_show(0) and shown() == ["leg tip"], "the Summary row changes nothing"

# --- Show All Paths: every one again, and [ ] go back to the switch layers' ---------------------------------------------
doc.path_show_all = True
assert sorted(shown()) == ["arm head", "arm tip", "leg head", "leg tip"], shown()
assert ops.anim.motion_path_active_next() == {'CANCELLED'}, "nothing to step through"
path = os.path.join(tempfile.mkdtemp(), "one.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
doc.path_show_all = False
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
assert oanim.data.document.path_show_all is True, "saved with the file"

print("One motion path tests passed")
