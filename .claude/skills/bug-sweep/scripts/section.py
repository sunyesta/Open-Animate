"""Run one `# --- ` section of a test on its own: its header, then section OA_SEC (1-based) of OA_TEST."""
import os, sys
src = open(os.environ["OA_TEST"], encoding="utf-8").read()
parts = src.split("\n# --- ")
idx = int(os.environ["OA_SEC"])
code = parts[0] + "\n# --- " + parts[idx]
code = code.split('\nprint("test_')[0]
exec(compile(code, "section%d" % idx, "exec"), {"__name__": "__main__", "__file__": os.path.abspath(os.environ["OA_TEST"])})
print("SECTION", idx, "PASS")
