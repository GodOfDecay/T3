"""A small ClaimTrack legacy repository, and the brief / assessment as the pages STORE them.

The files sit at the locations the ClaimTrack design fixture cites (handover/fixtures/claimtrack/
design.json), so the fixture design can be checked against real code end to end. Plus two things a
scan must NOT read: a vendored jQuery with an Express-looking call, and a `.git` folder.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from agents_orchestrator.modernization_common.handover import FIXTURE_DIR

FILES = {
    "claimtrack-core/pom.xml": "<project><artifactId>claimtrack-core</artifactId></project>\n",
    "claimtrack-core/src/main/java/com/contoso/claimtrack/core/Claim.java": (
        "package com.contoso.claimtrack.core;\n@Entity\n@Table(name = \"claims\")\npublic class Claim {}\n"),
    "claimtrack-web/pom.xml": "<project><artifactId>claimtrack-web</artifactId></project>\n",
    "claimtrack-web/src/main/java/com/contoso/claimtrack/api/ClaimsApiController.java": (
        "package com.contoso.claimtrack.api;\n"
        "@RestController\n"
        "@RequestMapping(\"/api/v1/claims\")\n"
        "public class ClaimsApiController {\n"
        "    @GetMapping(\"/{id}\")\n"
        "    public Claim get(@PathVariable String id) { return repo.find(\"SELECT * FROM claims WHERE id = ?\"); }\n"
        "    @PostMapping\n"
        "    public Claim create(@RequestBody Claim c) { return c; }\n"
        "    @RequestMapping(value = \"/search\", method = RequestMethod.GET)\n"
        "    public List<Claim> search() { return rest.getForObject(\"https://risklens.contoso.com/score\", List.class); }\n"
        "    private RestTemplate rest;\n"
        "}\n"),
    "claimtrack-web/src/main/java/com/contoso/claimtrack/api/LegacyResource.java": (
        "@Path(\"/legacy\")\npublic class LegacyResource {\n    @GET\n    @Path(\"/ping\")\n    public String ping() { return \"ok\"; }\n}\n"),
    "claimtrack-web/src/main/webapp/WEB-INF/web.xml": (
        "<web-app><servlet-mapping><servlet-name>adj</servlet-name><url-pattern>/adjuster/*</url-pattern>"
        "</servlet-mapping></web-app>\n"),
    "claimtrack-web/src/main/webapp/adjuster/claim.jsp": "<html><body>claim</body></html>\n",
    "claimtrack-batch/pom.xml": "<project><artifactId>claimtrack-batch</artifactId></project>\n",
    "claimtrack-batch/src/main/java/com/contoso/claimtrack/batch/SettlementFileWriter.java": (
        "package com.contoso.claimtrack.batch;\n"
        "public class SettlementFileWriter {\n"
        "    @Scheduled(cron = \"0 30 1 * * *\")\n"
        "    public void write() throws Exception {\n"
        "        Map<String, Line> lines = new HashMap<>();\n"
        "        Writer w = new FileWriter(\"/out/bank/settlement.txt\");\n"
        "    }\n"
        "}\n"),
    "claimtrack-batch/src/main/java/com/contoso/claimtrack/batch/PolicyExtractReader.java": (
        "public class PolicyExtractReader {\n"
        "    List<String> read() { return Files.readAllLines(Paths.get(\"/data/policyhub/extract.csv\")); }\n"
        "    @KafkaListener(topics = \"claims-events\")\n"
        "    void on(String m) {}\n"
        "}\n"),
    "claimtrack-batch/src/main/resources/application.properties": "settlement.cron=0 30 1 * * *\n",
    "claimtrack-agent-portal/package.json": "{\"name\": \"claimtrack-agent-portal\"}\n",
    "claimtrack-agent-portal/src/server.js": "app.get('/portal/claims', handler);\nfetch('/api/v1/claims');\n",
    # NOT under a skipped folder: only the vendored-asset rule (by name) keeps it out.
    "claimtrack-agent-portal/src/static/jquery.min.js": "app.get('/not-ours', x);\n",
    "claimtrack-reports/requirements.txt": "pyyaml==3.12\n",
    "claimtrack-reports/cr4_return.py": (
        "import requests\n"
        "def main(out_path):\n"
        "    with open(out_path, \"w\") as fh:\n"
        "        fh.write(str(round(2.5)))\n"
        "    cfg = open('config.yml')\n"),
    "claimtrack-reports/sql/monthly.sql": (
        "-- monthly totals\nCREATE TABLE IF NOT EXISTS report_runs (id int);\n"
        "SELECT region, SUM(amount) FROM payouts GROUP BY region;\n"),
    ".git/config": "[core]\n",
}


def build_repo(root: Path) -> Path:
    for rel, body in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def design_payload() -> dict:
    """The ClaimTrack design fixture's payload (a fresh copy to edit)."""
    return copy.deepcopy(fixture("design")["payload"])


def stored_brief() -> dict:
    """The ClaimTrack brief as the Migration Intent page stores it (MigrationIntentArtifact)."""
    p = fixture("brief")["payload"]
    return {
        "system_name": p["system_name"], "goal": p["goal"],
        "target_state": {"stack": "; ".join(p["target_stack"]), "description": ""},
        "current_state": {"stack": "Java 7/8, Node 8, Python 2.7, MySQL 5.6", "description": ""},
        "in_scope": p["scope"]["in"], "out_of_scope": p["scope"]["out"], "constraints": p["constraints"],
        "deadline": p["deadline"], "budget": p["budget"], "must_not_change": p["must_not_change"],
        "success_measures": [{"metric": m["metric"], "current": m.get("today") or "", "target": m["target"],
                              "kind": m["kind"]} for m in p["success_measures"]],
        "business_drivers": ["Dallas data-centre exit"], "success_criteria": ["identical payouts"],
        "open_questions": p["open_questions"],
    }


def stored_assessment() -> dict:
    """The ClaimTrack assessment as the Dependency and Risk page stores it (schema 2)."""
    p = fixture("assessment")["payload"]
    return {
        "schema_version": 2, "generated_at": "2026-09-11T11:00:00Z", "as_of": "2026-09-11",
        "repository": {"url": p["repository"], "commit": p["commit"], "name": "Project 2", "branch": "main"},
        "summary": {"module_count": len(p["modules"])},
        "modules": [{"id": m["id"], "name": m["name"], "path": m["path"], "ecosystem": "maven",
                     "risk": {"tier": m["tier"], "score": m["score"], "factors": []},
                     "runtime": m.get("runtime") or {}, "depends_on": [], "dependents": [], "dependencies": [],
                     "blockers": []} for m in p["modules"]],
        "dependency_graph": {"edges": [{"from": "module:claimtrack-web", "to": "module:claimtrack-core",
                                        "type": "module"}]},
        "flags": {}, "scanners": {"trivy": "ok", "note": ""},
        "golden_master": {"status": "not_captured", "baselines": []},
        "not_assessable_statically": [{"topic": "runtime", "modules": [], "question": q}
                                      for q in p["not_assessable_statically"]],
    }
