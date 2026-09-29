"""What the assessment cannot know from the code (`analysis/unknowns.py`, research §6.2 item 2).

The ClaimTrack case the Development Plan names: a batch module that declares Java 7 but depends
on a library that needs Java 8 — so production cannot be running Java 7, and that is a question,
said specifically. Plus the scheduler question for a batch module, the configuration question
(always asked), an undeclared runtime, and an unreadable manifest. Pure: no database.
"""
from __future__ import annotations

from pathlib import Path

from agents_orchestrator.discovery_agent.analysis.inventory import scan_inventory
from agents_orchestrator.discovery_agent.analysis.manifests import parse_module_manifest
from agents_orchestrator.discovery_agent.analysis.unknowns import _java_needed, not_assessable
from agents_orchestrator.discovery_agent.analysis.manifests import Dependency

BATCH_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.claimtrack</groupId>
  <artifactId>claims-batch</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.source>1.7</maven.compiler.source>
  </properties>
  <dependencies>
    <dependency><groupId>com.google.guava</groupId><artifactId>guava</artifactId><version>23.0</version></dependency>
    <dependency><groupId>commons-io</groupId><artifactId>commons-io</artifactId><version>2.4</version></dependency>
  </dependencies>
</project>
"""
API_POM = BATCH_POM.replace("claims-batch", "claims-api").replace("1.7", "1.8")
NODE = '{"name": "letters", "version": "1.0.0", "dependencies": {"express": "^4.17.1"}}'


def _repo(root: Path, *, env_files: bool = True) -> Path:
    (root / "batch").mkdir(parents=True)
    (root / "batch" / "pom.xml").write_text(BATCH_POM, encoding="utf-8")
    (root / "batch" / "Job.java").write_text("class Job {}\n", encoding="utf-8")
    (root / "api").mkdir()
    (root / "api" / "pom.xml").write_text(API_POM, encoding="utf-8")
    (root / "api" / "Api.java").write_text("class Api {}\n", encoding="utf-8")
    (root / "letters").mkdir()
    (root / "letters" / "package.json").write_text(NODE, encoding="utf-8")
    (root / "letters" / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    if env_files:
        (root / "api" / "application-prod.properties").write_text("db=x\n", encoding="utf-8")
    return root


def _rows(root: Path):
    inventory = scan_inventory(root)
    manifests = {m.name: parse_module_manifest(root, m) for m in inventory.modules}
    rows = []
    for i, m in enumerate(sorted(inventory.modules, key=lambda m: m.path), start=1):
        rt = manifests[m.name].runtime
        rows.append({"id": f"M-{i:02d}", "name": m.name, "path": m.path,
                     "runtime": {"name": rt.name if rt else "", "version": rt.version if rt else ""},
                     "parse_error": manifests[m.name].parse_error})
    return rows, manifests


def test_the_claimtrack_batch_runtime_case_is_asked_specifically(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    items = not_assessable(tmp_path, rows, manifests)
    batch = next(r for r in rows if r["path"] == "batch")
    runtime = [i for i in items if i["topic"] == "runtime" and i["modules"] == [batch["id"]]]
    assert len(runtime) == 1
    q = runtime[0]["question"]
    assert "declares Java 7" in q and "guava 23.0" in q and "Java 8 or later" in q
    api = next(r for r in rows if r["path"] == "api")
    assert not any(api["id"] in i["modules"] for i in items if i["topic"] == "runtime"), \
        "a module whose declared runtime satisfies its libraries is not asked about"


def test_a_batch_module_raises_the_scheduler_question(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    batch = next(r for r in rows if r["path"] == "batch")
    scheduler = [i for i in not_assessable(tmp_path, rows, manifests) if i["topic"] == "scheduler"]
    assert [i["modules"] for i in scheduler] == [[batch["id"]]]


def test_configuration_is_always_asked_and_names_the_files_found(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    config = [i for i in not_assessable(tmp_path, rows, manifests) if i["topic"] == "configuration"]
    assert len(config) == 1 and "api/application-prod.properties" in config[0]["question"]


def test_configuration_is_asked_even_with_no_files(tmp_path):
    rows, manifests = _rows(_repo(tmp_path, env_files=False))
    config = [i for i in not_assessable(tmp_path, rows, manifests) if i["topic"] == "configuration"]
    assert len(config) == 1 and "no per-environment files" in config[0]["question"]


def test_an_undeclared_runtime_is_asked(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    letters = next(r for r in rows if r["path"] == "letters")
    undeclared = [i for i in not_assessable(tmp_path, rows, manifests)
                  if i["topic"] == "runtime" and letters["id"] in i["modules"]]
    assert len(undeclared) == 1 and "No runtime version is declared" in undeclared[0]["question"]


def test_an_unreadable_manifest_is_asked(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    rows[0]["parse_error"] = "not well-formed XML"
    items = [i for i in not_assessable(tmp_path, rows, manifests) if i["topic"] == "unreadable"]
    assert [i["modules"] for i in items] == [[rows[0]["id"]]]


def test_the_list_is_deterministic(tmp_path):
    rows, manifests = _rows(_repo(tmp_path))
    assert not_assessable(tmp_path, rows, manifests) == not_assessable(tmp_path, list(reversed(rows)), manifests)


def test_java_needed_uses_the_highest_line_and_ignores_unknown_libraries():
    deps = [Dependency("org.springframework.boot:spring-boot-starter", "3.1.0"),
            Dependency("com.google.guava:guava", "20.0"), Dependency("com.acme:thing", "99")]
    assert _java_needed(deps) == (17, "org.springframework.boot:spring-boot-starter 3.1.0")
    assert _java_needed([Dependency("com.google.guava:guava", "20.0")]) is None
    assert _java_needed([Dependency("org.springframework:spring-core", "5.3.1")]) == (8, "org.springframework:spring-core 5.3.1")


def test_a_test_only_library_says_nothing_about_production():
    """Review finding 3a: JUnit is test-scoped; it says nothing about the production JRE."""
    assert _java_needed([Dependency("org.junit.jupiter:junit-jupiter", "5.9.0")]) is None


def test_guavas_android_flavour_says_nothing():
    """Review finding 3b: the -android flavour kept an older baseline than the JRE flavour."""
    assert _java_needed([Dependency("com.google.guava:guava", "25.1-android")]) is None
    assert _java_needed([Dependency("com.google.guava:guava", "25.1-jre")]) == (8, "com.google.guava:guava 25.1-jre")


def test_bin_and_packages_are_searched(tmp_path):
    """Review finding 6: a legacy bin/crontab and a monorepo's packages/*/.env.production."""
    _repo(tmp_path, env_files=False)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "crontab").write_text("0 2 * * * run\n", encoding="utf-8")
    (tmp_path / "packages" / "web").mkdir(parents=True)
    (tmp_path / "packages" / "web" / ".env.production").write_text("X=1\n", encoding="utf-8")
    rows, manifests = _rows(tmp_path)
    items = not_assessable(tmp_path, rows, manifests)
    assert "bin/crontab" in next(i for i in items if i["topic"] == "scheduler")["question"]
    assert "packages/web/.env.production" in next(i for i in items if i["topic"] == "configuration")["question"]


def test_ids_are_ordered_by_number():
    from agents_orchestrator.discovery_agent.analysis.unknowns import _id_key

    assert sorted([{"id": "M-100"}, {"id": "M-11"}, {"id": "M-02"}], key=_id_key) == [
        {"id": "M-02"}, {"id": "M-11"}, {"id": "M-100"}]
