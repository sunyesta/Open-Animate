"""Edges and Strokes modes pick the line nearest the click across every drawing being edited (not the first drawing with
a line within reach), a click on a line's painted width counting as on it; in Strokes mode a line under the mouse beats
a point of another line beside it; clicking again in the same place picks the next line there (a lid over an eye's
white), and a press in Edges mode grabs the line a click would pick.

Run with:  OpenAnimate --background --python tests/test_line_pick.py
"""

import oanim

ops = oanim.ops
ZOOM = 1000.0  # pixels per unit


def scene(*curves):
    """A new file with a drawing per curve [(name, points, line width)], all picked; the first one active."""
    assert ops.wm.read_homefile() == {'FINISHED'}
    made = []
    for name, points, width in curves:
        assert ops.layer.new() == {'FINISHED'}
        layer = oanim.data.layers.active
        layer.name = name
        layer.add_curve(points)
        layer.set_shape_style(0, line_width=width)
        made.append(layer)
    for layer in made:
        layer.selected = True
    oanim.data.layers.active = made[0]
    return made


def picked():
    """{drawing name: its selected points} for the drawings with any."""
    return {l.name: [i for i, p in enumerate(l.points) if p[2]] for l in oanim.data.layers.all()
            if l.type == "VECTOR" and any(p[2] for p in l.points)}


def click(x, y):
    oanim.wm.select_click(x, y, ZOOM)
    return picked()


# --- Edges: the nearest line wins, though the active drawing (first in the list) has one within reach too ---------------
scene(("far", [(-1.0, 0.006), (1.0, 0.006)], 0.0001), ("near", [(-1.0, 0.0), (1.0, 0.0)], 0.0001))
ops.mesh.select_mode_edge()
assert click(0.0, 0.001) == {"near": [0, 1]}, picked()

# --- A click on a thick line's painted width, well away from its middle, picks it ---------------------------------------
scene(("thick", [(-1.0, 0.0), (1.0, 0.0)], 0.1), ("thin", [(-1.0, 0.07), (1.0, 0.07)], 0.0001))
ops.mesh.select_mode_edge()
# 30 pixels from the thick line's middle (its painted half width is 50), 40 from the thin one.
assert click(0.3, 0.03) == {"thick": [0, 1]}, picked()

# --- Strokes: a line under the mouse beats a point of another line beside it --------------------------------------------
scene(("lashes", [(0.0, 1.0), (0.0, 1.2)], 0.004), ("other", [(0.012, 1.1), (0.1, 1.1)], 0.004))
ops.mesh.select_mode_stroke()
# Right on the first lash, 11 pixels from the other's end point (points reach 20).
assert click(0.001, 1.1) == {"lashes": [0, 1]}, picked()
# On the other's end point itself: that stroke.
assert click(0.012, 1.1) == {"other": [0, 1]}, picked()

# --- Clicking again in the same place picks the next line there ----------------------------------------------------------
scene(("lid", [(-1.0, 0.0), (1.0, 0.0)], 0.01), ("white", [(-1.0, 0.001), (1.0, 0.001)], 0.01))
ops.mesh.select_mode_edge()
first = click(0.0, 0.0005)
second = click(0.0, 0.0005)
third = click(0.0, 0.0005)
assert sorted([list(first), list(second)]) == [["lid"], ["white"]], (first, second)
assert third == first, (first, third)

# --- A press in Edges mode grabs the nearest line too --------------------------------------------------------------------
made = scene(("far", [(-1.0, 0.006), (1.0, 0.006)], 0.0001), ("near", [(-1.0, 0.0), (1.0, 0.0)], 0.0001))
ops.mesh.select_mode_edge()
grab = oanim.wm.select_press_grab(0.0, 0.001, ZOOM)
assert grab == [(made[1].id, [0, 1])], grab

print("test_line_pick: OK")
