"""The timeline's Only Selected counts what is picked on the motion paths with the Motion Path tool: a key picked on a
bone's path shows its layer and the bone's rows (red, as a selected bone's) though the bone isn't selected; one picked on
a point's path shows the point's layer though it isn't selected or edited.

Run with:  OpenAnimate --background --python tests/test_timeline_path_picks.py
"""

import oanim
oanim.data.document.path_show_all = True  # these tests look at several paths at once

ops, layers, wm = oanim.ops, oanim.data.layers, oanim.wm
doc = oanim.data.document
doc.auto_key = True
doc.auto_freeze_keys = False
doc.frame_current = 0
assert ops.layer.new_bone() == {'FINISHED'}
rig = layers.active
rig.name = "Rig"
ops.armature.bone_add(name="a", head_x="0", head_y="0", tail_x="1", tail_y="0", parent="")
ops.layer.new()
art = layers.active
assert ops.layer.move_to_group(group=str(rig.id)) == {'FINISHED'}
art = next(l for l in layers.all() if l.id == art.id)
art.name = "Art"
art.add_curve([(0.0, 1.0), (1.0, 1.0), (2.0, 1.0)])
rig = next(l for l in layers.all() if l.id == rig.id)
for f, turn in ((10, 0.5), (20, 1.0)):
    doc.frame_current = f
    rig.bone_set("a", angle=turn)
    art.set_point(1, (1.0, 1.0 + turn))
doc.frame_current = 1
doc.frame_current = 0

# Only the bone layer picked, none of its bones; the bone's and a point's paths pinned, so they show unpicked.
for l in layers.all():
    l.selected = l.id == rig.id
layers.active = next(l for l in layers.all() if l.id == rig.id)
ops.armature.select_none()
doc.timeline_only_selected = True
doc.frame_current = 15
assert ops.wm.tool_motion_path() == {'FINISHED'}
assert ops.anim.motion_path_pin(layer=str(rig.id), bone="a", pinned="1") == {'FINISHED'}
assert ops.anim.motion_path_pin(layer=str(art.id), point="2", pinned="1") == {'FINISHED'}


def rows():
    return {r["label"]: r for r in wm.timeline_row_details(True)}


assert list(rows()) == ["Rig"], ("nothing picked in the bone layer: its name alone", list(rows()))

# A key picked on the bone's path: its bone's rows show, red, the stretch teal.
assert ops.anim.motion_path_select(bone="a", frame="10", layer=str(rig.id)) == {'FINISHED'}
r = rows()
assert "a" in r and r["a"]["red"], ("the bone picked on its path shows", list(r))
assert r["Angle"]["teal"] == (10, 20), r["Angle"]
assert r["Rig"]["red"], "the layer holds a pick"

# Nothing picked on the paths: back to the name alone.
assert ops.anim.motion_path_deselect_all() == {'FINISHED'}
assert list(rows()) == ["Rig"], list(rows())

# A key picked on the point's path: its layer shows, neither selected nor edited.
assert ops.anim.motion_path_select(layer=str(art.id), point="2", frame="10") == {'FINISHED'}
r = rows()
assert "Art" in r and r["Art"]["red"], ("the point's layer shows", list(r))

# Another tool: what was picked on the paths doesn't count.
assert ops.wm.tool_select() == {'FINISHED'}
assert "Art" not in rows(), list(rows())

print("test_timeline_path_picks: ok")
