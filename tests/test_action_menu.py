"""The timeline's action menu: Mainline on top, a filter, and two tabs. Actions: New first, then the ordinary actions.
Bone actions: the selected bone's block first (with New while it has room), then each bone's in the order they were
made (a controller's sides Right, Left, Up, Down; a bone's turns counterclockwise first), each with its arrow, then the
fixes with how much each plays. The menu opens on the edited action's tab.

Run with:  OpenAnimate --background --python tests/test_action_menu.py
"""

import math

import oanim

ops, doc, layers, wm = oanim.ops, oanim.data.document, oanim.data.layers, oanim.wm

assert ops.wm.read_homefile() == {'FINISHED'}
doc.auto_key = True
doc.auto_freeze_keys = False
assert ops.layer.new_bone() == {'FINISHED'}
rig_id = layers.active.id
rig = lambda: next(l for l in layers.all() if l.id == rig_id)
for name, y in (("arm", 0.0), ("lid", 1.0), ("eye", 2.0), ("leg", 3.0)):
    ops.armature.select_none()
    assert ops.armature.bone_add(name=name, head_x="0.0", head_y=str(y), tail_x="1.0", tail_y=str(y)) == {'FINISHED'}
ops.armature.select_none()


def settle():
    doc.frame_current += 1
    doc.frame_current -= 1


def mainline():
    assert ops.anim.action_set(name="") == {'FINISHED'}
    doc.frame_current = 0


def key_turn(action, bone, angle):
    """An action bone action of `bone`, its turn keyed to `angle` on frame 24."""
    layers.active = rig()
    assert ops.anim.action_new(name=bone, action_bone="1") == {'FINISHED'} and doc.action == action, doc.action
    doc.frame_current = 24
    rig().bone_set(bone, angle=angle)
    settle()
    mainline()


def rows(filter=""):
    return wm.action_menu_rows(filter)


def tab(t, filter=""):
    return [(r["group"], r["name"], r["arrow"]) for r in rows(filter) if r["tab"] == t]


# Ordinary actions.
for name in ("wave", "Walk"):
    layers.active = rig()
    assert ops.anim.action_new(name=name) == {'FINISHED'}
    doc.frame_current = 10
    rig().bone_set("leg", angle=0.3)
    settle()
    mainline()
# arm: clockwise first ("arm", the right arrow), then counterclockwise ("arm 2", the left).
key_turn("arm", "arm", -0.5)
key_turn("arm 2", "arm", 0.5)
# lid: a whole turn, 360.
key_turn("lid", "lid", 2.0 * math.pi)
# eye: a 2 Axis Controller, its sides made Up, Right, Down, Left.
for side in ("Up", "Right", "Down", "Left"):
    layers.active = rig()
    assert ops.anim.action_new(name="eye " + side) == {'FINISHED'}
    doc.frame_current = 24
    rig().bone_set("leg", angle=0.2)
    settle()
    mainline()
rig().select_bone("eye")
assert ops.armature.bone_convert(type="CONTROLLER_2D") == {'FINISHED'}
for side in ("UP", "RIGHT", "DOWN", "LEFT"):
    assert ops.armature.controller_side(side=side, action="eye " + side.title()) == {'FINISHED'}
# A fix following eye and arm.
rig().select_bone("eye")
rig().select_bone("arm", extend=True)
assert ops.armature.bone_fix_new(bones="eye,arm") == {'FINISHED'}
fix = rig().bone_fixes[0]["name"]
mainline()
ops.armature.select_none()

# --- Mainline on top, then the Actions tab: New first, the ordinary actions only ---------------------------------------
all_rows = rows()
assert all_rows[0]["tab"] == -1 and all_rows[0]["name"] == "", all_rows[0]
assert tab(0) == [("", "", None), ("", "wave", None), ("", "Walk", None)], tab(0)
assert [r["add"] for r in all_rows if r["tab"] == 0] == [True, False, False]

# --- The Bone actions tab: each bone's in the order made, arrows, the sides in order, the fixes last -------------------
assert tab(1) == [("arm", "arm 2", "LEFT"), ("arm", "arm", "RIGHT"),
                  ("lid", "lid", "LEFT"),
                  ("eye", "eye Right", "RIGHT"), ("eye", "eye Left", "LEFT"), ("eye", "eye Up", "UP"),
                  ("eye", "eye Down", "DOWN"),
                  ("Fixes", fix, None)], tab(1)
bone_rows = [r for r in all_rows if r["tab"] == 1]
assert [r["group_kind"] for r in bone_rows] == [1, 1, 1, 2, 2, 2, 2, 3], bone_rows
assert [r["full_turn"] for r in bone_rows if r["group"] == "lid"] == [True], "lid's whole turn shows 360"
assert not any(r["full_turn"] for r in bone_rows if r["group"] != "lid")
assert [r["strength"] is not None for r in bone_rows] == [False] * 7 + [True], "only the fix has a share"
assert not any(r["picked"] for r in all_rows), "nothing selected: no block"

# --- The selected bone's block, first and red ---------------------------------------------------------------------------
rig().select_bone("eye")
picked = [(r["group"], r["name"], r["add"]) for r in rows() if r["picked"]]
assert picked == [("eye", "eye Right", False), ("eye", "eye Left", False), ("eye", "eye Up", False),
                  ("eye", "eye Down", False)], ("a controller: its sides, no New", picked)
assert tab(1)[:4] == [("eye", "eye Right", "RIGHT"), ("eye", "eye Left", "LEFT"), ("eye", "eye Up", "UP"),
                      ("eye", "eye Down", "DOWN")], tab(1)
assert [g for g, _, _ in tab(1)].count("eye") == 4, "not listed twice"
rig().select_bone("lid")
assert [(r["name"], r["add"]) for r in rows() if r["picked"]] == [("lid", False)], "a whole turn has no room for more"
rig().select_bone("arm")
assert [(r["name"], r["add"]) for r in rows() if r["picked"]] == [("arm 2", False), ("arm", False)], "both ways made"
rig().select_bone("leg")
assert [(r["group"], r["name"], r["add"]) for r in rows() if r["picked"]] == [("leg", "", True)], \
    "a bone with none: New alone"
assert tab(1)[0] == ("leg", "", None), tab(1)
# New makes it (as the row does), and it stays there while there is room the other way.
assert ops.anim.action_new(name="leg", action_bone="1") == {'FINISHED'} and doc.action == "leg"
mainline()
rig().select_bone("leg")
assert [(r["name"], r["add"], r["arrow"]) for r in rows() if r["picked"]] == [("", True, None), ("leg", False, "LEFT")], \
    rows()
assert "leg" not in [r["name"] for r in rows() if r["tab"] == 0], "an action bone action isn't an ordinary action"
# Two bones selected: no block.
rig().select_bone("arm", extend=True)
assert not any(r["picked"] for r in rows())
ops.armature.select_none()

# --- The filter: any case, a bone's name brings all its actions; New stays ----------------------------------------------
assert tab(0, "WAV") == [("", "", None), ("", "wave", None)], tab(0, "WAV")
assert [n for _, n, _ in tab(1, "WAV")] == [], tab(1, "WAV")
assert [n for _, n, _ in tab(1, "eye")] == ["eye Right", "eye Left", "eye Up", "eye Down"] + \
    ([fix] if "eye" in fix.lower() else []), tab(1, "eye")
assert [n for _, n, _ in tab(1, "up")] == ["eye Up"], tab(1, "up")
assert rows("zzz")[0]["tab"] == -1, "Mainline always"

# --- Which tab it opens on: the edited action's ------------------------------------------------------------------------
assert ops.anim.action_set(name="wave") == {'FINISHED'}
assert wm.action_menu_tab() == 0
assert ops.anim.action_set(name="arm 2") == {'FINISHED'}
assert wm.action_menu_tab() == 1
assert ops.anim.action_set(name=fix) == {'FINISHED'}
assert wm.action_menu_tab() == 1
mainline()
assert wm.action_menu_tab() == 0, "the mainline: the last used (Actions, never opened here)"

print("Action menu tests passed")
