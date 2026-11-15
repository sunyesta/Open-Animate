"""Picking: where a point's handle ends near the point (zoomed out, or points crowded as along a mouth's lips), a click
or press there takes the point; a handle takes it only when clearly nearer than any point, so it can still be picked
where it stands apart.

Run with:  OpenAnimate --background --python tests/test_point_over_handle.py
"""

import math

import oanim

wm = oanim.wm
doc = oanim.data.document
doc.frame_current = 0
oanim.ops.layer.new()
layer = oanim.data.layers.active
layer.add_curve([(0.0, 0.0), (1.0, 0.3), (2.0, 0.0)])
wm.set_overlay("handles", "ALL")

point = layer.points[1][:2]
handle_out = layer.curve_handles(0)[1][2]
length = math.dist(point, handle_out)
assert length > 0.05, ("the middle point has a handle", length)
reach = wm.click_reach()


def zoom_for(pixels):
    """The zoom (pixels per unit) at which the handle's end is `pixels` from its point on screen."""
    return pixels / length


def picked_point():
    return [i for i, p in enumerate(layer.points) if p[2]]


# --- Crowded: the handle's end 5 pixels from its point -----------------------------------------------------------------
zoom = zoom_for(5.0 * reach)
assert wm.select_press_takes(*handle_out, zoom) == "POINT", "pressing on a handle's end next to its point takes the point"
oanim.ops.mesh.select_none()
wm.select_click(*handle_out, zoom)
assert picked_point() == [1], ("a click there picks the point", picked_point())

# --- Apart: the handle's end 24 pixels from its point -------------------------------------------------------------------
zoom = zoom_for(24.0 * reach)
assert wm.select_press_takes(*handle_out, zoom) == "HANDLE", "a handle standing apart is still taken"
wm.select_click(*handle_out, zoom)
assert picked_point() == [], ("a click on it picks the handle alone", picked_point())
# Between, a little nearer the handle (11 pixels against 13): the point.
mid = tuple(p + (h - p) * 0.55 for p, h in zip(point, handle_out))
assert wm.select_press_takes(*mid, zoom) == "POINT"

print("point over handle: ok")
