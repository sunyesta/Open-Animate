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
    ('src/anim/animation.cc', '          return bone ? &bone_poses_of(poses, *bone) : &poses.all;',
     '          return &poses.all;',
     'Auto-Freeze doesn\'t hold a bone at a knob\'s key whose actions hold it still', 'tests/test_auto_freeze_knob.py'),
    ('src/anim/animation.cc', '    const bool moves = knob == &bone ||',
     '    const bool moves = false ||',
     'Auto-Freeze holds a knob at its own keys', 'tests/test_auto_freeze_knob.py'),
    ('src/anim/animation.cc', '                       [&](const auto &k) { return k.frame > 0 && distance(k.value, setup) > 1e-5f; });',
     '                       [&](const auto &k) { return k.frame > 0 && distance(k.value, setup) >= 0.0f; });',
     'A bone an action holds still isn\'t moved by it for Auto-Freeze', 'tests/test_auto_freeze_knob.py'),
    ('src/ops/vector_ops.cc', '            std::all_of(rigs.begin(), rigs.end(),',
     '            std::all_of(rigs.end() - 1, rigs.end(),',
     'A collection hidden on the bone layer worked in hides a sub bone group\'s drawings in it', 'tests/test_sub_group_collections.py'),
    ('src/data/bones.cc', '  return std::all_of(panels.begin(), panels.end(),',
     '  return std::all_of(panels.end() - 1, panels.end(),',
     'A collection hidden on the bone layer worked in hides a sub bone group\'s bones in it', 'tests/test_sub_group_collections.py'),
    ('src/data/bones.cc', '  return !held;', '  return false;',
     'A bone or drawing in no collection shows with All hidden', 'tests/test_sub_group_collections.py'),
    ('src/anim/animation.cc', '      if (knob.controller_size_auto && !sides_keyed) {', '      if (knob.controller_size_auto) {',
     'Picking another action never moves a controller edge the knob was keyed to', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (!knob.controller_actions[side].empty() && own_timing[side].empty() && !across.empty()) {',
     '        if (false) {',
     'A controller side not keyed yet is as long as the opposite side is keyed', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (most <= 1e-6f) {', '        if (false) {',
     'A controller side keyed only at rest counts as not keyed', 'tests/test_controller_box_from_keys.py'),
    ('src/anim/animation.cc', '        if (custom && key.interp == Interp::Custom) {', '        if (false) {',
     "The timeline's Paste Interpolation carries a Custom curve", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc', '      b.timing = s.interp == Interp::Custom ? curve : TimingCurve{};',
     '      b.timing = TimingCurve{};',
     "The Path Timing graph's Paste Interpolation gives the copied curve", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc',
     '    for (size_t i = first; i < ch.keys.size() && (i == first || ch.keys[i].frame <= end); i++) {',
     '    for (size_t i = first; i < ch.keys.size() && i == first; i++) {',
     "The graph's Paste Interpolation pastes a span across breakdowns whole", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/anim/motion_path.cc', '      s.interval = b.interval;', '      s.interval = settings.interval;',
     "The graph's Paste Interpolation keeps each key's hold and interval", 'tests/test_timing_interpolation_clipboard.py'),
    ('src/ops/anim_ops.cc',
     '    const bool edits = edited->contains(flat->id) || flat->id == doc.active_layer || family.contains(flat->id);',
     '    const bool edits = edited->contains(flat->id) || flat->id == doc.active_layer;',
     "Only Selected shows a bone picked in a sub bone group of the bone layer worked in",
     'tests/test_timeline_sub_group_bones.py'),
    ('src/ops/operator.cc', '      stretch_sync.finish(C);', '      (void)stretch_sync;',
     "A timing edit to the active picked stretch goes to the other picked stretches", 'tests/test_stretch_sync.py'),
    ('src/ops/motion_path_ops.cc', '        !(now == o.settings && now_curve == o.curve))', '        false)',
     "A picked stretch a timing edit changed itself keeps what it did", 'tests/test_stretch_sync.py'),
    ('src/ops/motion_path_ops.cc', '      if (on_active) {', '      if (on_active && false) {',
     "Shift Alt click on the active picked stretch unpicks it", 'tests/test_stretch_sync.py'),
    ('src/editors/timeline.cc', '        f.teals.push_back({{p.target}, p.start, p.end, p == shown});',
     '        f.teals.push_back({{p.target}, p.start, p.end, false});',
     "Each picked stretch is teal, the active one lighter", 'tests/test_stretch_sync.py'),
    ('src/ops/anim_ops.cc', '          if (targets.empty() && !doc.path_show_all) {', '          if (false) {',
     "Alt click in a row whose path is hidden shows it and picks there", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/ops/anim_ops.cc', '                wm.path_also_shown = before;', '                (void)before;',
     "Shift Alt click on another path's row keeps the paths shown and their picks", 'tests/test_stretch_pick_hidden_path.py'),
    ('src/ops/motion_path_ops.cc', '  if (picks.stretches.size() < 2) {', '  if (picks.spans < 2) {',
     "One span picked on several paths: a timing edit reaches them all", 'tests/test_stretch_pick_hidden_path.py'),
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
