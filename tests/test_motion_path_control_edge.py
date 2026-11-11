"""A path control point on a knob held at its box's edge (Contain Knob in Box): it moves. The nudges that measure how
the place follows the value were clamped by the edge going out, so it had no slope that way and every drag of the
point, its handles or a key's handles at the edge was refused ("No such control point"). Measured the other way there:
dragged in it follows the mouse; dragged out it stays on the edge, following along it; dragged past the far edge it
stops there, where it can still be dragged back.

Run with:  OpenAnimate --background --python tests/test_motion_path_control_edge.py
"""

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

ops.wm.read_homefile()
doc.auto_key = True
ops.layer.new_bone()
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
bone = lambda n: next(b for b in rig().bones if b["name"] == n)
ops.armature.bone_add(name="Knob", head_x="3.0", head_y="3.0", tail_x="3.5", tail_y="3.0")
ops.armature.select_none()
ops.armature.bone_add(name="Lid", head_x="0.0", head_y="4.0", tail_x="1.0", tail_y="4.0")
ops.armature.select_none()


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


# The knob's sides turn Lid.
for side in ("Right", "Up"):
    assert ops.anim.action_new(name="Knob " + side) == {'FINISHED'}
    doc.frame_current = 24
    rig().bone_set("Lid", angle=bone("Lid")["setup_angle"] + 0.1)
    doc.frame_current = 25
    ops.anim.action_set(name="")
    doc.frame_current = 0
rig().select_bone("Knob")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("RIGHT", "UP"):
    assert ops.armature.controller_side(side=side, action="Knob " + side.title()) == {'FINISHED'}
assert bone("Knob")["contain_knob"], "Contain Knob in Box is on by default"
(lo_x, lo_y), (hi_x, hi_y) = bone("Knob")["controller_box"]
assert hi_y > lo_y + 1 and hi_x > lo_x + 1, bone("Knob")["controller_box"]

# Keyed along the top edge: on 10 and on 30.
doc.frame_current = 10
rig().bone_set("Knob", knob=(lo_x + 0.25 * (hi_x - lo_x), hi_y))
doc.frame_current = 30
rig().bone_set("Knob", knob=(lo_x + 0.75 * (hi_x - lo_x), hi_y))
settle()
doc.auto_key = False
assert abs(bone("Knob")["knob"][1] - hi_y) < 1e-4, ("on the top edge", bone("Knob")["knob"], hi_y)

doc.motion_paths = True
doc.path_all = True
assert ops.wm.tool_motion_path() == {'FINISHED'}
layers.active = rig()
args = dict(bone="Knob", head="1", layer=str(rig_id))
assert ops.anim.motion_path_select(frame="30", **args) == {'FINISHED'}
assert ops.anim.motion_path_control_add(frame="20", **args) == {'FINISHED'}


def control():
    cs = wm.motion_path_controls()
    assert len(cs) == 1, cs
    return cs[0]


def move(x, y):
    c = control()
    return ops.anim.motion_path_control_move(frame=str(c["end"]), index=str(c["index"]), x=str(x), y=str(y), **args)


top = control()["at"]

# --- Its handles and a key's at the edge -------------------------------------------------------------------------------
c = control()
assert ops.anim.motion_path_control_handle_move(frame=str(c["end"]), index=str(c["index"]), out="1",
                                                x=str(top[0] + 0.01), y=str(top[1] - 0.005), **args) == {'FINISHED'}, \
    "a control point's handle on the edge moves"
assert ops.ed.undo() == {'FINISHED'}
assert ops.anim.motion_path_handle(frame="10", side="OUT", x=str(top[0]), y=str(top[1] - 0.005), **args) == \
    {'FINISHED'}, "a key's handle on the edge moves"
assert ops.ed.undo() == {'FINISHED'}
assert abs(control()["at"][1] - top[1]) < 1e-6

# --- Dragged in, off the edge: it follows the mouse --------------------------------------------------------------------
assert move(top[0], top[1] - 0.002) == {'FINISHED'}, "the control point on the edge moves in"
at = control()["at"]
assert abs(at[1] - (top[1] - 0.002)) < 1e-4 and abs(at[0] - top[0]) < 1e-4, ("where the mouse is", at, top)

# --- Dragged past the far edge: it stops there, and still moves back ---------------------------------------------------
assert move(top[0], top[1] - 10.0) == {'FINISHED'}
bottom = control()["at"][1]
assert bottom < top[1] - 0.004, ("down to the bottom edge", bottom, top)
assert move(top[0], top[1] - 20.0) == {'FINISHED'}
assert abs(control()["at"][1] - bottom) < 0.02 * (top[1] - bottom), "held at the bottom edge"
middle = 0.5 * (top[1] + bottom)
assert move(top[0], middle) == {'FINISHED'}, "back from the far edge"
assert abs(control()["at"][1] - middle) < 0.02 * (top[1] - bottom), ("back in the box", control()["at"], middle)

# --- Dragged out past the top, and along: it goes to the edge and follows along it -------------------------------------
for _ in range(3):
    assert move(top[0] + 0.01, top[1] + 5.0) == {'FINISHED'}
at = control()["at"]
assert abs(at[1] - top[1]) < 0.01 * (top[1] - bottom), ("on the top edge", at, top)
assert abs(at[0] - (top[0] + 0.01)) < 1e-4, ("along the edge with the mouse", at, top)
wm.motion_path_places_clear()
assert move(top[0] - 0.01, top[1] + 5.0) == {'FINISHED'}, "on the edge, still moves along it"
places = wm.motion_path_places()["places"]
assert abs(control()["at"][0] - (top[0] - 0.01)) < 1e-4, control()["at"]
print("places for a drag along the edge:", places)
assert places <= 16, (f"a drag out along the edge worked out {places} places: the edge found from two a way, as each is "
                      "a whole frame worked out on a rig")
assert abs(bone("Knob")["knob"][1] - hi_y) < 1e-4, "the knob itself still on its key's edge"

print("test_motion_path_control_edge: ok")
