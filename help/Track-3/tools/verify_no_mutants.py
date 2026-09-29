"""After ANY interrupted mutation run: check that every spec's ORIGINAL line is back.

WHY. A run stopped mid-mutant leaves the mutant in the source. Grepping for `if False:` is not
enough (Phase C: a UI mutant rewriting a template string went unnoticed into a pushed commit).
For each mutant in every spec, this reports specs whose original text is absent from the target:
either the code was rewritten on purpose since (read it and confirm), or a mutant is still there.

    python help/Track-3/tools/verify_no_mutants.py [spec_dir ...]   (default: specs-phase-c)
"""
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
dirs = [pathlib.Path(d) for d in sys.argv[1:]] or [pathlib.Path(__file__).parent / "specs-phase-c"]
absent = 0
for d in dirs:
    for sp in sorted(d.glob("*.json")):
        s = json.loads(sp.read_text(encoding="utf-8"))
        target = REPO / (s.get("root") or "backend") / s["target"]
        text = target.read_text(encoding="utf-8").replace("\r\n", "\n") if target.exists() else ""
        for name, orig, mut in s["mutants"]:
            if orig.replace("\r\n", "\n") not in text:
                absent += 1
                hint = "MUTANT STILL THERE" if mut and mut in text and mut not in orig else "rewritten since? read it"
                print(f"{sp.name:26} {name:28} original absent — {hint}")
print(f"done; {absent} original(s) absent")
