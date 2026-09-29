"""Phase E independent review (build-log Entry 11) — one guarding test per fixed finding that
needs no database. The DB-backed fixes (#5, #8, #11, #12) are in test_record_tool.py and
test_approval_and_routes.py.

  #1  a confirmed contract names ONE file the inventory shows AT that place (no wildcard, folder,
      multi-file elision, or unrelated line in the same file)
  #2  a one-letter "open question" does not keep the assessment's questions open
  #3  a version the lifecycle table does not know is noted as not checked; non-LTS Java/Node are EOL
  #4  a database named by its engine, not only by the layer's name, needs the data migration
  #6  the scanner never follows a symlink out of the checkout
  #7  C# method routes join the controller prefix; a bare JAX-RS @GET does not borrow its
      neighbour's @Path; open(os.path.join(...), "w") is a write; prose is not SQL
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from agents_orchestrator.design_modernization_agent.analysis import checks
from agents_orchestrator.design_modernization_agent.analysis.interfaces import capture_interfaces, lines_by_file

AS_OF = date(2026, 9, 29)
FILES = {"src/Api.java", "src/Other.java", "src/sql/a.sql"}
DIRS = {"src", "src/sql"}
CAPTURED = {"src/Api.java": [40], "src/Other.java": [5]}


def _contract(location, status="confirmed", brief_item=None):
    return {"id": "CT-09", "name": "invented", "legacy_location": location, "status": status, "brief_item": brief_item}


def _problems(location, **kw):
    return checks.check_locations([_contract(location, **kw)], [], FILES, DIRS, CAPTURED).problems


# ── #1 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("location", ["*", "...", "src", "src/*.java"])
def test_a_confirmed_contract_cannot_hide_behind_a_wildcard_or_a_folder(location):
    [p] = _problems(location)
    assert "names 2 files" in p or "names 3 files" in p, p


def test_even_a_brief_named_contract_names_one_file():
    assert "files" in _problems("src", brief_item="the API")[0]
    assert _problems("src/Api.java", brief_item="the API") == []


@pytest.mark.parametrize("location,ok", [
    ("src/Api.java:42", True),       # within the slack of the entry at line 40
    ("src/Api.java", True),          # no line cited: the file is shown
    ("src/Api.java:120", False),     # an unrelated line in the same file
    ("src/sql/a.sql:1", False),      # a file the inventory does not show
])
def test_confirmed_means_the_inventory_shows_it_there(location, ok):
    assert (_problems(location) == []) is ok


def test_a_proposed_contract_may_point_at_a_folder():
    assert _problems("src", status="proposed") == []


def test_lines_by_file_reads_every_entry():
    inv = {"items": [{"location": "a/b.py:3"}, {"location": "a/b.py:9"}, {"location": "c.jsp:1"}]}
    assert lines_by_file(inv) == {"a/b.py": [3, 9], "c.jsp": [1]}


# ── #2 ───────────────────────────────────────────────────────────────────────

def test_a_one_letter_open_question_keeps_nothing_open():
    q = "Which downstream systems read the nightly bank file?"
    assert checks.check_questions([q], [], ["a"])
    assert checks.check_questions([q], [], ["?"])
    assert checks.check_questions([q], [], [q + " (asked the ops lead, waiting)"]) == []


# ── #3 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("target,needle", [
    ("Java 23", "Java 23 is past its end of support"),
    ("Node 17", "Node.js 17 is past its end of support"),
])
def test_non_lts_releases_are_end_of_life(target, needle):
    assert needle in checks.check_versions([("Runtime", target)], AS_OF).problems[0]


def test_an_unknown_version_is_said_not_passed():
    out = checks.check_versions([("Runtime", "Java 99")], AS_OF)
    assert out.problems == []
    assert out.notes == ["Runtime: Java 99 is not in the lifecycle table, so its end of support was not checked "
                         "— confirm it is a supported release."]


# ── #4 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("layer", [
    {"layer": "Persistence", "today": "Oracle 12c", "target": "PostgreSQL 16"},
    {"layer": "Storage", "today": "files on NAS", "target": "Blob storage"},
    {"layer": "Back end", "today": "Tomcat + MySQL 5.6", "target": "App Service + MySQL 8.0"},
])
def test_a_changing_database_is_recognised_by_its_engine(layer):
    assert checks.check_data_migration([layer], None)


def test_an_unchanged_or_non_database_layer_needs_no_plan():
    assert checks.check_data_migration([{"layer": "Hosting", "today": "VMs", "target": "App Service"}], None) == []
    assert checks.check_data_migration([{"layer": "Persistence", "today": "Oracle 19c", "target": "Oracle 19c"}], None) == []


# ── #6, #7: the scanner ──────────────────────────────────────────────────────

def _scan(tmp_path: Path, files: dict[str, str]) -> list[tuple]:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return [(i["kind"], i["direction"], i["name"], i["location"]) for i in capture_interfaces(tmp_path)["items"]]


def test_a_symlink_out_of_the_checkout_is_never_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Secret.java").write_text('@RestController\n@RequestMapping("/x")\nclass S {\n  @GetMapping("/leak")\n}\n')
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        os.symlink(outside / "Secret.java", repo / "Link.java")
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot create symlinks (Windows without Developer Mode)")
    assert capture_interfaces(repo)["items"] == []


def test_a_file_the_os_reports_as_a_symlink_is_skipped(tmp_path, monkeypatch):
    """The same guard where symlinks cannot be created (Windows without Developer Mode): the
    scanner asks the OS and skips what it says is a link."""
    _scan(tmp_path, {"Link.java": '@RequestMapping("/x")\nclass S {\n  @GetMapping("/leak")\n}\n',
                     "Real.java": '@RequestMapping("/y")\nclass R {\n  @GetMapping("/ok")\n}\n'})
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "Link.java" or real_is_symlink(self))
    assert [i["name"] for i in capture_interfaces(tmp_path)["items"]] == ["GET /y/ok"]


def test_csharp_method_routes_join_the_controller_prefix(tmp_path):
    items = _scan(tmp_path, {"ClaimsController.cs": (
        '[Route("api/claims")]\npublic class ClaimsController {\n'
        '    [HttpGet("{id}")]\n    public X Get() {}\n'
        '    [Route("search")]\n    [HttpGet]\n    public X Search() {}\n}\n')})
    names = [n for k, d, n, _ in items if k == "http"]
    assert names == ["GET api/claims/{id}", "GET api/claims/search"]


def test_a_bare_jaxrs_verb_does_not_borrow_the_next_methods_path(tmp_path):
    items = _scan(tmp_path, {"R.java": (
        '@Path("/claims")\npublic class R {\n'
        '    @GET\n    public List list() { return all(); }\n'
        '    @GET\n    @Path("/secret")\n    public X secret() {}\n}\n')})
    assert [n for k, _d, n, _ in items if k == "http"] == ["GET /claims", "GET /claims/secret"]


def test_python_open_with_a_joined_path_is_a_write(tmp_path):
    items = _scan(tmp_path, {"r.py": 'with open(os.path.join(OUT, "bank.csv"), "w") as f:\n    pass\n'
                                     'x = open(p, mode="a")\n'})
    assert ("file", "writes", "bank.csv", "r.py:1") in items
    assert ("file", "writes", "p", "r.py:3") in items


def test_prose_is_not_sql_but_sql_still_is(tmp_path):
    items = _scan(tmp_path, {"S.java": (
        'class S {\n  void a() { log("Failed to update from server cache"); log("Copied from backups into archives"); }\n'
        '  void b() { q("UPDATE claims SET paid = 1 WHERE id = ?"); q("INSERT INTO audit VALUES (1)"); }\n}\n')})
    assert [(n, loc) for k, _d, n, loc in items if k == "db"] == [("audit", "S.java:3"), ("claims", "S.java:3")]
