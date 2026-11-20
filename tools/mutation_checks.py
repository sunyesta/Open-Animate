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
    ('src/anim/animation.cc', '      if (!ch.animated() && !own.count(name)) {', '      if (false && !ch.animated() && !own.count(name)) {', 'Key Together on a reference leaves the channels it follows following', 'tests/test_key_together_reference.py'),
    ('src/data/vector.cc', '    if (size_t(c) >= closed.size() || !closed[size_t(c)] || on_shape[size_t(c)] || !curve.closed ||', '    if ((false && (size_t(c) >= closed.size() || !closed[size_t(c)])) || on_shape[size_t(c)] || !curve.closed ||', 'F and Merge fill only the bare loops they close', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '      if (shape.has_fill) {\n        has_fill = true;\n      }', '      if (shape.has_fill && only_here) {\n        has_fill = true;\n      }', 'A fill joined with others or with a hole is a fill round each loop', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '    if (has_fill) {\n      continue;\n    }\n    curve = std::move(shut);', '    curve = shut;\n    if (has_fill) {\n      continue;\n    }\n    curve = std::move(shut);', 'F on a filled loop ending on its first point changes nothing', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '      curve_fold_repeats(curve, removed);\n    }\n    {', '      (void)0;\n    }\n    {', 'Delete leaves no point twice in a row on a curve', 'tests/test_fill_loop.py'),
    ('src/data/vector.cc', '    curve_fold_repeats(curve, removed);\n    size_t w = 0;', '    size_t w = 0;', 'Dissolve leaves no point twice in a row on a curve', 'tests/test_fill_loop.py'),
    ('src/data/gradient.cc', '  if (!std::isfinite(total)) {', '  if (false && !std::isfinite(total)) {', 'A gradient whose path no number reaches shows nothing', 'tests/test_gradient_guards.py'),
    ('src/data/gradient.cc', '  const float x = std::isnan(a) ? 0.0f : std::clamp(a / L, 0.0f, 1.0f) * float(GRADIENT_LUT_SIZE);', '  const float x = std::clamp(a / L, 0.0f, 1.0f) * float(GRADIENT_LUT_SIZE);', "A gradient sampled at NaN doesn't index past its table", 'tests/test_gradient_guards.py'),
    ('src/data/layer.cc', '              if (!std::isnan(v)) {', '              if (true) {', "Squash set to NaN isn't stored", 'tests/test_gradient_guards.py'),
    ('src/anim/gradient_shown.cc', '  return std::isfinite(v) ? std::clamp(v, 0.05f, 20.0f) : g.squash;', '  return std::clamp(v, 0.05f, 20.0f);', 'Squash dragged to NaN stays as it was', 'tests/test_gradient_guards.py'),
    ('src/io/oanim_file.cc', '    g.squash = std::isfinite(g.squash) ? std::clamp(g.squash, 0.01f, 100.0f) : 1.0f;', '    g.squash = std::max(g.squash, 0.01f);', "A file's Squash out of range opens clamped", 'tests/test_gradient_guards.py'),
    ('src/anim/deform.cc', '    else if (m.type == ModifierType::Resample && !layer.is_gradient()) {', '    else if (m.type == ModifierType::Resample) {', 'Resample adds no points to a gradient', 'tests/test_gradient_guards.py'),
    ('src/anim/deform.cc', '    else if (m.type == ModifierType::Bevel && !layer.is_gradient()) {', '    else if (m.type == ModifierType::Bevel) {', 'Bevel adds no points to a gradient', 'tests/test_gradient_guards.py'),
    ('src/anim/vector_deform.cc', '  const bool cut_self = m.deform_resample_self && !g_shape_read && !layer.is_gradient();', '  const bool cut_self = m.deform_resample_self && !g_shape_read;', 'Resample Self adds no points to a gradient', 'tests/test_gradient_guards.py'),
    ('src/ops/layer_clipboard.cc', '  if (!target || target->type != LayerType::Vector || target->is_reference() || target->is_gradient()) {', '  if (!target || target->type != LayerType::Vector || target->is_reference()) {', 'Move to Layer into a gradient is refused', 'tests/test_gradient_guards.py'),
    ('src/ops/layer_clipboard.cc', '    if (layer->type != LayerType::Vector || layer->is_reference() || layer->is_gradient() || layer->id == target->id) {', '    if (layer->type != LayerType::Vector || layer->is_reference() || layer->id == target->id) {', 'Move to Layer out of a gradient moves nothing', 'tests/test_gradient_guards.py'),
    ('src/ops/gradient_ops.cc', '        drawing_remove_points(layer.drawing, extra);', '        (void)extra;', "A script's extra gradient point is put back on another frame", 'tests/test_gradient_guards.py'),
    ('src/ops/gradient_ops.cc', '        GradientFalloff falloff = s.falloff;', '        s.midpoint = std::clamp(op_arg_float(C, "midpoint", s.midpoint), 0.02f, 0.98f); GradientFalloff falloff = s.falloff;', 'Span Set with a bad falloff changes nothing', 'tests/test_gradient_guards.py'),
    ('src/ops/gradient_ops.cc', '        if ((op_has_arg(C, "stop") && (stop < 0 || stop >= n)) || (op_has_arg(C, "span") && (span < 0 || span >= n - 1))) {', '        if (op_has_arg(C, "stop") && (stop < 0 || stop >= n)) {', 'Pick with a bad span changes nothing', 'tests/test_gradient_guards.py'),
    ('src/ops/gradient_ops.cc', '    if (!std::all_of(text.begin() + 1, text.end(), [](char ch) { return std::isxdigit(static_cast<unsigned char>(ch)); }))', '    if (false && !std::all_of(text.begin() + 1, text.end(), [](char ch) { return std::isxdigit(static_cast<unsigned char>(ch)); }))', 'A hex colour is hex digits only', 'tests/test_gradient_guards.py'),
    ('src/data/vector.cc', '  if (moved && order.size() == drawing.shapes.size()) {', '  if (false && moved && order.size() == drawing.shapes.size()) {', 'A shape tree split in the stacking order stands together again', 'tests/test_shape_tree.py'),
    ('src/data/vector.cc', '  drawing_shapes_copied(drawing, size_t(old_shape_count), copied_from, true);', '  (void)copied_from;', 'Duplicate puts a copied sub shape under the copied parent', 'tests/test_shape_tree.py'),
    ('src/anim/deform.cc', '        copy.parent = shape.parent | (uint64_t(1) << 63);', '        copy.parent = shape.parent;', "The Mirror modifier's image of a shape tree is a tree of its own", 'tests/test_shape_tree.py'),
    ('src/ops/shape_tree_ops.cc', '              anchor = std::max(anchor, m);', '              (void)m;', 'A shape moved above another goes above its whole tree', 'tests/test_shape_tree.py'),
    ('src/anim/shape_tree.cc', '      int point = node.point;', '      int point = -1;', 'Apply keeps the points the outline still runs through', 'tests/test_shape_tree.py'),
    ('src/anim/shape_tree.cc', '  drawing_remove_curves(drawing, old_curve);', '  (void)0;', 'Apply takes away the curves no shape is on any more', 'tests/test_shape_tree.py'),
    ('src/ops/shape_tree_ops.cc', '        if (C.document->frame_current != 0) {', '        if (false && C.document->frame_current != 0) {', 'Apply works on Setup only', 'tests/test_shape_tree.py'),
    ('src/editors/viewport.cc', '        choice = (k + 1) % hits.size();\n        break;\n      }\n    }\n  }\n  if (!shift && !ctrl) {', '        choice = k;\n        break;\n      }\n    }\n  }\n  if (!shift && !ctrl) {', 'A click again in the same place picks the next shape there', 'tests/test_shape_tree.py'),
    ('src/editors/viewport.cc', '      if (points_all_selected(hit.layer->drawing, shape_hit_points(C, hit))) {', '      if (false && points_all_selected(hit.layer->drawing, shape_hit_points(C, hit))) {', 'A press on the shape picked grabs it under the others', 'tests/test_shape_tree.py'),
    ('src/editors/viewport.cc', '  const std::vector<int> members = C.wm->tool_settings.select_mode == SelectMode::ShapeGroup', '  const std::vector<int> members = C.wm->tool_settings.select_mode == SelectMode::Point', 'Shape Group mode picks the whole tree', 'tests/test_shape_tree.py'),
    ('src/ops/operator.cc', '      document_shape_trees_mend(*C.document);', '      (void)0;', 'A sub shape whose parent went goes back into the list', 'tests/test_shape_tree.py'),
    ('src/ops/vector_ops.cc', '      whole[size_t(s)] = true;\n      continue;', '      continue;', 'Points picked in Shape mode grow to the whole shape', 'tests/test_shape_tree.py'),
     ('src/editors/viewport.cc', '      hit_layer->drawing.active_point = hit_layer->drawing.points[size_t(picked.front())].id;', '      (void)0;', 'The point clicked is the active one', 'tests/test_shape_joins.py'),
     ('src/editors/viewport.cc', '      const ImU32 fill = pass == 2         ? IM_COL32_WHITE', '      const ImU32 fill = pass == 3         ? IM_COL32_WHITE', 'The active point is drawn white', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '      if (looked >= 0 && has(looked)) {', '      if (false && looked >= 0 && has(looked)) {', "A join takes the look of the active point's shape", 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '      merged.style.fill = drawing.shapes[size_t(fill_from)].style.fill;', '      (void)0;', 'With no active point a join takes the fill of the lowest with one', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '    if (it != into.end()) {\n      shape.parent = it->second;', '    if (false && it != into.end()) {\n      shape.parent = it->second;', 'The sub shapes of a shape joined into another go under it', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '      if (!at_selected || at_pick(m)) {', '      if (!at_selected || at_pick(m) || true) {', 'A Stroke Pen line welded to another stays its own shape through joins elsewhere', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '      if (keep != i) {\n        off.push_back(i);', '      if (false && keep != i) {\n        off.push_back(i);', 'A shape broken apart keeps its biggest part, the others copies of it', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '        if (was[j] == was[i] && (keep == parts.size() || parts[j].size() > parts[keep].size())) {', '        if ((true || was[j] == was[i]) && (keep == parts.size() || parts[j].size() > parts[keep].size())) {', 'A hole stays with the shape round it through a delete', 'tests/test_shape_joins.py'),
     ('src/io/oanim_file.cc', '  if (g_loading_version < 13 && layer.has_shapes() && !layer.is_gradient() && !layer.is_reference() &&', '  if (false && g_loading_version < 13 && layer.has_shapes() && !layer.is_gradient() && !layer.is_reference() &&', "Older files' shapes sharing points become one on open", 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '      if (first_from == last_to && chain.size() > 1) {\n        grew = false;', '      if (false && first_from == last_to && chain.size() > 1) {\n        grew = false;', 'A loop with a line running on from it still fills', 'tests/test_shape_joins.py'),
     ('src/data/vector.cc', '        shape.style.fill = shape.style.line;', '        (void)0;', "A line whose ends are joined is filled in its line's colour", 'tests/test_fill_loop.py'),
     ('src/data/fill_paint.cc', '  if (s >= 0) {\n    bool empty = false;', '  if (false && s >= 0) {\n    bool empty = false;', 'The Fill Pen grows the shape it starts on', 'tests/test_fill_paint.py'),
     ('src/data/fill_paint.cc', '  if (shape_work_in(drawing, s, area, ShapeOp::Subtract, pixel, tolerance, &empty)) {', '  if (shape_work_in(drawing, s, area, ShapeOp::Union, pixel, tolerance, &empty)) {', 'The Fill Eraser cuts from the shape it starts on', 'tests/test_fill_paint.py'),
     ('src/data/fill_paint.cc', '        grown.has_fill = true;', '        (void)0;', 'A shape the Fill Pen grows gains a fill if it had none', 'tests/test_fill_paint.py'),
     ('src/data/fill_paint.cc', '      (selected_only && !drawing_selected_shapes(drawing)[size_t(s)]))', '      (selected_only && false))', 'Selected Only erases only from a selected shape', 'tests/test_fill_paint.py'),
     ('src/data/vector.cc', '        drawing.active_point = drawing.points[size_t(keep)].id;', '        (void)keep;', 'The active point merged: the point they became is the active one', 'tests/test_shape_joins.py'),
     ('src/io/oanim_file.cc', '    out["active_point"] = drawing.active_point;', '    (void)out;', 'The active point is saved with the drawing', 'tests/test_shape_joins.py'),
     ('src/data/fill_paint.cc', '    if (shape.has_outline && outline_distance(drawing, shape, start) <= std::max(reach, shape.style.line_width * 0.5f)) {', '    if (false && shape.has_outline && outline_distance(drawing, shape, start) <= std::max(reach, shape.style.line_width * 0.5f)) {', 'The Fill Pen started on a line grows its shape', 'tests/test_fill_paint.py'),
     ('src/editors/viewport.cc', '      drawing.active_point = drawing.points[size_t(grab.points.front())].id;', '      (void)0;', 'A point dragged becomes the active one', 'tests/test_shape_joins.py'),
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
