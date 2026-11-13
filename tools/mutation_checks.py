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
    ('src/anim/animation.cc', 'if (frame != 0 && !ch.animated() && ch.action_slope.known && ch.action_played.on) {',
     'if (frame != 0 && !ch.animated() && ch.action_slope.known && ch.action_bone_live) {',
     'Auto Keying off: an edit to a value an action holds still lands where it was put', 'tests/test_autokey_off_held.py'),
    ('src/ops/operator.cc', 'std::isfinite(v) && std::abs(v) <= 1e7f) ? v : fallback;', 'std::isfinite(v)) ? v : fallback;',
     'Numbers past ten million are refused as nan is', 'tests/test_sweep_key_guards.py'),
    ('src/editors/viewport.cc', 'std::clamp(op_arg_float(C, "scale", 1.0f), -1e3f, 1e3f)', 'op_arg_float(C, "scale", 1.0f)',
     'Bones scale at most a thousand times', 'tests/test_sweep_key_guards.py'),
    ('src/anim/animation.cc', 'if (at < 0 || (at == 0 && knob)) {', 'if (at < 0) {',
     'A knob key pasted on frame 0 leaves its controller at rest', 'tests/test_sweep_key_guards.py'),
    ('src/anim/animation.cc', 'if (!channel.animated() && at != 0 && value) {', 'if (false) {',
     'Keys pasted onto an unkeyed channel key its setup first', 'tests/test_sweep_key_guards.py'),
    ('src/ops/anim_ops.cc', 'filter.picked_bones_only = C.document->timeline_only_selected && !C.document->timeline_lock;', 'filter.picked_bones_only = false;',
     'Select All with Only Selected picks only the keys the rows show', 'tests/test_sweep_key_guards.py'),
    ('src/ops/anim_ops.cc', 'std::clamp(op_arg_int(C, "frames", 0), -KEY_FRAME_LAST, KEY_FRAME_LAST)', 'op_arg_int(C, "frames", 0)',
     'Move Keys by INT_MAX does not wrap round', 'tests/test_sweep_key_guards.py'),
    ('src/anim/animation.cc', 'const int drop = keys_drop(layers, lifted, false);', 'const int drop = 0;',
     'Key moves stop at the last frame', 'tests/test_sweep_key_guards.py'),
    ('src/anim/animation.cc', 'const int offset = std::clamp(offset_asked, -KEY_FRAME_LAST, KEY_FRAME_LAST);', 'const int offset = offset_asked;',
     'Duplicate Keys by INT_MAX does not wrap round', 'tests/test_sweep_key_guards.py'),
    ('src/ops/anim_ops.cc', 'if (factor == 1.0f) {', 'if (false) {',
     'Scale Keys by 1 is CANCELLED with no undo step', 'tests/test_sweep_key_guards.py'),
    ('src/ops/file_ops.cc', '    width = stem.size() - digits_at;', '    width = std::max<size_t>(width, stem.size() - digits_at);',
     'Save Incremental keeps the digit count', 'tests/test_sweep_key_guards.py'),
    ('src/anim/switch.cc', 'original = original && original->is_switch() ? original : nullptr;', 'original = nullptr;',
     "A switch reference shows its original's picks", 'tests/test_sweep_key_guards.py'),
    ('src/anim/motion_path.cc', '    if (at >= most) {\n      least = most;', '    if (false) {\n      least = most;',
     "A dot slid to itself at an overshoot's turn stays", 'tests/test_sweep_path_guards.py'),
    ('src/anim/motion_path.cc', '  const bool shaped = interp_timed_by_mode(b.interp);\n',
     '  bool shaped = interp_timed_by_mode(b.interp);\n  if constexpr (std::is_same_v<T, float2>) {\n'
     '    shaped = shaped && b.path_controls.empty();\n  }\n',
     'A Bounce stretch through a control point is timed by its mode', 'tests/test_sweep_path_guards.py'),
    ('src/anim/motion_path.cc', 'order_progress(u, k0, 0.02f / float(n), 0, -1, ch.keys[i - 1].interval);',
     'order_progress(u, k0, 0.02f / float(n), 0, -1, 1);',
     "Alt S keeps a step's frames together on 2s", 'tests/test_sweep_path_guards.py'),
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
