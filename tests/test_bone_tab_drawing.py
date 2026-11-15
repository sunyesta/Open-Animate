"""The Bone tab as Drawing: with a bone layer worked in and only points of the drawings edited with its bones picked,
the tab is called Drawing and shows those drawings' colour (a bone colour set, their wires and points drawn in it) and
collections; Bone Constraints goes while it does. A bone picked brings the Bone tab back.

Run with:  OpenAnimate --background --python tests/test_bone_tab_drawing.py
"""

import pathlib
import tempfile

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.layer.new_bone()
rig = layers.active
ops.armature.bone_add(name="jaw", head_x="-3.0", head_y="0.0", tail_x="-1.0", tail_y="0.0")
for name, y in (("Mouth", -2.0), ("Nose", 2.0)):
    ops.layer.new()
    l = layers.active
    l.name = name
    l.add_curve([(0.0, y), (1.0, y), (0.5, y + 1.0)], closed=True)
    ops.layer.move_to_group(group=str(rig.id))
mouth = next(l for l in layers.all() if l.name == "Mouth")
nose = next(l for l in layers.all() if l.name == "Nose")
mouth.edit_with_bones = True
nose.edit_with_bones = True
layers.active = rig


def picked(bone=False, mouth_points=(), nose_points=()):
    layers.active = rig
    ops.armature.select_none()
    for l in (mouth, nose):
        l.select_points(range(len(l.points)), False)
    if bone:
        rig.select_bone("jaw", extend=True)
    mouth.select_points(mouth_points)
    nose.select_points(nose_points)


# --- Which tab: Bone with a bone picked, Drawing with only points ------------------------------------------------------
picked(bone=True)
tabs = wm.properties_tabs()
assert "Bone" in tabs and "Bone Constraints" in tabs and "Drawing" not in tabs, tabs
picked(mouth_points=[1])
tabs = wm.properties_tabs()
assert "Drawing" in tabs and "Bone" not in tabs and "Bone Constraints" not in tabs, tabs
# A bone picked beside the points (Shift): the bone's tab.
picked(bone=True, mouth_points=[1])
tabs = wm.properties_tabs()
assert "Bone" in tabs and "Bone Constraints" in tabs, tabs
# Nothing picked: the Bone tab, as before.
picked()
assert "Bone" in wm.properties_tabs()

# --- Color: on every drawing with points picked, one undo step ---------------------------------------------------------
picked(mouth_points=[1], nose_points=[0])
assert mouth.color_set == "DEFAULT"
assert ops.layer.color_set(color_set="THEME04") == {'FINISHED'}
assert (mouth.color_set, nose.color_set) == ("THEME04", "THEME04"), (mouth.color_set, nose.color_set)
assert ops.layer.color_set(color_set="THEME04") == {'CANCELLED'}, "as it already is: nothing to do"
assert oanim.ops.ed.undo() == {'FINISHED'}
assert (mouth.color_set, nose.color_set) == ("DEFAULT", "DEFAULT")
assert oanim.ops.ed.redo() == {'FINISHED'}
assert mouth.color_set == "THEME04"
# Named drawings only.
assert ops.layer.color_set(color_set="THEME01", layers=str(nose.id)) == {'FINISHED'}
assert (mouth.color_set, nose.color_set) == ("THEME04", "THEME01")

# --- Drawn in it: wires and points in the regular shade, picked points in the selected one ------------------------------
picked(mouth_points=[1])
c = wm.overlay_colors(mouth, left=(1.0, 1.0, 1.0), right=(1.0, 1.0, 1.0))
wire_colors = {w["color"].lower() for w in c["wires"]}
assert "#0a3694" in wire_colors, ("the wires in 04 - Blue's regular shade", wire_colors)
points = {tuple(round(v, 3) for v in p["at"]): p["color"].lower() for p in c["points"]}
assert points[(1.0, -2.0)] == "#3667df", ("the picked point in its selected shade", points)
assert points[(0.0, -2.0)] == "#0a3694", ("the others in its regular shade", points)
# Default Colors: the overlays' own, as before.
mouth.color_set = "DEFAULT"
c = wm.overlay_colors(mouth, left=(1.0, 1.0, 1.0), right=(1.0, 1.0, 1.0))
assert "#0a3694" not in {w["color"].lower() for w in c["wires"]}
points = {tuple(round(v, 3) for v in p["at"]): p["color"].lower() for p in c["points"]}
assert points[(1.0, -2.0)] == "#ff8c00", points
mouth.color_set = "THEME04"

# --- Collections: the drawings named with it ---------------------------------------------------------------------------
assert ops.layer.collection_link(layer=str(mouth.id), layers=str(nose.id), collection="Face") == {'FINISHED'}
assert mouth.collections == ["Face"] and nose.collections == ["Face"], (mouth.collections, nose.collections)

# --- Saved and opened as it was ----------------------------------------------------------------------------------------
mouth.color_set = "CUSTOM"
path = str(pathlib.Path(tempfile.mkdtemp(prefix="oanim_bone_tab_drawing_")) / "drawing_color.oanim")
assert ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
assert ops.wm.open_mainfile(filepath=path, confirmed="1") == {'FINISHED'}
mouth = next(l for l in layers.all() if l.name == "Mouth")
nose = next(l for l in layers.all() if l.name == "Nose")
assert (mouth.color_set, nose.color_set) == ("CUSTOM", "THEME01"), (mouth.color_set, nose.color_set)

print("bone tab drawing: ok")

# --- The last click decides: a point clicked makes it Drawing beside picked bones, a bone clicked makes it Bone ---------
rig = next(l for l in layers.all() if l.type == "BONE")
layers.active = rig
picked(bone=True)
assert "Bone" in wm.properties_tabs()
wm.select_click(1.0, -2.0, 100.0)
assert [p[2] for p in mouth.points] == [False, True, False], "the click picks the point"
assert any(b["selected"] for b in rig.bones), "the bone stays picked beside it"
tabs = wm.properties_tabs()
assert "Drawing" in tabs and "Bone Constraints" not in tabs, ("the point clicked last", tabs)
wm.bone_press(-2.0, 0.0, 100.0, transform_tool=True, shift=True)
tabs = wm.properties_tabs()
assert "Bone" in tabs and "Bone Constraints" in tabs, ("the bone clicked last", tabs)
wm.select_click(1.0, -2.0, 100.0)
assert "Drawing" in wm.properties_tabs()

# --- Copy Color to Selected from the Drawing tab: to the picked bones and the other drawings, all three shades ----------
mouth.color_set = "THEME04"
mouth.color_set = "CUSTOM"
assert mouth.custom_colors == "#0a3694 #3667df #5ec1ef", ("Custom starts from the set's three shades", mouth.custom_colors)
nose.select_points([0])
assert ops.layer.copy_color_to_selected() == {'FINISHED'}
jaw = next(b for b in rig.bones if b["name"] == "jaw")
assert jaw["color_set"] == "CUSTOM", jaw["color_set"]
hexes = ["#%02x%02x%02x" % tuple(round(v * 255) for v in c) for c in jaw["colors"]]
assert hexes == ["#0a3694", "#3667df", "#5ec1ef"], ("the bone takes all three shades", hexes)
assert (nose.color_set, nose.custom_colors) == ("CUSTOM", "#0a3694 #3667df #5ec1ef"), (nose.color_set, nose.custom_colors)
assert oanim.ops.ed.undo() == {'FINISHED'}
jaw = next(b for b in rig.bones if b["name"] == "jaw")
assert jaw["color_set"] == "DEFAULT" and nose.color_set == "THEME01", "one undo step"

# --- Copy Bone Color to Selected: to the drawings with points picked too ------------------------------------------------
wm.bone_press(-2.0, 0.0, 100.0, transform_tool=True)
assert "Bone" in wm.properties_tabs()
rig.bone_set("jaw", color_set="THEME09")
assert ops.armature.copy_bone_color_to_selected() == {'CANCELLED'}, "nothing else picked"
mouth.select_points([0])
assert ops.armature.copy_bone_color_to_selected() == {'FINISHED'}
assert mouth.color_set == "THEME09" and nose.color_set == "THEME01", (mouth.color_set, nose.color_set)

print("bone tab drawing, copying: ok")
