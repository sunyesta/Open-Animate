"""Shift Alt click on a second drawing's row (keyed whole: Key Whole Drawing) adds its stretch to the one picked on the first,
one path shown at a time: the first path stays shown beside the second with its pick (its dot is on the timing the
drawing's paths share, which the check for picks on a kept path missed, so the first pick was dropped).

Run with:  OpenAnimate --background --python tests/test_drawing_stretch_add.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.wm.read_homefile()
doc.auto_key = True
doc.path_show_all = False
doc.frame_current = 0
made = []
for name, y in (("top", 1.0), ("bottom", -1.0)):
    assert ops.layer.new() == {'FINISHED'}
    layer = layers.active
    layer.name = name
    layer.add_curve([(0.0, y), (1.0, y), (2.0, y)])
    made.append(layer)
# Each drawing keyed whole on frames 1 and 14.
for f, dx in ((1, 0.2), (14, 0.5)):
    doc.frame_current = f
    for layer in made:
        p = layer.points[0]
        layer.set_point(0, (dx, p[1]))
doc.frame_current = 7
for layer in made:
    layer.selected = True
    layer.select_points(range(3))
layers.active = made[0]
assert ops.wm.tool_motion_path() == {'FINISHED'}


def drawing_rows():
    """The rows and the two drawings' own rows (a lone drawing's row keys it whole, chained shut)."""
    rows = wm.timeline_row_details(as_shown=True)
    return rows, [next(i for i, r in enumerate(rows) if r["name"] == l.name) for l in made]


rows, picks = drawing_rows()
assert all(rows[i]["stretch_pickable"] for i in picks), [(r["name"], r["chain"]) for r in rows]
assert all(rows[i]["frames"][-2:] == [1, 14] for i in picks), [rows[i]["frames"] for i in picks]

assert wm.timeline_row_alt_click(picks[0], 5)
assert wm.timeline_row_alt_click(picks[1], 6, shift=True)
rows, picks = drawing_rows()
assert [rows[i]["teal_spans"] for i in picks] == [[(1, 14, False)], [(1, 14, True)]], [rows[i]["teal_spans"] for i in picks]
assert sorted(d["frame"] for d in wm.motion_path_dots()) == [5, 6], wm.motion_path_dots()
assert len(wm.motion_paths()) == 2, ("the first path kept beside the second", [p["label"] for p in wm.motion_paths()])

# Without Shift the second pick takes the first's place.
assert wm.timeline_row_alt_click(picks[0], 4)
rows, picks = drawing_rows()
assert [rows[i]["teal_spans"] for i in picks] == [[(1, 14, True)], []], [rows[i]["teal_spans"] for i in picks]

print("test_drawing_stretch_add: OK")
