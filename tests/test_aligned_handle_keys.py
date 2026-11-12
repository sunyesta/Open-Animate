"""An aligned point's two handle keys on one frame play alike: Set Interpolation on one sets the other's on that frame,
and Align Handles makes the turned handle's keys play as the other's (keys set apart while the two were free). Played
apart (one Smooth, one Linear), the two handles turned apart between keys and the point bent by itself, 3.7 degrees.

Run with:  OpenAnimate --background --python tests/test_aligned_handle_keys.py
"""

import math

import oanim

ops, doc, layers = oanim.ops, oanim.data.document, oanim.data.layers
IN, OUT = "curves[0].points[1].handle_in", "curves[0].points[1].handle_out"


def scene(whole):
    ops.wm.read_homefile()
    doc.auto_key = True
    doc.auto_freeze_keys = True
    doc.frame_current = 0
    layer = layers.active
    layer.key_whole_drawing = whole
    layer.add_curve([(0.0, 0.0), (1.0, 0.5), (2.0, 0.0)])
    ops.mesh.select_none()
    assert layer.curve_handles(0)[1][0] == "ALIGNED"
    return layer


def keys(layer, path):
    return [(k['frame'], k['interp']) for k in layer.keyframes(path)]


def linear_at_45(layer):
    """The out handle keyed on 45 and made Linear (by the operator)."""
    layer.keyframe_insert(OUT, 45)
    doc.frame_current = 0
    assert ops.anim.keys_select(frame_start="45", frame_end="45", layers=str(layer.id), path=OUT) == {'FINISHED'}
    assert ops.anim.keys_interpolation_set(interp="LINEAR") == {'FINISHED'}


def drag_out_on_20(layer):
    doc.frame_current = 20
    _, i, o = layer.curve_handles(0)[1]
    q = layer.points[1][:2]
    v = (o[0] - q[0], o[1] - q[1])
    a = math.radians(-25)
    layer.move_handle(0, 1, "OUT", (q[0] + v[0] * math.cos(a) - v[1] * math.sin(a),
                                     q[1] + v[0] * math.sin(a) + v[1] * math.cos(a)))
    doc.frame_current = 21


def bent(layer):
    worst = 0.0
    for f in range(0, 50):
        doc.frame_current = f
        _, i, o = layer.curve_handles(0)[1]
        q = layer.points[1][:2]
        a, b = (q[0] - i[0], q[1] - i[1]), (o[0] - q[0], o[1] - q[1])
        worst = max(worst, abs(math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))))
    return worst


# --- Set Interpolation on one handle's key: the other's on that frame takes it too ----------------------------------
layer = scene(whole=True)
linear_at_45(layer)
assert dict(keys(layer, IN)).get(45) == 'LINEAR', (keys(layer, IN), keys(layer, OUT))
drag_out_on_20(layer)
assert bent(layer) < 0.05, ("the point bent by itself", bent(layer), keys(layer, IN), keys(layer, OUT))

# --- Aligned again after a key was set apart: the turned handle's keys play as the other's ---------------------------
layer = scene(whole=False)
layer.select_points([1])
assert ops.mesh.handles_unalign() == {'FINISHED'}
ops.mesh.select_none()
doc.frame_current = 45
_, i, o = layer.curve_handles(0)[1]
layer.move_handle(0, 1, "OUT", (o[0], o[1] + 0.1))
doc.frame_current = 0
assert ops.anim.keys_select(frame_start="45", frame_end="45", layers=str(layer.id), path=OUT) == {'FINISHED'}
assert ops.anim.keys_interpolation_set(interp="LINEAR") == {'FINISHED'}
assert dict(keys(layer, IN)).get(45) == 'SMOOTH', "free: each its own"
ops.anim.keys_deselect_all()
layer.select_points([1])
assert ops.mesh.handles_align() == {'FINISHED'}
ops.mesh.select_none()
assert keys(layer, IN) == keys(layer, OUT), (keys(layer, IN), keys(layer, OUT))
drag_out_on_20(layer)
assert bent(layer) < 0.05, ("the point bent by itself", bent(layer), keys(layer, IN), keys(layer, OUT))

print("test_aligned_handle_keys: ok")
