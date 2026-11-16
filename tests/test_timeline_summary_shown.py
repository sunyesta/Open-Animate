"""The timeline's Summary row shows and acts on only the keys of the rows shown: with a filter on (kinds, Changed, the
search) the keys of the rows it takes away are neither drawn on the Summary nor picked, moved or keyed through it.

Run with:  OpenAnimate --background --python tests/test_timeline_summary_shown.py
"""

import oanim

ops, wm = oanim.ops, oanim.wm


def scene():
    """A bone layer: its position keyed on 10 and 30, bone arm on 20 and 30, bone leg on 30; every row listed."""
    global doc, layers, rig
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc, layers = oanim.data.document, oanim.data.layers
    doc.frame_current = 0
    doc.auto_key = False
    doc.auto_freeze_keys = False
    assert ops.layer.new_bone() == {'FINISHED'}
    rig = layers.active
    rig.name = "rig"
    ops.armature.bone_add(name="arm", head_x="0", head_y="0", tail_x="1", tail_y="0")
    ops.armature.bone_add(name="leg", head_x="0", head_y="0", tail_x="0", tail_y="-1")
    for frame, path in ((10, "position"), (20, 'bones["arm"].angle'), (30, "position"), (30, 'bones["arm"].angle'),
                        (30, 'bones["leg"].angle')):
        doc.frame_current = frame
        if path == "position":
            rig.location_x = frame / 100.0
        else:
            rig.bone_set(path.split('"')[1], angle=frame / 100.0)
        rig.keyframe_insert(path)
    doc.frame_current = 0
    assert ops.armature.select_none() == {'FINISHED'}
    doc.timeline_only_selected = False
    assert ops.anim.keys_deselect_all() == {'FINISHED'}


def summary():
    rows = wm.timeline_row_details(True)
    at = next(i for i, r in enumerate(rows) if r["summary"])
    return at, set(rows[at]["frames"])


def frames(path):
    return sorted(k["frame"] for k in rig.keyframes(path))


def picked(path):
    return sorted(k["frame"] for k in rig.keyframes(path) if k["selected"])


ARM, LEG = 'bones["arm"].angle', 'bones["leg"].angle'

# --- No filter: the Summary shows every key -----------------------------------------------------------------------------
scene()
_, shown = summary()
assert {10, 20, 30} <= shown, shown

# --- Kinds: just the bones. The position's frame 10 isn't on the Summary; a drag there moves the bones' keys only --------
scene()
assert ops.anim.timeline_filter(kinds="BONES") == {'FINISHED'}
row, shown = summary()
assert 10 not in shown and {20, 30} <= shown, ("the position's key isn't shown", shown)
assert wm.timeline_key_press(row, 30, to_frame=33)
assert frames("position") == [0, 10, 30], ("the position's key stays", frames("position"))
assert 33 in frames(ARM) and 33 in frames(LEG) and 30 not in frames(LEG), (frames(ARM), frames(LEG))

# --- Search: only leg's rows. A click picks leg's key alone; a double-click picks every key leg's rows show -------------
scene()
assert ops.anim.timeline_filter(search="leg") == {'FINISHED'}
row, shown = summary()
assert shown - {0} == {30}, ("only leg's keys (and the setup)", shown)
assert wm.timeline_key_press(row, 30)
assert picked(LEG) == [30] and picked(ARM) == [] and picked("position") == [], (picked(LEG), picked(ARM))
assert wm.timeline_key_press(row, 30, double_click=True)
assert picked(ARM) == [] and picked("position") == [], ("nothing hidden picked", picked(ARM), picked("position"))

# --- Keying the Summary (a double-click off its keys) keys only the channels shown ---------------------------------------
doc.frame_current = 40
args = {"layers": str(rig.id), "kinds": str(0xffffffff), "frame": "40", "summary": "1"}
assert ops.anim.keys_insert(**args) == {'FINISHED'}
assert 40 in frames(LEG) and 40 not in frames(ARM) and 40 not in frames("position"), \
    (frames(LEG), frames(ARM), frames("position"))

# --- Changed: a channel whose keys hold one value goes, and with it its keys on the Summary -----------------------------
scene()
doc.frame_current = 50
rig.keyframe_insert("opacity")
assert 50 in frames("opacity")
assert ops.anim.timeline_filter(show="CHANGED") == {'FINISHED'}
row, shown = summary()
assert 50 not in shown, ("opacity's one value isn't a change", shown)

# --- Filters off again: the Summary acts on everything, as before -------------------------------------------------------
assert ops.anim.timeline_filter(show="ANIMATED", kinds="ALL", search="") == {'FINISHED'}
row, shown = summary()
assert {10, 20, 30, 50} <= shown, shown
assert wm.timeline_key_press(row, 30)
assert picked("position") == [30] and picked(ARM) == [30] and picked(LEG) == [30]

print("timeline summary shown: ok")
