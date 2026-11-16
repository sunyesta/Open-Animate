"""Picks on motion paths stay only on what is traced: a stretch picked on a bone's path is let go once that bone's path
is no longer traced (its bone let go), with Show All on or one path left, so no dot edit reaches a hidden path; and a
stretch picked by Alt click on a whole drawing's Drawing row or a folded layer's Key Together row, with one of its
points' paths shown, stays picked (its dot is on the timing those paths share).

Run with:  OpenAnimate --background --python tests/test_motion_path_picks_traced.py
"""

# --- Picks on a path no longer traced are let go ---------------------------------------------------------------------
import oanim
ops, layers, wm = oanim.ops, oanim.data.layers, oanim.wm
problems = []
for show_all in (False, True):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc = oanim.data.document
    doc.auto_key = True
    doc.auto_freeze_keys = False
    doc.motion_paths = True
    doc.path_show_all = show_all
    assert ops.layer.new_bone() == {'FINISHED'}
    rig_id = layers.active.id
    rig = lambda: next(l for l in layers.all() if l.id == rig_id)
    for name, x in (("arm", 0.0), ("leg", 3.0)):
        ops.armature.select_none()
        assert ops.armature.bone_add(name=name, head_x=str(x), head_y="0", tail_x=str(x), tail_y="1", parent="") == {'FINISHED'}
    for f, a in ((10, 0.5), (20, -0.3)):
        doc.frame_current = f
        rig().bone_set("arm", angle=a, position=(0.2 * a + 0.5, 0.1 + a))
        rig().bone_set("leg", angle=-a, position=(3.0, 0.2 * a))
    doc.frame_current = 15
    doc.auto_key = False
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    rig().select_bone("arm")
    rig().select_bone("leg", extend=True)
    row = dict(layers=str(rig_id), path='bones["arm"].position', kinds="304")
    assert ops.anim.timeline_stretch_pick(frame="15", **row) == {'FINISHED'}
    assert any(d["frame"] == 15 for d in wm.motion_path_dots()), (wm.motion_path_dots(), wm.motion_paths_traced(), [k["frame"] for k in rig().keyframes('bones["arm"].position')])
    # Only leg picked now (show_all on), or nothing (one path left traced: the layer's): arm's path is not traced.
    if show_all:
        rig().select_bone("leg")
    else:
        ops.armature.select_none()
    traced = wm.motion_paths_traced()
    assert not any(t.startswith("arm") for t in traced), traced
    before = [k.get("timing") for k in rig().keyframes('bones["arm"].position')]
    r = ops.anim.motion_path_dots_slide(x="0.05", y="0.05")
    after = [k.get("timing") for k in rig().keyframes('bones["arm"].position')]
    dots = wm.motion_path_dots()
    if dots or r == {'FINISHED'} or before != after:
        problems.append(f"show_all={show_all}: traced {traced}, dots still {[(d['bone'], d['frame']) for d in dots]}, "
                        f"dots_slide {r}, arm's timing changed={before != after}, panel "
                        f"{(wm.motion_path_timing_panel() or {}).get('label')}")
assert not problems, "picks on a path no longer traced kept and edited: " + " | ".join(problems)

# --- A Drawing or Key Together row's stretch, one of its points' paths shown, stays picked ------------------------------
ops, wm, L = oanim.ops, oanim.wm, oanim.data.layers
got = {}
for kt, show_all in ((False, True), (False, False), (True, True), (True, False)):
    assert ops.wm.read_homefile() == {'FINISHED'}
    doc = oanim.data.document
    doc.auto_key = True
    doc.auto_freeze_keys = False
    doc.motion_paths = True
    doc.path_show_all = show_all
    assert ops.layer.new() == {'FINISHED'}
    lay = L.active
    lid = lay.id
    lay.add_curve([(0.0, 0.0), (1.0, 0.0), (2.0, 0.5)])
    lay.key_together = kt
    assert lay.key_whole_drawing
    for f, dx in ((10, 0.5), (20, 1.5)):
        doc.frame_current = f
        for i in range(3):
            lay.set_point(i, (float(i) + dx, 0.3 * dx * i))
    doc.frame_current = 15
    doc.auto_key = False
    assert ops.wm.tool_motion_path() == {'FINISHED'}
    lay = next(l for l in L.all() if l.id == lid)
    lay.select_points([0, 1])
    rows = wm.timeline_row_details(as_shown=True)
    dr = next(i for i, r in enumerate(rows) if r["chain"] == ("TOGETHER" if kt else "DRAWING"))
    assert wm.timeline_row_alt_click(dr, 15, False), "Alt click picks the drawing's stretch"
    h = wm.timeline_key_header()
    got[kt, show_all] = (len(wm.motion_path_dots()), h.get("picked"), wm.timing_chart_rows(), [p["label"] for p in wm.motion_paths()])
bad = []
for kt in (False, True):
    a, b = got[kt, True], got[kt, False]
    assert a[0] == 1 and a[1], a
    if b[:3] != a[:3]:
        bad.append(f"{'Key Together row' if kt else 'Drawing row'}, one path shown: after the Alt click {b[0]} dots picked "
                   f"(Show All: {a[0]}), header picked {b[1]} ({a[1]}), timing chart rows {b[2]} ({a[2]}), shown {b[3]}")
assert not bad, " | ".join(bad)

print("motion path picks traced: ok")
