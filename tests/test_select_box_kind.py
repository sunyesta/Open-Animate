"""The select box's mode by the keys held, as Blender's Select Box: none a new selection, Shift adds, Ctrl takes out (Ctrl
winning over Shift); in the Transform tool's box over bones Alt takes out too, as it did before Ctrl. The same answer
draws the box while it is dragged (white; a "+"; red and dashed with a "-").

Run with:  OpenAnimate --background --python tests/test_select_box_kind.py
"""

import oanim

kind = oanim.wm.select_box_kind

assert kind() == "SET"
assert kind(shift=True) == "ADD"
assert kind(ctrl=True) == "REMOVE", "Ctrl takes out"
assert kind(shift=True, ctrl=True) == "REMOVE", "Ctrl wins over Shift"
assert kind(alt=True) == "SET", "Alt is the Select tool's own (a layer pick), never a box's"

# The Transform tool's box over bones: Ctrl takes out as everywhere (it took only Alt), and Alt still does.
assert kind(ctrl=True, transform_bones=True) == "REMOVE"
assert kind(alt=True, transform_bones=True) == "REMOVE"
assert kind(shift=True, transform_bones=True) == "ADD"
assert kind(transform_bones=True) == "SET"

print("Select box kind tests passed")
