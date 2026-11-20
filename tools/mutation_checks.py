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
    ('src/anim/dynamics.cc', '  const int upto = std::min(frame, std::max(start, doc.frame_end));', '  const int upto = frame;', 'Dynamics stop at the end frame', 'tests/test_dynamics_end_frame.py'),
    ('src/data/grid.cc', '      cp.handles_set = true;', '      cp.handles_set = false;', "The Shape tool's grid lines have handles of no length", 'tests/test_grid.py'),
    ('src/data/vector.cc', '    if (w > 0.0f) {', '    if (false && w > 0.0f) {', "A grid node's short handle reads as reaching a third along", 'tests/test_mesh_points.py'),
    ('src/anim/animation.cc', '      keyable[i] = inside.contains(flat[i]);', '      keyable[i] = true;', "In an action, layers outside its bone layer aren't auto-keyed", 'tests/test_action_outside_keys.py'),
    ('src/ops/anim_ops.cc', '      return l == &doc.camera || l == &doc.simulation || !layer_keys_editable(doc, l->id);', '      return l == nullptr;', "In an action, the timeline leaves out layers outside its bone layer", 'tests/test_action_outside_keys.py'),
    ('src/ops/anim_ops.cc', '!layer->locked && layer_keys_editable(doc, layer->id)) {', '!layer->locked) {', "In an action, I and Alt I key nothing outside its bone layer", 'tests/test_action_outside_keys.py'),
    ('src/anim/reference.cc', '          delta = p.pos - again.points[i].pos;', '          delta = p.pos - rs.built_pos[i];', "A reference's points moved with its original's move once", 'tests/test_reference_move_once.py'),
    ('src/anim/reference.cc', '          if (const VectorDrawing &again = rebuilt(); same_curves(again.curves, d.curves)) {', '          if (const VectorDrawing &again = rebuilt(); false && same_curves(again.curves, d.curves)) {', "A reference's handles turned with its original's turn once", 'tests/test_reference_move_once.py'),
    ('src/editors/viewport.cc', "    return kind != 'E' && std::any_of(layers.begin(), layers.end(),", "    return false && kind != 'E' && std::any_of(layers.begin(), layers.end(),", "A locked reference moved with its original isn't reported locked", 'tests/test_reference_move_once.py'),
    ('src/ops/operator.cc', '    if (guard && !gradients.items.empty()) {', '    if (false && guard && !gradients.items.empty()) {', "An operator can't add or take away a gradient's points", 'tests/test_gradient_layer.py'),
    ('src/ops/undo.cc', '    gradients_check(doc, was);', '    (void)was;', "A script's change to a gradient's points is put back at the next undo step", 'tests/test_gradient_layer.py'),
    ('src/ops/gradient_ops.cc', '      layer.gradient.stops = stops_merged(had->gradient.stops, layer.gradient.stops);', '      layer.gradient.stops = had->gradient.stops;', "Putting a gradient's points back keeps the rest of the step's edit", 'tests/test_gradient_layer.py'),
    ('src/data/gradient.cc', '  piece(f.path.back(), end_dir, inf, f.total, 1.0f);', '  (void)end_dir;', "A gradient's path carries on past its end", 'tests/test_gradient_layer.py'),
    ('src/data/gradient.cc', '  const float q = (2.0f * m - 1.0f) / (1.0f - m);', '  const float q = 0.0f * m;', "A span's tick is where its colours meet half way", 'tests/test_gradient_layer.py'),
    ('src/data/gradient.cc', 'slopes[k][i] = a * b <= 0.0f ? 0.0f :', 'slopes[k][i] = true ? 0.0f :', 'A Smooth gradient has no kink at a stop', 'tests/test_gradient_layer.py'),
    ('src/data/vector.cc', '      if (last > 0 && curve.points[size_t(last)].point == curve.points[0].point && (curve.closed || kept_n >= 4)) {', '      if (last > 0 && curve.points[size_t(last)].point == curve.points[0].point && (curve.closed || false && kept_n >= 4)) {', "Merging an open curve's two ends closes it", 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '  if (!closed_before && !closed_after) {', '  if (!closed_before) {', 'A line along a curve whose ends merged goes round with it', 'tests/test_fill_loop.py'),
    ('src/ops/vector_ops.cc', '                        filled += drawing_fill_loops(layer->drawing, style);', '                        (void)style;', 'F on a whole loop with no fill makes a shape of it', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '    if (!curve.closed && curve.points.size() >= 4 && curve.points.back().point == curve.points.front().point) {', '    if (false && !curve.closed && curve.points.size() >= 4 && curve.points.back().point == curve.points.front().point) {', 'F closes a loop whose ends were merged before merging closed it', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '      drawing.shapes[size_t(round)].has_fill = true;', '      round = -1;', 'F fills the line round a loop instead of adding a shape', 'tests/test_fill_loop.py'),
    ('src/ops/vector_ops.cc', '                        drawing_fill_bare_loops(layer->drawing, style);', '                        (void)style;', 'F closing a curve with nothing on it fills it', 'tests/test_fill_loop.py'),
    ('src/ops/vector_ops.cc', '                        drawing_fill_bare_loops(layer->drawing, C.wm ? C.wm->tool_settings.style : Style());', '                        (void)0;', "Merging a curve's ends into a loop with nothing on it fills it", 'tests/test_fill_loop.py'),
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
