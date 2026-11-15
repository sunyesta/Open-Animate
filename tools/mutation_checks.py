"""Mutation checks, batched until a milestone: each proves a test fails without the fix it guards.

Each feature adds an entry to PENDING for every fix it makes: the file, a piece of its code (found exactly once), what
to put there instead to undo the fix, a name, and the test that should then fail. They are run together when the user
says "run milestone checks":

    python tools/mutation_checks.py              # every pending check
    python tools/mutation_checks.py 3 7          # only those
    python tools/mutation_checks.py --lanes 6    # six at once (this folder and five lane folders)
    python tools/mutation_checks.py --lanes 6 --prepare   # only make and build the lane folders
    python tools/mutation_checks.py --lanes 6 --not-here  # the five lane folders only: this one stays free to edit
    python tools/mutation_checks.py --remove-lanes

Lanes: a check edits the source and rebuilds, so checks run side by side only in folders of their own. --lanes N uses
this folder and N-1 lane worktrees beside it (<this folder's name>-mut1, ...), made on first use (a configure and full
build, about ten minutes, reusing this build's fetched sources) and kept for the next run; each run brings them to this
folder's commit plus its uncommitted changes. A lane takes the next check on the file it last changed when there is
one, so each rebuild compiles one file. --remove-lanes deletes them.

Run it from the worktree's root, with nothing else building or editing the source there: it changes one file at a
time, rebuilds (for C++), runs the test and puts the file back. A check the test still passes is "NOT CAUGHT": the
test is strengthened until it fails. Once every check is caught and committed, PENDING is emptied.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading

CMAKE = (r"C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/Common7/IDE/CommonExtensions/Microsoft/"
         r"CMake/CMake/bin/cmake.exe")
EXE = os.path.join("build", "bin", "RelWithDebInfo", "OpenAnimate.exe")

# (file, old, new, name, test)
PENDING = [
    ('src/ops/anim_ops.cc', 'const int frame = std::clamp(op_arg_int(C, "frame", doc.frame_current), 0, KEY_FRAME_LAST);\n                      if (frame != doc.frame_current) {', 'const int frame = std::max(0, op_arg_int(C, "frame", doc.frame_current));\n                      if (frame != doc.frame_current) {',
     'Insert Keys in Row past the last frame keys the last frame', 'tests/test_frame_last_noop.py'),
    ('src/ops/builtin_ops.cc', 'C.document->frame_current = std::min(C.document->frame_current, KEY_FRAME_LAST - 1) + 1;', 'C.document->frame_current++;',
     'Next Frame on the last frame stays there', 'tests/test_frame_last_noop.py'),
    ('src/io/oanim_file.cc', 'doc.frame_current = std::clamp(get_int(j, "frame_current", doc.frame_current), 0, KEY_FRAME_LAST);', 'doc.frame_current = std::max(0, get_int(j, "frame_current", doc.frame_current));',
     'A file saved past the last frame opens on the last', 'tests/test_frame_last_noop.py'),
    ('src/ops/anim_ops.cc', '      if (doc.layers == was) {\n        return OpStatus::Cancelled;\n      }\n      return OpStatus::Finished;\n    };\n    operators().add(std::move(ot));\n  }\n  {\n    OperatorType ot;\n    ot.idname = "anim.action_move";', '      return OpStatus::Finished;\n    };\n    operators().add(std::move(ot));\n  }\n  {\n    OperatorType ot;\n    ot.idname = "anim.action_move";',
     'Set Action as it already is makes no undo step', 'tests/test_frame_last_noop.py'),
    ('src/ops/anim_ops.cc', 'plays.erase(std::remove(plays.begin(), plays.end(), at_rest), plays.end());', '(void)plays;',
     'Set Action as it already is keeps no entry for an action at rest', 'tests/test_frame_last_noop.py'),
    ('src/ops/layer_ops.cc', '              !differs("match_original", rs.match_original))\n          {\n            return OpStatus::Cancelled;', '              !differs("match_original", rs.match_original) && false)\n          {\n            return OpStatus::Cancelled;',
     'Reference Settings as they already are makes no undo step', 'tests/test_frame_last_noop.py'),
    ('src/ops/layer_ops.cc', '    if (keep) {\n      drawing_mirror_setup_x_keeping_keys(l.drawing);', '    if (false) {\n      drawing_mirror_setup_x_keeping_keys(l.drawing);',
     "Symmetrize Layers keeps a drawing's keys, mirrored", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '    channel_values_map(copy.rotation_keys, [&](float v) { return copy.rotation - (v - was_turn); });', '    clear_transform_keys(copy);',
     "Symmetrize Layers mirrors the copy's own transform keys", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '      channel_values_map(l.rotation_keys, [](float v) { return -v; });\n      channel_values_map(l.shear_keys', '      channel_values_map(l.rotation_keys, [](float v) { return v; });\n      channel_values_map(l.shear_keys',
     'Symmetrize Layers turns the keys of the layers inside the other way', 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '    for (const std::string &name : symmetrize_actions_apply(copy, names)) {', '    for (const std::string &name : std::vector<std::string>()) {',
     "Symmetrize Layers moves action keys to their other side's actions", 'tests/test_layer_symmetrize_keys.py'),
    ('src/anim/symmetrize_keys.cc', '        names.to[a] = around_name(*owner, a);', '        names.to[a] = a;',
     "A bone layer around the copy: an action's keys go to its mirror (Head into Head 2)", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '      channel_values_map(b.angle_keys, [](float v) { return -v; });', '      channel_values_map(b.angle_keys, [](float v) { return v; });',
     "Mirrored bones' keys turn the other way", 'tests/test_layer_symmetrize_keys.py'),
    ('src/anim/symmetrize_keys.cc', '    for (std::string &a : l.actions) {\n      a = names.rename(a, nullptr);\n    }', '    for (std::string &a : l.actions) {\n      (void)a;\n    }',
     "A bone layer inside the copy: its actions take their other side's names", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '    if (old_target) {\n      symmetrize_keep_partner(t, *old_target);\n    }', '    if (false) {\n      symmetrize_keep_partner(t, *old_target);\n    }',
     "Keep Partner's keeps the remade partner's own keys", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '      switch_remap(l, reassign);\n', '',
     "A remade switch's keys name its children by their old ids", 'tests/test_layer_symmetrize_keys.py'),
    ('src/ops/layer_ops.cc', '      animation_record(doc);\n      /* On the mainline while it works', '      /* On the mainline while it works',
     'Symmetrize Layers records edits made on the setup frame first', 'tests/test_layer_symmetrize_keys.py'),
    ('src/anim/symmetrize_keys.cc', '    return handle_change(to_setup, across(shown), -change.x, in);', '    return handle_change(to_setup, shown, -change.x, in);',
     'Handle keys go across mirrored', 'tests/test_layer_symmetrize_keys.py'),
    ('src/anim/animation.cc', '  if (const float whole = std::round(t); std::abs(t - whole) < 1e-3f) {',
     '  if (const float whole = std::round(t); false && std::abs(t - whole) < 1e-3f) {',
     'A knob at its box edge plays the Step keys on its last frame', 'tests/test_controller_step_end.py'),
    ('src/ops/rig_ops.cc', '                 if (made > 0 && (mirror_all || !sides_later.empty())) {',
     '                 if (made > 0 && mirror_all) {',
     'Bone Symmetrize makes a knob side the other side has no action for, the option off', 'tests/test_controller.py'),
    ('src/ops/rig_ops.cc', '      if (picks(name)) {', '      if (true || picks(name)) {',
     'Symmetrize reports only the picked bones actions', 'tests/test_controller.py'),
    ('src/ops/rig_ops.cc', 'bone_find_by_name(armature, other)); existing && !positions) {',
     'bone_find_by_name(armature, other)); existing && false) {',
     'Mirror Positions off leaves the other side bone where it is', 'tests/test_action_mirror.py'),
    ('src/ops/rig_ops.cc', '                   const std::string v = op_arg(C, name, "1");',
     '                   const std::string v = op_arg(C, name, "0");',
     'Bone Symmetrize mirrors positions and actions by default', 'tests/test_action_mirror.py'),
    ('src/ops/rig_ops.cc', '                 return made > 0 && changed ? OpStatus::Finished : OpStatus::Cancelled;',
     '                 return made > 0 ? OpStatus::Finished : OpStatus::Cancelled;',
     'Bone Symmetrize with nothing to do is cancelled', 'tests/test_action_mirror.py'),
    ('src/editors/select_box.cc', '  if (ctrl || (alt && alt_removes)) {', '  if ((alt && alt_removes)) {',
     'Ctrl drag takes out of a select box', 'tests/test_select_box_kind.py'),
    ('src/editors/select_box.cc', '  if (ctrl || (alt && alt_removes)) {', '  if (ctrl) {',
     'Alt still takes out in the Transform tool box over bones', 'tests/test_select_box_kind.py'),
    ('src/editors/viewport.cc', '    family_and_points_deselect(C, doc, armature);\n    bone_click_select(armature, under.front().hit, false);',
     '    family_deselect_all(doc, armature);\n    bone_click_select(armature, under.front().hit, false);',
     'A knob pressed lets go of the points picked before', 'tests/test_bone_pick_deselects_points.py'),
    ('src/editors/viewport.cc', '  if (!shift) {\n    family_and_points_deselect(C, doc, armature);\n  }',
     '  if (!shift) {\n    family_deselect_all(doc, armature);\n  }',
     'A bone clicked with the Transform tool lets go of the points picked before', 'tests/test_bone_pick_deselects_points.py'),
    ('src/editors/properties.cc', '      const bool drawing = !bone_tab_drawings(doc).empty();',
     '      const bool drawing = false;',
     'With only a drawing\'s points picked the Bone tab is Drawing', 'tests/test_bone_tab_drawing.py'),
    ('src/editors/properties.cc', '      if (!drawing) {\n        /* A controller',
     '      if (true) {\n        /* A controller',
     'No Bone Constraints tab while it is Drawing', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/vector_ops.cc', '      if (b.selected || b.select_head || b.select_tail) {\n        return {};',
     '      if (false) {\n        return {};',
     'A bone picked beside the points keeps the Bone tab', 'tests/test_bone_tab_drawing.py'),
    ('src/editors/viewport.cc', '  const ContrastColors wire = tint ? contrast_colors_of(tint->regular) : wire_colors();',
     '  const ContrastColors wire = wire_colors();',
     'A drawing\'s wires and points take its colour set', 'tests/test_bone_tab_drawing.py'),
    ('src/editors/viewport.cc', '  const ImU32 point_picked = tint ? contrast_u32(tint->select, 1.0f) : COL_POINT_SELECTED;',
     '  const ImU32 point_picked = COL_POINT_SELECTED;',
     'A drawing\'s picked points take its colour set\'s selected shade', 'tests/test_bone_tab_drawing.py'),
    ('src/io/oanim_file.cc', '  if (layer.color_set != 0) {\n    j["color_set"]',
     '  if (false) {\n    j["color_set"]',
     'A drawing\'s colour is saved', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/rig_ops.cc', '      for (Layer *l : layers_named(doc, op_arg(C, "layers"))) {\n        if (l != layer) {',
     '      for (Layer *l : layers_named(doc, "")) {\n        if (l != layer) {',
     'Layer in Collection takes the drawings named too', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/rig_ops.cc', '        if (l->type == LayerType::Vector && l->color_set != set) {',
     '        if (l->type == LayerType::Vector) {',
     'Drawing Color as it already is is cancelled', 'tests/test_bone_tab_drawing.py'),
    ('src/editors/viewport.cc', '      document_set_active_shape(*C.document, *hit_layer, picked.front(), hit_edge);\n      C.document->picked_drawing = hit_layer->id;',
     '      document_set_active_shape(*C.document, *hit_layer, picked.front(), hit_edge);',
     'A point clicked makes the Bone tab Drawing beside picked bones', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/vector_ops.cc', '  if (doc.picked_drawing != 0 && clicked != out.end()) {',
     '  if (false && clicked != out.end()) {',
     'The drawing clicked last keeps the Drawing tab', 'tests/test_bone_tab_drawing.py'),
    ('src/editors/viewport.cc', '  if (best.hit.bone) {\n    doc.picked_drawing = 0;\n  }\n',
     '',
     'A bone clicked brings the Bone tab back', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/rig_ops.cc', '                 for (Layer *l : drawings_points_picked(*C.document)) {\n                   l->color_set = from.color_set;',
     '                 for (Layer *l : std::vector<Layer *>()) {\n                   l->color_set = from.color_set;',
     'Copy Bone Color to Selected gives drawings with points picked the colour', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/rig_ops.cc', '                   if (b.selected || b.select_head || b.select_tail) {\n                     b.color_set = set;',
     '                   if (false) {\n                     b.color_set = set;',
     'Copy Color to Selected from a drawing gives the picked bones its colour', 'tests/test_bone_tab_drawing.py'),
    ('src/ops/rig_ops.cc', '                     b.custom_colors = shades;',
     '                     b.custom_colors = {shades[0], shades[1], b.custom_colors[2]};',
     'A drawing\'s colour copied to a bone carries its third shade', 'tests/test_bone_tab_drawing.py'),
    ('src/data/bones.cc', '    layer.custom_colors = {from.regular, from.select, from.active};',
     '    layer.custom_colors = {from.regular, from.select, layer.custom_colors[2]};',
     'A drawing going Custom keeps the set\'s third shade', 'tests/test_bone_tab_drawing.py'),
]

def build(root):
    return subprocess.run([CMAKE, "--build", "--preset", "release"], cwd=root, capture_output=True,
                          text=True).returncode == 0


def git(root, *args, data=None):
    r = subprocess.run(["git", *args], cwd=root, input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {root}: {r.stderr.decode(errors='replace')}")
    return r.stdout


def lane_roots(root, count):
    parent, name = os.path.split(os.path.abspath(root))
    return [os.path.join(parent, f"{name}-mut{k}") for k in range(1, count)]


def lane_ready(root, lane):
    """Bring a lane worktree to this folder's commit and uncommitted changes, made and built the first time."""
    sha = git(root, "rev-parse", "HEAD").decode().strip()
    if not os.path.isdir(lane):
        git(root, "worktree", "add", "--detach", lane, sha)
        deps = os.path.join(root, "build", "_deps")
        fetched = [f"-DFETCHCONTENT_SOURCE_DIR_{d[:-4].upper()}={os.path.join(deps, d)}"
                   for d in (os.listdir(deps) if os.path.isdir(deps) else []) if d.endswith("-src")]
        if subprocess.run([CMAKE, "--preset", "windows", *fetched], cwd=lane, capture_output=True).returncode:
            raise RuntimeError(f"configure failed in {lane}")
    else:
        git(lane, "checkout", "-f", "--detach", sha)
        git(lane, "clean", "-fdq", "--", "src", "tests", "scripts", "tools")
    diff = git(root, "diff", "--binary", "HEAD")
    if diff:
        git(lane, "apply", "--whitespace=nowarn", "-", data=diff)
    for path in git(root, "ls-files", "--others", "--exclude-standard").decode().splitlines():
        os.makedirs(os.path.dirname(os.path.join(lane, path)) or lane, exist_ok=True)
        shutil.copyfile(os.path.join(root, path), os.path.join(lane, path))
    if not build(lane):
        raise RuntimeError(f"build failed in {lane}")


class Lane:
    def __init__(self, root, number):
        self.root, self.number = root, number
        self.rebuilt = False  # its build holds a native entry's change
        self.last = None      # the file it last changed


def check(lane, i, entry, say):
    """Run one check in a lane: True when its test fails with the fix undone."""
    path, old, new, name, test = entry
    full = os.path.join(lane.root, path)
    if not os.path.exists(os.path.join(lane.root, test)):
        # Older entries name the test without its folder and prefix.
        test = os.path.join("tests", f"test_{test}.py")
    if not os.path.exists(os.path.join(lane.root, test)):
        say(f"{i} {name}: no test {test}; fix the entry")
        return False
    with open(full, encoding="utf-8") as f:
        src = f.read()
    if src.count(old) != 1:
        say(f"{i} {name}: its code is found {src.count(old)} times in {path}; fix the entry")
        return False
    backup = os.path.join(tempfile.gettempdir(), f"oanim_mutation_{os.getpid()}_{lane.number}_{os.path.basename(path)}")
    shutil.copyfile(full, backup)
    # On disk before the source changes: a power cut mid-check once left a source file zeroed with no copy to go back to.
    with open(backup, "rb+") as f:
        os.fsync(f.fileno())
    try:
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(src.replace(old, new))
        lane.last = path
        native = not path.endswith(".py")
        if not native and lane.rebuilt:
            # The build still holds the last native entry's change: a script-only entry runs on a clean one.
            shutil.copyfile(backup, full)
            if not build(lane.root):
                raise RuntimeError(f"the build in {lane.root} with every file put back failed: look before going on")
            lane.rebuilt = False
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(src.replace(old, new))
        if native:
            lane.rebuilt = True
            if not build(lane.root):
                say(f"{i} {name}: BUILD FAILED with it undone; fix the entry")
                return False
        r = subprocess.run([os.path.join(lane.root, EXE), "--background", "--python", test], cwd=lane.root,
                           capture_output=True, text=True)
        why = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "assert" in l][-1:]
        if r.returncode:
            say(f"{i} {name}: caught {why}")
            return True
        say(f"{i} {name}: NOT CAUGHT by {test}")
        return False
    finally:
        shutil.copyfile(backup, full)
        os.remove(backup)


def main():
    root = os.getcwd()
    args = sys.argv[1:]
    if "--remove-lanes" in args:
        parent, name = os.path.split(root)
        for lane in sorted(d for d in os.listdir(parent) if d.startswith(f"{name}-mut")):
            git(root, "worktree", "remove", "--force", os.path.join(parent, lane))
            print(f"removed {lane}", flush=True)
        return
    count = 1
    if "--lanes" in args:
        at = args.index("--lanes")
        count = max(1, int(args[at + 1]))
        del args[at:at + 2]
    only = set(args) - {"--prepare", "--not-here"}
    todo = [i for i in range(len(PENDING)) if not only or str(i) in only]
    # --not-here: only the lane folders, so this one stays free for editing while they run.
    here = "--not-here" not in args
    lanes = [Lane(root, 0)] if here else []
    extra = lane_roots(root, min(count, len(todo) + (not here)))
    if extra:
        print(f"getting {len(extra)} lane folder(s) ready", flush=True)
        errors = []

        def ready(lane):
            try:
                lane_ready(root, lane)
            except RuntimeError as e:
                errors.append(str(e))

        threads = [threading.Thread(target=ready, args=(lane,)) for lane in extra]
        [t.start() for t in threads]
        [t.join() for t in threads]
        if errors:
            print("\n".join(errors), flush=True)
            sys.exit(2)
        lanes += [Lane(lane, k + 1) for k, lane in enumerate(extra)]
    if "--prepare" in args:
        # Lanes made and built ahead of a run (it brings them up to date again).
        return
    lock = threading.Lock()
    tally = {"caught": 0, "missed": 0}
    broken = []

    def say(line):
        with lock:
            print(line, flush=True)

    def next_for(lane):
        with lock:
            if not todo or broken:
                return None
            # The next check on the file this lane last changed: its rebuild then compiles that one file.
            k = next((k for k, i in enumerate(todo) if PENDING[i][0] == lane.last), 0)
            return todo.pop(k)

    def work(lane):
        try:
            while (i := next_for(lane)) is not None:
                ok = check(lane, i, PENDING[i], say)
                with lock:
                    tally["caught" if ok else "missed"] += 1
            if lane.rebuilt and not build(lane.root):
                raise RuntimeError(f"the build in {lane.root} with every file put back failed: look before going on")
        except RuntimeError as e:
            with lock:
                broken.append(str(e))

    threads = [threading.Thread(target=work, args=(lane,)) for lane in lanes]
    [t.start() for t in threads]
    [t.join() for t in threads]
    if broken:
        print("\n".join(broken), flush=True)
        sys.exit(2)
    print(f"{tally['caught']} caught, {tally['missed']} not", flush=True)
    sys.exit(1 if tally["missed"] else 0)


if __name__ == "__main__":
    main()
