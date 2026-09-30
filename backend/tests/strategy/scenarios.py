"""Two unrelated migrations the Strategy rules must both handle — the plan is universal, not ClaimTrack's.

  claimtrack()  the research's ClaimTrack chain (Java/Node/Python → Azure), from the handover fixtures.
  payroll()     a .NET Framework 4.6.2 payroll system → .NET 8 on AWS: a dependency CYCLE (M-02 ⇄ M-03
                must move together), a module moved before its dependency under an ADR (M-04 before
                M-01, branch by abstraction), a module the design KEEPS (M-05), a weekend cutover window
                with a 4-hour limit, a change-freeze milestone, and no dated deadline.

Each returns (brief, assessment, design, plan) as hand-over PAYLOADS (dicts), valid by the models.
"""
from __future__ import annotations

import copy

from tests.design_modernization.claimtrack import fixture


def claimtrack():
    return tuple(copy.deepcopy(fixture(n)["payload"]) for n in ("brief", "assessment", "design", "plan"))


def payroll():
    brief = {
        "system_name": "Payroll", "goal": "Leave .NET Framework and the on-premises farm before the licence renewal.",
        "target_stack": [".NET 8 on AWS ECS", "SQL Server 2022"],
        "scope": {"in": ["PayCalc", "PayRules", "PayRules.Tax", "Payslip portal"], "out": ["HR master data"]},
        "constraints": ["weekend cutovers only"], "deadline": None, "budget": None,
        "freeze_from": "2027-03-01", "downtime_window": "Saturday–Sunday, at most 4 hours",
        "data_residency": "UK regions only",
        "must_not_change": ["the BACS payment file format"],
        "success_measures": [
            {"metric": "net pay identical on 12 recorded payroll runs", "target": "identical", "kind": "equivalence"},
            {"metric": "payslip page p95", "today": "3 s", "target": "under 1 s", "kind": "performance"},
            {"metric": "licence savings", "target": "£120k a year", "kind": "cost"},
        ],
        "business_owner": None, "open_questions": [],
        "milestones": [{"date": "2027-03-01", "label": "Year-end change freeze", "kind": "freeze"},
                       {"date": "2027-09-30", "label": "Farm licence renewal", "kind": "decommission"}],
    }
    assessment = {
        "repository": "https://github.com/acme/payroll", "commit": "9f8e7d6",
        "modules": [
            {"id": "M-01", "name": "Payroll.Common", "path": "src/Common", "tier": "mechanical", "score": 20, "loc": 12000},
            {"id": "M-02", "name": "PayCalc", "path": "src/PayCalc", "tier": "llm_assisted", "score": 60, "loc": 40000},
            {"id": "M-03", "name": "PayRules", "path": "src/PayRules", "tier": "llm_assisted", "score": 55, "loc": 25000},
            {"id": "M-04", "name": "Payslip.Web", "path": "src/Web", "tier": "manual", "score": 70, "loc": 18000},
            {"id": "M-05", "name": "Payroll.Archive", "path": "src/Archive", "tier": "mechanical", "score": 10, "loc": 3000},
        ],
        "graph": [["M-02", "M-01"], ["M-02", "M-03"], ["M-03", "M-02"], ["M-04", "M-01"], ["M-04", "M-02"]],
        "flags": {"eol": [], "deprecated": [], "vulnerable": []},
        "golden_master": {"status": "not_captured", "baselines": []},
        "not_assessable_statically": [],
    }
    design = {
        "summary": "Upgrade in place to .NET 8; the web tier is rewritten behind an abstraction.",
        "layers": [{"layer": "Runtime", "today": ".NET Framework 4.6.2", "target": ".NET 8", "modules": ["M-01", "M-02"]}],
        "modules": [
            {"module_id": "M-01", "module": "Payroll.Common", "tier": "mechanical", "risk_score": 20,
             "patterns": ["in_place_upgrade"], "rationale": "mechanical", "adr_ids": ["ADR-01"], "contract_ids": []},
            {"module_id": "M-02", "module": "PayCalc", "tier": "llm_assisted", "risk_score": 60,
             "patterns": ["in_place_upgrade", "parallel_run"], "rationale": "financial output", "adr_ids": [],
             "contract_ids": ["CT-01"]},
            {"module_id": "M-03", "module": "PayRules", "tier": "llm_assisted", "risk_score": 55,
             "patterns": ["in_place_upgrade"], "rationale": "cycle with PayCalc", "adr_ids": [], "contract_ids": []},
            {"module_id": "M-04", "module": "Payslip.Web", "tier": "manual", "risk_score": 70,
             "patterns": ["rewrite", "branch_by_abstraction"], "rationale": "WebForms", "adr_ids": ["ADR-01"],
             "contract_ids": []},
            {"module_id": "M-05", "module": "Payroll.Archive", "tier": "mechanical", "risk_score": 10,
             "patterns": ["keep"], "rationale": "read-only archive, out of scope", "adr_ids": [], "contract_ids": []},
        ],
        "frozen_contracts": [{"id": "CT-01", "name": "BACS payment file", "kind": "file",
                              "legacy_location": "src/PayCalc/Bacs.cs", "proof": "byte compare",
                              "status": "confirmed", "brief_item": "the BACS payment file format"}],
        "traps": [{"id": "TR-01", "change": "decimal rounding in .NET Core Math.Round", "affects": ["M-02"],
                   "where": "src/PayCalc/Rounding.cs", "effect": "pennies differ"}],
        "adrs": [{"id": "ADR-01", "title": "Payslip rewrite behind an abstraction over Common",
                  "context": "WebForms has no upgrade path", "options": ["wait for Common", "abstraction"],
                  "decision": "abstraction", "consequences": "Payslip moves before Common"}],
    }
    plan = {
        "summary": "Foundation, then the Payslip rewrite behind its abstraction, then Common, then the pay engine.",
        "waves": [
            {"id": "W0", "name": "Foundation", "modules": [], "patterns": {}, "starts": "2026-11-02", "ends": "2026-12-18",
             "date_status": "proposed", "entry_criteria": [], "exit_criteria": ["pipelines green", "baselines accepted"],
             "rollback": {"trigger": "foundation unhealthy", "method": "nothing to roll back"}, "order_reason": "foundation"},
            {"id": "W1", "name": "Payslip", "modules": ["M-04"], "patterns": {"M-04": ["rewrite", "branch_by_abstraction"]},
             "starts": "2027-01-04", "ends": "2027-02-26", "date_status": "proposed", "entry_criteria": ["W0 exit met"],
             "exit_criteria": ["EC-03", "security sign-off"], "cutover_window": "Sat 27 Feb 2027 22:00–01:00",
             "rollback": {"trigger": "p95 over 1 s", "method": "switch the abstraction back"},
             "order_reason": "ADR-01 lets the rewrite run against the old Common"},
            {"id": "W2", "name": "Common", "modules": ["M-01"], "patterns": {"M-01": ["in_place_upgrade"]},
             "starts": "2027-03-01", "ends": "2027-04-30", "date_status": "proposed", "entry_criteria": ["W0 exit met"], "exit_criteria": ["security sign-off"],
             "cutover_window": "Sun 2 May 2027 01:00–03:00",
             "rollback": {"trigger": "build fails", "method": "redeploy the Framework build"}, "order_reason": "lowest risk"},
            {"id": "W3", "name": "Pay engine", "modules": ["M-02", "M-03"],
             "patterns": {"M-02": ["in_place_upgrade", "parallel_run"], "M-03": ["in_place_upgrade"]},
             "starts": "2027-05-03", "ends": "2027-08-27", "date_status": "proposed", "entry_criteria": ["W2 exit met"],
             "exit_criteria": ["EC-01", "EC-02", "three identical runs"],
             "parallel_run": {"required": True, "period": "three monthly payroll runs", "system_of_record": "legacy"},
             "cutover_window": "Sat 28 Aug 2027 20:00–23:30",
             "rollback": {"trigger": "any net-pay difference", "method": "legacy stays the system of record"},
             "order_reason": "the cycle PayCalc ⇄ PayRules moves together, after Common"},
        ],
        "order_exceptions": [{"module_id": "M-04", "depends_on": "M-01", "reason": "Payslip reads Common through the "
                              "abstraction until Common moves", "adr_id": "ADR-01"},
                             {"module_id": "M-04", "depends_on": "M-02", "reason": "Payslip calls PayCalc through the "
                              "abstraction", "adr_id": "ADR-01"}],
        "equivalence_criteria": [
            {"id": "EC-01", "module_id": "M-02", "protects": ["CT-01", "TR-01"],
             "protects_measures": ["net pay identical on 12 recorded payroll runs"], "observable": "BACS file and net pay",
             "input_set": "12 recorded monthly runs", "comparison": "byte_identical",
             "normalization": [{"field": "file creation time", "rule": "ignore", "reason": "written at run time"}]},
            {"id": "EC-02", "module_id": "M-03", "protects": ["TR-01"], "observable": "rule outcomes",
             "input_set": "12 recorded runs", "comparison": "exact"},
            {"id": "EC-03", "module_id": "M-04", "protects_measures": ["payslip page p95"], "observable": "p95",
             "input_set": "recorded peak", "comparison": "percentile_threshold", "threshold": "p95 < 1 s"},
        ],
        "baseline_plan": [
            {"ec_id": "EC-01", "inputs": "12 runs", "environment": "legacy sandbox", "data_source": "snapshot",
             "masking": "tokenize employee data", "due": "2026-12-18"},
            {"ec_id": "EC-02", "inputs": "12 runs", "environment": "legacy sandbox", "data_source": "snapshot",
             "masking": "tokenize employee data", "due": "2026-12-18"},
        ],
        "freeze_policy": {"from": "2027-03-01", "allowed": "statutory changes only",
                          "carry_forward": "carried to the target within one pay cycle and re-baselined"},
        "critical_path": ["W3 parallel run", "licence renewal 30 Sep 2027"],
        "calendar_conflicts": [],
        "effort": [{"wave": w, "band": "tbd", "basis": "table"} for w in ("W0", "W1", "W2", "W3")],
        "budget_fit": "",
    }
    return brief, assessment, design, plan
