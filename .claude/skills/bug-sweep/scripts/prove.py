"""Proves PENDING entries by index: undo the fix, build, run its test (must fail), put the fix back. Rebuilds at the end.
Run from the checkout's root:  python .claude/skills/bug-sweep/scripts/prove.py 56 57 58
Never stop it mid-run: the undone fix would stay in the source."""
import importlib.util, os, subprocess, sys
ROOT = os.getcwd().replace("\\", "/")
CMAKE = r"C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
EXE = ROOT + "/build/bin/RelWithDebInfo/OpenAnimate.exe"
spec = importlib.util.spec_from_file_location("m", ROOT + "/tools/mutation_checks.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def build():
    # The linker sometimes fails on a locked exe or PDB (LNK1168, LNK1318): tried again, not counted as the change failing.
    for _ in range(4):
        r = subprocess.run([CMAKE, "--build", "--preset", "release", "-j", "2"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return True
        if "LNK1168" not in r.stdout and "LNK1318" not in r.stdout:
            print(next((l for l in r.stdout.splitlines() if " error " in l), "build failed"), flush=True)
            return False
    return False
for idx in map(int, sys.argv[1:]):
    path, find, put, what, test = m.PENDING[idx]
    test = test if test.startswith("tests/") else "tests/test_%s.py" % test
    data = open(ROOT + "/" + path, "rb").read()
    text = data.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    f, r = find.replace("\n", nl), put.replace("\n", nl)
    if text.count(f) != 1:
        print("ANCHOR", text.count(f), idx, what, flush=True); continue
    open(ROOT + "/" + path, "wb").write(text.replace(f, r).encode("utf-8"))
    try:
        if not build():
            print("BUILD FAILED", idx, what, flush=True); continue
        res = subprocess.run([EXE, "--background", "--python", test], cwd=ROOT, capture_output=True, text=True, timeout=600)
        print(("CAUGHT " if res.returncode else "MISSED "), idx, what, flush=True)
    finally:
        open(ROOT + "/" + path, "wb").write(data)
print("rebuild", build(), flush=True)
