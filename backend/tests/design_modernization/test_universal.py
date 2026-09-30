"""Phase F's universal pass over A–E (plan Part 1): nothing in the chain may assume one system.

  U1  the brief hands over its change freeze, cutover window, residency and dated milestones
  U2  end of support is known for databases and the other common server runtimes
  U3  the interface scanner reads Go, PHP, Ruby, VB.NET, COBOL/JCL and DECLARED contract files
  U4  a contract can be RPC, a screen, a job or a shared library
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agents_orchestrator.design_modernization_agent.analysis import checks
from agents_orchestrator.design_modernization_agent.analysis.interfaces import capture_interfaces
from agents_orchestrator.discovery_agent.analysis.eol import Runtime, runtime_status
from agents_orchestrator.modernization_common.handover.emit import brief_packet, brief_payload
from agents_orchestrator.modernization_common.handover.packets import FrozenContract

AS_OF = date(2026, 9, 30)
BRIEF = {"system_name": "Ledger", "goal": "Move off the mainframe.", "target_state": {"stack": "Java 21"},
         "in_scope": ["GL batch"], "success_measures": [{"metric": "totals", "target": "identical", "kind": "equivalence"}]}


# ── U1 ───────────────────────────────────────────────────────────────────────

def test_the_brief_hands_over_its_planning_dates_in_the_users_words():
    p = brief_payload({**BRIEF, "deadline": "end of Q2 2028", "downtime_window": "Saturday nights, max 4 hours",
                       "data_residency": "EU only", "milestones": [
                           {"date": "2028-06-30", "label": "Mainframe lease ends", "kind": "deadline"},
                           {"date": "2027-11-01", "label": "Change freeze", "kind": "freeze"},
                           {"date": "sometime in spring", "label": "Audit", "kind": "compliance"}]})
    assert p["freeze_from"] == "2027-11-01"
    assert p["deadline"] == "2028-06-30"  # the prose deadline falls back to the deadline milestone
    assert "Deadline: end of Q2 2028" in p["constraints"]  # …and the user's words are kept
    assert (p["downtime_window"], p["data_residency"]) == ("Saturday nights, max 4 hours", "EU only")
    assert [m["label"] for m in p["milestones"]] == ["Change freeze", "Mainframe lease ends"]  # undated one left out
    assert brief_packet({**BRIEF, "milestones": p["milestones"]}, {"version": 1, "status": "draft"}).ok


def test_a_brief_without_them_hands_over_nothing_invented():
    p = brief_payload(BRIEF)
    assert (p["freeze_from"], p["deadline"], p["downtime_window"], p["data_residency"], p["milestones"]) == (
        None, None, None, None, [])


# ── U2 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,version,status", [
    ("MySQL", "8.0.36", "eol"), ("MySQL", "8.4", "supported"), ("MySQL", "5.7", "eol"),
    ("PostgreSQL", "11.4", "eol"), ("PostgreSQL", "14", "approaching"), ("PostgreSQL", "17", "supported"),
    ("PostgreSQL", "9.6", "eol"),
    ("SQL Server", "2016", "eol"), ("SQL Server", "2019", "legacy"), ("SQL Server", "2022", "supported"),
    ("PHP", "7.4", "eol"), ("PHP", "8.2", "approaching"), ("PHP", "8.4", "supported"),
    ("Ruby", "2.7.8", "eol"), ("Ruby", "3.4", "supported"), ("Go", "1.21", "eol"), ("Go", "1.27", "unknown"),
])
def test_databases_and_other_runtimes_have_their_end_of_support(name, version, status):
    assert runtime_status(Runtime(name, version), AS_OF).status == status


@pytest.mark.parametrize("text,expected", [
    ("Azure Database for MySQL 8.0", ("MySQL", "8.0")),
    ("Postgres 16 on RDS", ("PostgreSQL", "16")), ("PostgreSQL 9.6", ("PostgreSQL", "9.6")),
    ("Azure Database for PostgreSQL Flexible Server 13", ("PostgreSQL", "13")),
    ("SQL Server Managed Instance 2016", ("SQL Server", "2016")),
    ("SQL Server 2019 Enterprise", ("SQL Server", "2019")),
    ("PHP 8.3-FPM", ("PHP", "8.3")), ("Ruby 3.3 on Rails 7", ("Ruby", "3.3")), ("Go 1.22", ("Go", "1.22")),
])
def test_the_design_check_reads_them_in_a_target(text, expected):
    assert Runtime(*expected) in checks.runtimes_in(text)


@pytest.mark.parametrize("text,expected", [
    ("PostgreSQL 16 (replacing MySQL 5.7)", [("PostgreSQL", "16")]),
    ("Java 21, was Java 8", [("Java", "21")]),
    ("Node 24 instead of Node 14", [("Node.js", "24")]),
    ("from VMs to Azure Database for MySQL 8.0", [("MySQL", "8.0")]),
    ("from VMs to Azure MySQL 8.0", [("MySQL", "8.0")]),  # "to" ends what is being left
])
def test_a_version_the_target_replaces_is_not_the_target(text, expected):
    assert [(r.name, r.version) for r in checks.runtimes_in(text)] == expected


def test_a_go_mod_minimum_is_not_the_runtime(tmp_path):
    from agents_orchestrator.discovery_agent.analysis.inventory import ModuleFacts
    from agents_orchestrator.discovery_agent.analysis.manifests import parse_module_manifest

    (tmp_path / "go.mod").write_text("module x\n\ngo 1.21\n", encoding="utf-8")
    rt = parse_module_manifest(tmp_path, ModuleFacts(name="x", path=".", ecosystem="Go", manifest="go.mod")).runtime
    status = runtime_status(rt, AS_OF)
    assert (rt.version, rt.minimum, status.status) == ("1.21", True, "unknown")
    assert "only the minimum" in status.note
    (tmp_path / "go.mod").write_text("module x\n\ngo 1.21\ntoolchain go1.21.5\n", encoding="utf-8")
    rt = parse_module_manifest(tmp_path, ModuleFacts(name="x", path=".", ecosystem="Go", manifest="go.mod")).runtime
    assert (rt.version, rt.minimum, runtime_status(rt, AS_OF).status) == ("1.21", False, "eol")


@pytest.mark.parametrize("files,expected", [
    ({"package.json": '{"engines": {"node": ">=14"}}'}, ("14", True)),
    ({"package.json": '{"engines": {"node": "14 || 16"}}'}, ("14", True)),
    ({"package.json": '{"engines": {"node": "^14.17"}}'}, ("14", False)),
    ({"package.json": '{"engines": {"node": "14.x"}}'}, ("14", False)),
    ({"package.json": '{"engines": {"node": ">=14"}}', ".nvmrc": "18.19.0\n"}, ("18", False)),
    ({"package.json": "{}", ".nvmrc": "v16\n"}, ("16", False)),
])
def test_a_node_minimum_is_marked_and_a_pin_file_wins(tmp_path, files, expected):
    from agents_orchestrator.discovery_agent.analysis.inventory import ModuleFacts
    from agents_orchestrator.discovery_agent.analysis.manifests import parse_module_manifest

    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    rt = parse_module_manifest(tmp_path, ModuleFacts(name="x", path=".", ecosystem="Node.js",
                                                     manifest="package.json")).runtime
    assert (rt.version, rt.minimum) == expected


@pytest.mark.parametrize("files,expected", [
    ({"pyproject.toml": '[project]\nrequires-python = ">=3.8"\n'}, ("3.8", True)),
    ({"pyproject.toml": '[project]\nrequires-python = "~=3.9"\n'}, ("3.9", True)),
    ({"pyproject.toml": '[project]\nrequires-python = "==3.9.*"\n'}, ("3.9", False)),
    ({"pyproject.toml": '[tool.poetry.dependencies]\npython = "^3.8"\n'}, ("3.8", True)),
    ({"pyproject.toml": '[project]\nrequires-python = ">=3.8"\n', ".python-version": "3.12.4\n"}, ("3.12", False)),
    ({"requirements.txt": "flask\n", "runtime.txt": "python-3.11.9\n"}, ("3.11", False)),
])
def test_a_python_minimum_is_marked_and_a_pin_file_wins(tmp_path, files, expected):
    from agents_orchestrator.discovery_agent.analysis.inventory import ModuleFacts
    from agents_orchestrator.discovery_agent.analysis.manifests import parse_module_manifest

    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    manifest = "pyproject.toml" if "pyproject.toml" in files else "requirements.txt"
    rt = parse_module_manifest(tmp_path, ModuleFacts(name="x", path=".", ecosystem="Python", manifest=manifest)).runtime
    assert (rt.version, rt.minimum) == expected


def test_a_node_or_python_minimum_is_scored_and_labelled_a_go_minimum_is_not():
    """Go's compatibility promise makes its minimum harmless; a legacy Node/Python app's minimum is the
    line it was written for — scored for migration risk, labelled, with the production version to confirm."""
    node = runtime_status(Runtime("Node.js", "14", minimum=True), AS_OF)
    assert node.status == "eol" and node.note.startswith("Declared as a minimum (Node.js 14 or later)")
    assert "confirm it" in node.note
    assert runtime_status(Runtime("Node.js", "14"), AS_OF).note == "Past the vendor's end of support."
    assert runtime_status(Runtime("Go", "1.21", minimum=True), AS_OF).status == "unknown"
    assert runtime_status(Runtime("Python", "3.99", minimum=True), AS_OF).status == "unknown"  # not in the table


def test_symfony_attribute_and_docblock_routes_are_read(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ClaimController.php").write_text(
        "<?php\n# a comment Route::get('/not-real')\nclass ClaimController {\n"
        "    #[Route('/api/claims', methods: ['GET'])]\n    public function list() {}\n"
        "    /**\n     * @Route(\"/api/claims/{id}\")\n     */\n    public function show() {}\n}\n", encoding="utf-8")
    got = {e["name"] for e in capture_interfaces(tmp_path)["items"]}
    assert {"/api/claims", "/api/claims/{id}"} <= {n.split()[-1] for n in got}
    assert not any("not-real" in n for n in got)


def test_a_database_target_past_support_is_refused_and_prose_is_not_a_version():
    out = checks.check_versions([("Database target", "Azure Database for MySQL Flexible Server 8.0")], AS_OF)
    assert "MySQL 8.0 is past its end of support (2026-04-30)" in out.problems[0]
    assert checks.runtimes_in("we go live on Sunday") == []


# ── U3 ───────────────────────────────────────────────────────────────────────

POLYGLOT = {
    "svc/main.go": ('package main\nfunc main() {\n  http.HandleFunc("/health", h)\n  r.GET("/claims/:id", get)\n'
                    '  os.WriteFile("/out/report.csv", b, 0644)\n  c.AddFunc("0 2 * * *", nightly)\n}\n'),
    "web/routes/api.php": "<?php\nRoute::get('/invoices/{id}', [InvoiceController::class, 'show']);\n"
                          "file_put_contents('/exports/daily.csv', $rows);\n",
    "rails/config/routes.rb": "Rails.application.routes.draw do\n  resources :orders\n  get '/status', to: 'status#show'\nend\n",
    "rails/app/models/order.rb": "class Order < ApplicationRecord\n  self.table_name = 'ORD_HDR'\nend\n",
    "legacy/OrdersController.vb": ('<Route("api/orders")>\nPublic Class OrdersController\n'
                                   '    <HttpGet("{id}")>\n    Public Function GetOrder(id As Integer) As Order\n'),
    "cobol/GLPOST.cbl": ("       FILE-CONTROL.\n           SELECT GL-IN ASSIGN TO GLINPUT.\n"
                         "      * a comment: EXEC CICS LINK PROGRAM('NOTREAL')\n"
                         "           EXEC SQL\n              SELECT AMT INTO :WS-AMT\n              FROM GL_BALANCE\n"
                         "           END-EXEC.\n           EXEC CICS LINK PROGRAM('GLVALID') END-EXEC.\n"
                         "           EXEC CICS SEND MAP('GLMAP01') END-EXEC.\n           CALL 'MQPUT' USING HCONN.\n"),
    "jcl/GLNIGHT.jcl": ("//GLNIGHT  JOB (ACCT),'GL NIGHTLY'\n//*  comment DSN=NOT.A.DATASET\n"
                        "//STEP1    EXEC PGM=GLPOST\n//GLINPUT  DD DSN=PROD.GL.DAILY,DISP=SHR\n"),
    "api/openapi.yaml": ("openapi: 3.0.1\ninfo:\n  title: Claims\npaths:\n  /claims:\n    get: {}\n"
                         "  /claims/{id}:\n    get: {}\ncomponents:\n  schemas: {}\n"),
    "api/Billing.wsdl": '<definitions><portType name="B"><operation name="GetInvoice"/></portType></definitions>\n',
    "api/ledger.proto": 'syntax = "proto3";\nservice Ledger {\n  rpc Post (Entry) returns (Ack);\n}\n',
    "api/schema.graphql": "type Query {\n  order(id: ID!): Order\n}\ntype Order {\n  id: ID!\n}\n",
    "deploy/nightly.yaml": "apiVersion: batch/v1\nkind: CronJob\nspec:\n  schedule: \"30 1 * * *\"\n",
}


@pytest.fixture(scope="module")
def polyglot(tmp_path_factory):
    root = tmp_path_factory.mktemp("polyglot")
    for rel, body in POLYGLOT.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return {(i["kind"], i["direction"], i["name"]): i["location"] for i in capture_interfaces(root)["items"]}


@pytest.mark.parametrize("entry,location", [
    (("http", "exposes", "/health"), "svc/main.go:3"),
    (("http", "exposes", "GET /claims/:id"), "svc/main.go:4"),
    (("file", "writes", "/out/report.csv"), "svc/main.go:5"),
    (("job", "runs", "0 2 * * *"), "svc/main.go:6"),
    (("http", "exposes", "/invoices/{id}"), "web/routes/api.php:2"),
    (("file", "writes", "/exports/daily.csv"), "web/routes/api.php:3"),
    (("http", "exposes", "orders"), "rails/config/routes.rb:2"),
    (("http", "exposes", "/status"), "rails/config/routes.rb:3"),
    (("db", "defines", "ORD_HDR"), "rails/app/models/order.rb:2"),
    (("http", "exposes", "GET api/orders/{id}"), "legacy/OrdersController.vb:3"),
    (("file", "uses", "GLINPUT."), "cobol/GLPOST.cbl:2"),
    (("db", "uses", "GL_BALANCE"), "cobol/GLPOST.cbl:4"),
    (("rpc", "consumes", "GLVALID"), "cobol/GLPOST.cbl:8"),
    (("ui", "exposes", "GLMAP01"), "cobol/GLPOST.cbl:9"),
    (("queue", "produces", "MQPUT"), "cobol/GLPOST.cbl:10"),
    (("job", "runs", "GLPOST"), "jcl/GLNIGHT.jcl:3"),
    (("file", "uses", "PROD.GL.DAILY"), "jcl/GLNIGHT.jcl:4"),
    (("http", "exposes", "/claims (declared)"), "api/openapi.yaml:5"),
    (("http", "exposes", "/claims/{id} (declared)"), "api/openapi.yaml:7"),
    (("rpc", "exposes", "SOAP GetInvoice"), "api/Billing.wsdl:1"),
    (("rpc", "exposes", "gRPC Ledger.Post"), "api/ledger.proto:3"),
    (("rpc", "exposes", "GraphQL Query.order"), "api/schema.graphql:2"),
    (("job", "runs", "30 1 * * *"), "deploy/nightly.yaml:4"),
])
def test_every_ecosystem_and_declared_contract_is_read(polyglot, entry, location):
    assert polyglot.get(entry) == location, sorted(polyglot)


def test_comments_and_non_root_graphql_types_are_not_interfaces(polyglot):
    names = {name for (_k, _d, name) in polyglot}
    assert not any("NOTREAL" in n or "NOT.A.DATASET" in n for n in names), names  # inside a name, too
    assert "GraphQL Query.id" not in names and not any("components" in n for n in names)


def test_only_the_paths_block_and_only_cronjob_manifests_are_declared(tmp_path):
    (tmp_path / "openapi.yaml").write_text(
        "openapi: 3.0.1\npaths:\n  /claims:\n    get: {}\nx-internal-routes:\n  /debug:\n    get: {}\n", encoding="utf-8")
    (tmp_path / "values.yaml").write_text("backup:\n  schedule: \"0 3 * * *\"\n", encoding="utf-8")
    names = {i["name"] for i in capture_interfaces(tmp_path)["items"]}
    assert "/claims (declared)" in names
    assert "/debug (declared)" not in names and "0 3 * * *" not in names, names


# ── U4 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["rpc", "ui", "job", "library", "http", "file"])
def test_a_contract_can_be_any_kind_of_interface(kind):
    FrozenContract(id="CT-01", name="x", kind=kind, legacy_location="a.cbl", proof="p", status="proposed")
