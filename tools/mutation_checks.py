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
    ('src/anim/motion_path.cc', 'return !doc.action.empty() || !bone_fix_line_of(*layer, action.first, b, which);',
     'return true;', 'Own Motion: a fix line on the knob leaves its path to its keys', 'tests/test_motion_path_fix_line.py'),
    ('src/anim/motion_path.cc', '  if (down.empty()) {', '  if (true) {',
     'A control point on a knob held at its box edge: slopes measured off the edge', 'tests/test_motion_path_control_edge.py'),
    ('src/anim/motion_path.cc', 'if (!knob || !bone_is_controller(*knob) || !knob->controller_contain_knob) {', 'if (true) {',
     'A control point dragged past a contained knob box edge stops there', 'tests/test_motion_path_control_edge.py'),
    ('src/anim/motion_path.cc', 'edge = dot(got, rate) / dot(rate, rate);', 'edge = edge;',
     'The box edge found from the rate measured inside, not the rough slopes', 'tests/test_motion_path_control_edge.py'),
    ('src/anim/motion_path.cc', '!bone_fix_line_of(owner, by, *holder, &holder->position_keys))', 'true)',
     'Kept action offsets: a fix line in a knob keys moves nothing', 'tests/test_motion_path_knob_fix_offsets.py'),
    ('src/anim/motion_path.cc', '      if (!fix || fix->follows.empty()) {', '      if (true) {',
     'Kept action offsets: a fix played by a knob its keys alone move', 'tests/test_motion_path_knob_fix_offsets.py'),
    ('src/anim/motion_path.cc', '    if ((i >= 2 && !fits(i - 2)) || (i + 1 < n && !fits(i + 1))) {', '    if (false) {',
     'Path line: the keys curve shapes it only where the dots go as the keys do', 'tests/test_motion_path_line_actions.py'),
    ('src/anim/animation.cc', '        if (channel_on_path_at(ch, frame) && !(ch.from_action_bones == float2{0.0f, 0.0f})) {',
     '        if (false) {', 'On Path: what the actions add left out between the keys', 'tests/test_motion_path_on_path.py'),
    ('src/anim/animation.cc', '            b.position = bone_position_from_transform(b, b.transform);', '            ;',
     'On Path: the bone position follows what is left out', 'tests/test_motion_path_on_path.py'),
    ('src/anim/channel.cc', '    const float2 p1 = p0 + r_out, p2 = p3 + r_in;', '    const float2 p1 = r_out, p2 = r_in;',
     'Path fit: the handles solved as offsets from their ends', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '    if (channel_on_path_at(ch, frame)) {\n      added.transform = float2{0.0f, 0.0f};',
     '    if (false) {\n      added.transform = float2{0.0f, 0.0f};', 'On Path: Own Motion dots add nothing kept between the keys',
     'tests/test_motion_path_on_path.py'),
    ('src/ops/motion_path_ops.cc', '      path_edit_prepare(doc, targets);\n      const MotionPathTarget t = targets.front();',
     '      const MotionPathTarget t = targets.front();', 'A dot moved on a path without keys gives it keys On Path first',
     'tests/test_motion_path_on_path.py'),
    ('src/anim/channel.cc', '    if (on_path && frame > keys.back().frame) {', '    if (false) {',
     'On Path: past the last key the actions add again', 'tests/test_motion_path_on_path.py'),
    ('src/anim/channel.cc', '  return ch.on_path && ch.keys.size() >= 2;', '  return ch.on_path;',
     'On Path dropped when its keys are all deleted and it is keyed again', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '  if (motion_path_edit_keys_at(doc, target, frame)) {', '  if (false) {',
     'A path with no keys: the handles its keys will have on what moves it diamonds', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '  return on_key && std::any_of(dots.begin(), dots.end(),', '  return false && std::any_of(dots.begin(), dots.end(),',
     'A diamond on a path with no keys, picked as a dot, shows its handles', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '  return motion_path_is_key(doc, target, 0) || motion_path_edit_keys_at(doc, target, 0);',
     '  return motion_path_is_key(doc, target, 0);',
     'A path with no keys shows the setup diamond, its out handle', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '  Layer *owner = t.bone ? layer_find(doc, t.layer) : nullptr;',
     '  Layer *owner = t.bone && t.head ? layer_find(doc, t.layer) : nullptr;',
     'On Path and its handles on a tip path too, the bone not turning', 'tests/test_motion_path_on_path.py'),
    ('src/anim/motion_path.cc', '  if (ch.keys.size() >= 2 && (ch.key_at(frame) || frame <= ch.keys.front().frame || frame >= ch.keys.back().frame)) {',
     '  if (ch.keys.size() >= 2) {',
     'A diamond from what moves it between the bone\'s own keys shows the handles its key will have', 'tests/test_motion_path_on_path.py'),
    ('src/anim/channel.cc', '  if (last.frame != was.last && last.path_handles != PathHandles::Auto) {', '  if (false) {',
     'A key left last by a delete: its out handle back in line', 'tests/test_motion_path_key_ends.py'),
    ('src/anim/channel.cc', '      k.path_handles = PathHandles::Auto;', '      k.path_handles = k.path_handles;',
     'A key left alone by a delete: its handles back to Auto', 'tests/test_motion_path_key_ends.py'),
    ('src/editors/viewport.cc', '  return timing ? !on_key && !alt : on_key || alt;', '  return on_key || alt;',
     'Edit Timing takes only dots, Edit Path keys', 'tests/test_motion_path_edit_split.py'),
    ('src/ops/motion_path_ops.cc', '  return path_edit_poll(C) && C.wm->tool_settings.path_brush == PathBrush::Edit;',
     '  return path_edit_poll(C);', 'G R S, V and X are Edit Path\'s only', 'tests/test_motion_path_edit_split.py'),
    ('src/ops/motion_path_ops.cc', '      if (op_arg_bool(C, "go") && op_has_arg(C, "pick") && !op_arg_bool(C, "pick")) {',
     '      if (false) {', 'Edit Path\'s double click on a dot only goes to its frame', 'tests/test_motion_path_edit_split.py'),
    ('src/anim/motion_path.cc', '  if (slide.proportional && dots.size() > 1) {', '  if (false) {',
     'G on several dots with O: each picked dot still lands where it is taken', 'tests/test_motion_path_dots_grab.py'),
    ('src/anim/motion_path.cc', '      if (f <= 0 || std::binary_search(p.keys.begin(), p.keys.end(), f) || at.x < lo.x || at.x > hi.x ||',
     '      if (f <= 0 || at.x < lo.x || at.x > hi.x ||', 'Edit Timing\'s box picks no key', 'tests/test_motion_path_dots_grab.py'),
    ('src/ops/motion_path_ops.cc', '        if (brush == PathBrush::Edit && ts.path_brush != PathBrush::Edit && !C.wm->path_dots.empty()) {',
     '        if (false) {', 'Edit Path lets go of the dots picked', 'tests/test_motion_path_edit_split.py'),
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
