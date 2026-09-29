"""`capture_legacy_interfaces` — the deterministic inventory the frozen contracts come from.

Guarding: each language's mappings are found WITH their class prefix and their file:line; entries
are attributed to the module whose folder holds them (its assessment id); vendored front-end code
and `.git` are never read; the same checkout gives the same inventory; the cap is reported.
"""
from __future__ import annotations

import pytest

from agents_orchestrator.design_modernization_agent.analysis import interfaces as iface
from tests.design_modernization.claimtrack import build_repo, stored_assessment

MODULES = [{"id": m["id"], "name": m["name"], "path": m["path"]} for m in stored_assessment()["modules"]]
API = "claimtrack-web/src/main/java/com/contoso/claimtrack/api/ClaimsApiController.java"


@pytest.fixture
def inventory(tmp_path):
    return iface.capture_interfaces(build_repo(tmp_path), MODULES, "a1b2c3d")


def _has(inv, kind, direction, name, location_prefix, module=None):
    for i in inv["items"]:
        if (i["kind"], i["direction"], i["name"]) == (kind, direction, name) and i["location"].startswith(location_prefix):
            return module is None or i["module"] == module
    return False


def test_spring_mappings_carry_the_class_prefix_and_the_line(inventory):
    assert _has(inventory, "http", "exposes", "GET /api/v1/claims/{id}", f"{API}:5", "M-02")
    assert _has(inventory, "http", "exposes", "POST /api/v1/claims", f"{API}:7")
    assert _has(inventory, "http", "exposes", "GET /api/v1/claims/search", f"{API}:9")


def test_jaxrs_joins_the_method_path_whatever_the_annotation_order(inventory):
    assert _has(inventory, "http", "exposes", "GET /legacy/ping", "claimtrack-web/src/main/java/com/contoso/claimtrack/api/LegacyResource.java:3")
    assert not _has(inventory, "http", "exposes", "GET /legacy", "claimtrack-web")


def test_servlets_and_pages_are_endpoints(inventory):
    assert _has(inventory, "http", "exposes", "servlet /adjuster/*", "claimtrack-web/src/main/webapp/WEB-INF/web.xml:1")
    assert _has(inventory, "http", "exposes", "JSP page /claimtrack-web/src/main/webapp/adjuster/claim.jsp",
                "claimtrack-web/src/main/webapp/adjuster/claim.jsp")


def test_outbound_calls_are_named_by_their_url(inventory):
    assert _has(inventory, "http", "consumes", "https://risklens.contoso.com/score", f"{API}:10")
    assert _has(inventory, "http", "consumes", "/api/v1/claims", "claimtrack-agent-portal/src/server.js:2", "M-04")


def test_files_written_and_read_are_found_with_their_literal(inventory):
    batch = "claimtrack-batch/src/main/java/com/contoso/claimtrack/batch/"
    assert _has(inventory, "file", "writes", "/out/bank/settlement.txt", batch + "SettlementFileWriter.java:6", "M-03")
    assert _has(inventory, "file", "reads", "/data/policyhub/extract.csv", batch + "PolicyExtractReader.java:2")
    assert _has(inventory, "file", "writes", "out_path", "claimtrack-reports/cr4_return.py:3", "M-05")
    assert _has(inventory, "file", "reads", "config.yml", "claimtrack-reports/cr4_return.py:5")


def test_jobs_tables_and_queues(inventory):
    assert _has(inventory, "job", "runs", "0 30 1 * * *", "claimtrack-batch/src/main/java/com/contoso/claimtrack/batch/SettlementFileWriter.java:3")
    assert _has(inventory, "job", "runs", "0 30 1 * * *", "claimtrack-batch/src/main/resources/application.properties:1")
    assert _has(inventory, "db", "defines", "claims", "claimtrack-core/", "M-01")
    assert _has(inventory, "db", "defines", "report_runs", "claimtrack-reports/sql/monthly.sql:2")
    assert _has(inventory, "db", "uses", "payouts", "claimtrack-reports/sql/monthly.sql:3")
    assert _has(inventory, "db", "uses", "claims", f"{API}:6")
    assert _has(inventory, "queue", "consumes", "claims-events", "claimtrack-batch/")


def test_vendored_code_and_git_are_never_read(inventory):
    assert not any("jquery" in i["location"] or i["location"].startswith(".git") for i in inventory["items"])
    assert not _has(inventory, "http", "exposes", "/not-ours", "")


def test_the_counts_add_up_and_it_is_deterministic(tmp_path, inventory):
    assert sum(inventory["counts"].values()) == inventory["total"] == len(inventory["items"]) == 21
    assert inventory["truncated"] is False and inventory["commit"] == "a1b2c3d"
    again = iface.capture_interfaces(build_repo(tmp_path / "again"), MODULES, "a1b2c3d")
    assert again["items"] == inventory["items"]


def test_the_cap_is_reported_not_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(iface, "MAX_ITEMS", 5)
    inv = iface.capture_interfaces(build_repo(tmp_path), MODULES)
    assert inv["truncated"] is True and len(inv["items"]) == 5 and inv["total"] == 21
    assert "capped at 5" in iface.interfaces_markdown(inv)


def test_the_report_cites_locations(inventory):
    md = iface.interfaces_markdown(inventory)
    assert "`GET /api/v1/claims/{id}` | `" + API + ":5` | M-02" in md
    assert iface.files_with_interfaces(inventory) >= {API, "claimtrack-reports/cr4_return.py"}


def test_a_module_path_prefix_does_not_match_a_sibling_folder():
    mods = [{"id": "M-01", "path": "web"}, {"id": "M-02", "path": "web-admin"}]
    assert iface._module_for("web-admin/x.java", mods) == "M-02"
    assert iface._module_for("web/x.java", mods) == "M-01"
    assert iface._module_for("other/x.java", mods) == ""
    assert iface._module_for("web-admin/x.java", [{"id": "M-01", "path": "web"}]) == ""
