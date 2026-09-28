"""R46 mutation runner (saved from the 2026-09-28 session; see ../SESSION-HANDOFF.md §6).

WINDOWS LESSONS BAKED IN — each one produced a false result before it was fixed:
  * patterns are written with LF and adapted to CRLF files (else every mutant is "BAD(0)");
  * changed lines are counted with difflib (`git diff --no-index` stdin reported whole files);
  * a shell command must call Git Bash BY FULL PATH (C:\Program Files\Git\usr\bin\bash.exe):
    `bash` from a Python subprocess resolves to WSL's bash (CreateProcess searches System32
    first), the script never runs, and a non-zero exit reads as a KILL;
  * for command specs set "require_pytest_exit": the script must print PYTEST_EXIT=<code>,
    so only pytest's own exit counts (a failed migration step reads MIGRATION-FAILED);
  * a mutated MIGRATION leaves the database mutated: give such specs an "after" command
    that re-applies the real migration (see reset_ledger.sh);
  * never run two DB-backed test processes at once: each test's tenant cleanup deletes the
    other's rows and every result becomes noise.

R46 mutation runner. Usage: python mutate.py spec.json
spec = {"root": "backend" | "frontend", "target": "<path rel to root>",
        "tests": [...] (pytest) | "cmd": [...] (any command, e.g. vitest),
        "env_test": true, "mutants": [[name, old, new], ...]}
Each mutant: exact single-occurrence replace (patterns written with LF, adapted to CRLF files),
prove the file changed and count changed lines (difflib), run the tests, expect failure,
restore in finally."""
import difflib, hashlib, json, os, pathlib, re, subprocess, sys

CRLF, LF = "\r\n", "\n"
spec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
ROOT = pathlib.Path(r"C:\Users\Aksha\OneDrive\Desktop\PWC\SDLC") / spec.get("root", "backend")
target = ROOT / spec["target"]
env = dict(os.environ)
if spec.get("env_test"):
    from dotenv import dotenv_values
    env.update({k: v for k, v in dotenv_values(ROOT / ".env.test").items() if v is not None})
cmd = spec.get("cmd") or [sys.executable, "-m", "pytest", *spec["tests"], "-q", "-p", "no:cacheprovider",
                          *spec.get("pytest_args", [])]
orig = target.read_bytes()
text = orig.decode()
crlf = CRLF in text
ansi = re.compile(r"\x1b\[[0-9;]*m")
rows = []
try:
    for name, old, new in spec["mutants"]:
        if crlf:
            old, new = old.replace(LF, CRLF), new.replace(LF, CRLF)
        if text.count(old) != 1:
            rows.append((name, f"BAD({text.count(old)})", "")); continue
        mutated = text.replace(old, new)
        target.write_bytes(mutated.encode())
        changed = hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(orig).digest()
        d = [l for l in difflib.unified_diff(text.splitlines(), mutated.splitlines(), lineterm="", n=0)
             if not l.startswith(("---", "+++", "@@"))]
        numstat = f"+{sum(l.startswith('+') for l in d)}/-{sum(l.startswith('-') for l in d)}"
        r = subprocess.run(cmd, capture_output=True, cwd=ROOT, env=env)
        out = [ansi.sub("", l) for l in r.stdout.decode("utf-8", "replace").splitlines()]
        failed = [l.strip() for l in out if l.startswith("FAILED") or l.strip().startswith(("Ã—", "FAIL "))]
        rc = r.returncode
        m = [l for l in out if l.startswith("PYTEST_EXIT=")]
        if m: rc = int(m[-1].split("=")[1])
        elif spec.get("require_pytest_exit"): rc = -999
        verdict = ("MIGRATION-FAILED" if rc == -999 else "KILLED" if rc != 0 else "SURVIVED") if changed else "NO-CHANGE"
        tail = next((l for l in reversed(out) if l.strip()), "")
        rows.append((name, verdict, f"{numstat} " + (failed[0] if failed else tail)))
        target.write_bytes(orig)
finally:
    target.write_bytes(orig)
    if spec.get("after"):
        # e.g. re-apply the UNMUTATED migration, so no mutant outlives the run in the database
        a = subprocess.run(spec["after"], capture_output=True, cwd=ROOT, env=env)
        print("after:", a.returncode, a.stdout.decode('utf-8','replace').strip().splitlines()[-1:] )
for n, v, d in rows:
    print(f"{v:9} {n:28} {d[:170]}")
print("restored:", target.read_bytes() == orig, "| killed", sum(v == "KILLED" for _, v, _ in rows), "of", len(rows))
