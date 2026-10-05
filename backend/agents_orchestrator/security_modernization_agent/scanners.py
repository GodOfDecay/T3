"""The three scanners of Track 3 Security, run the same way on the target and on the legacy (Phase I, I7).

Each is a digest-pinned image run offline:

  trivy     dependency vulnerabilities (SCA) and a CycloneDX SBOM. Its vulnerability database is a
            directory on the server (`SDLC_TRIVY_CACHE`, default <FILES>/scanner-cache/trivy) filled by
            a SEPARATE refresh step that has network (`refresh_command`); a scan never downloads. The
            database is opened read-write by Trivy's storage engine, so the directory is mounted (not the
            scanned code, which is always read-only). Trivy does not execute what it scans.
  semgrep   static analysis with the platform's own rule file (`rules/semgrep.yml`), metrics off.
  gitleaks  secrets. A secret's VALUE never leaves this module: it is hashed (`secret_hash`) for the
            carry-over check and dropped.

Every container: `--network none`, `runner.limits()`, read-only root with a tmpfs /tmp, the checkout
mounted read-only at /scan. A scanner that cannot run says so (`not_installed` / `failed`) and is never
reported clean (R39): with one missing, the sign-off cannot be PASS.

Normalized finding: {tool, rule, title, severity, file, line, package, version, cve, fixed_version,
secret_hash}. Severity: Trivy's own; Semgrep ERROR → high, WARNING → medium, INFO → low; a Gitleaks
secret → critical.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from typing import Optional

from agents_orchestrator.testing_modernization_agent.sandbox.runner import CaptureFailed, docker, limits

IMAGES = {
    "trivy": "aquasec/trivy@sha256:ab70a02200597efa04748f210f793936eb647cbcdb0ea69cc30b226d6f5a22c7",       # 0.58.1
    "semgrep": "semgrep/semgrep@sha256:ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98",   # 1.99.0
    "gitleaks": "zricethezav/gitleaks@sha256:0e99e8821643ea5b235718642b93bb32486af9c8162c8b8731f7cbdc951a7f46",  # v8.21.2
}
VERSIONS = {"trivy": "0.58.1", "semgrep": "1.99.0", "gitleaks": "8.21.2"}
SCANNERS = ("trivy", "semgrep", "gitleaks")
RULES_DIR = pathlib.Path(__file__).resolve().parent / "rules"
SCAN_SECONDS = 600
_SEMGREP_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
_TRIVY_SEVERITY = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low", "UNKNOWN": "info"}


class ScannerUnavailable(Exception):
    """A scanner that could not run. The message is for people."""


def image(tool: str) -> str:
    """The pinned image; `SDLC_SCANNER_IMAGE_<TOOL>` overrides it, and must be pinned by digest too."""
    override = os.environ.get(f"SDLC_SCANNER_IMAGE_{tool.upper()}", "").strip()
    ref = override or IMAGES[tool]
    if "@sha256:" not in ref:
        raise ScannerUnavailable(f"The {tool} image {ref!r} is not pinned by digest; set it as name@sha256:….")
    return ref


def trivy_cache() -> pathlib.Path:
    raw = os.environ.get("SDLC_TRIVY_CACHE", "").strip()
    if raw:
        return pathlib.Path(raw)
    from config import sdlcSettings  # noqa: PLC0415

    return pathlib.Path(sdlcSettings().FILES) / "scanner-cache" / "trivy"


def trivy_db_ready() -> bool:
    return (trivy_cache() / "db" / "trivy.db").is_file()


def refresh_command() -> str:
    """What an operator runs (with network) to fill or refresh Trivy's database. Shown, never run here."""
    return (f"docker run --rm -v {trivy_cache()}:/cache {IMAGES['trivy']} image --download-db-only --cache-dir /cache")


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]


def _run(tool: str, base: pathlib.Path, argv: list[str], extra_mounts: list[str], label: str) -> str:
    args = ["run", "--rm", "--network", "none", *limits(), "--read-only", "--tmpfs", "/tmp:rw,exec",
            "-e", "HOME=/tmp", "--mount", f"type=bind,src={base.resolve()},dst=/scan,readonly", *extra_mounts]
    if label:
        args += ["--label", f"sdlc.security={label}"]
    try:
        proc = docker(*args, image(tool), *argv, check=False, timeout=SCAN_SECONDS)
    except CaptureFailed as exc:
        raise ScannerUnavailable(str(exc)) from exc
    if proc.returncode == 125 or (proc.returncode not in (0, 1) and not (proc.stdout or "").strip()):
        raise ScannerUnavailable(f"{tool} could not run: {(proc.stderr or '').strip()[-300:]}")
    return proc.stdout or ""


def _rel(path: str, module_path: str = "") -> str:
    p = (path or "").replace("\\", "/")
    if p.startswith("/scan/"):
        return p[len("/scan/"):]
    return f"{module_path.rstrip('/')}/{p}" if module_path and not p.startswith(module_path.rstrip("/") + "/") else p


def parse_trivy(raw: str, module_path: str) -> list[dict]:
    data = json.loads(raw or "{}")
    out = []
    for r in data.get("Results") or []:
        target = _rel(r.get("Target") or "", module_path)
        for v in r.get("Vulnerabilities") or []:
            out.append({"tool": "trivy", "rule": v.get("VulnerabilityID"), "cve": v.get("VulnerabilityID"),
                        "title": (v.get("Title") or v.get("VulnerabilityID") or "")[:200],
                        "severity": _TRIVY_SEVERITY.get(str(v.get("Severity", "UNKNOWN")).upper(), "info"),
                        "package": v.get("PkgName"), "version": v.get("InstalledVersion"),
                        "fixed_version": v.get("FixedVersion"), "file": target, "line": None, "secret_hash": None})
    return out


def parse_sbom(raw: str) -> int:
    return len(json.loads(raw or "{}").get("components") or [])


def parse_semgrep(raw: str) -> tuple[list[dict], list[str]]:
    data = json.loads(raw or "{}")
    out = []
    for r in data.get("results") or []:
        rule = str(r.get("check_id") or "").split(".")[-1]
        extra = r.get("extra") or {}
        out.append({"tool": "semgrep", "rule": rule, "cve": None, "title": (extra.get("message") or rule)[:200],
                    "severity": _SEMGREP_SEVERITY.get(str(extra.get("severity", "")).upper(), "low"),
                    "package": None, "version": None, "fixed_version": None, "file": _rel(r.get("path") or ""),
                    "line": (r.get("start") or {}).get("line"), "secret_hash": None})
    errors = [str(e.get("message") or e.get("type") or "")[:200] for e in data.get("errors") or []]
    return out, errors


def parse_gitleaks(raw: str) -> tuple[list[dict], list[str]]:
    """Findings without the value, and the values themselves (for the carry-over check only)."""
    data = json.loads(raw or "[]") or []
    out, values = [], []
    for r in data:
        value = str(r.get("Secret") or "")
        values.append(value)
        out.append({"tool": "gitleaks", "rule": r.get("RuleID"), "cve": None,
                    "title": f"Secret in code ({r.get('RuleID')})", "severity": "critical", "package": None,
                    "version": None, "fixed_version": None, "file": _rel(r.get("File") or ""),
                    "line": r.get("StartLine"), "secret_hash": secret_hash(value) if value else None})
    return out, values


def scan(base: pathlib.Path, module_path: str, *, label: str = "") -> dict:
    """All three scanners on `base/<module_path>`. Returns {scans: {tool: status}, notes: {tool: why},
    findings: [...], sbom: {components, vulnerabilities}, secret_values: [...]} — the caller keeps
    `secret_values` in memory only."""
    target = f"/scan/{module_path.strip('/')}"
    scans, notes, findings, values = {}, {}, [], []
    sbom = {"components": None, "vulnerabilities": None}
    if not (base / module_path).is_dir():
        raise ScannerUnavailable(f"{module_path}/ is not in the checkout.")
    # Trivy: SCA, then the SBOM.
    if not trivy_db_ready():
        scans["trivy"], notes["trivy"] = "not_installed", (
            "Trivy's vulnerability database is not on this server. An operator fills it once (with network): "
            + refresh_command())
    else:
        common = ["--skip-db-update", "--skip-java-db-update", "--offline-scan", "--cache-dir", "/cache",
                  "--cache-backend", "memory", "--quiet"]
        mount = ["--mount", f"type=bind,src={trivy_cache().resolve()},dst=/cache"]
        try:
            vulns = parse_trivy(_run("trivy", base, ["fs", "--scanners", "vuln", "--format", "json", *common, target],
                                     mount, label), module_path)
            components = parse_sbom(_run("trivy", base, ["fs", "--format", "cyclonedx", *common, target], mount, label))
            findings += vulns
            sbom = {"components": components, "vulnerabilities": len(vulns)}
            scans["trivy"] = "ran"
        except (ScannerUnavailable, ValueError) as exc:
            scans["trivy"], notes["trivy"] = "failed", str(exc)[:300]
    try:
        hits, errors = parse_semgrep(_run(
            "semgrep", base, ["semgrep", "scan", "--config", "/rules/semgrep.yml", "--json", "--metrics=off",
                              "--disable-version-check", "--quiet", target],
            ["--mount", f"type=bind,src={RULES_DIR},dst=/rules,readonly", "-e", "SEMGREP_SEND_METRICS=off"], label))
        findings += hits
        scans["semgrep"] = "ran"
        if errors:
            notes["semgrep"] = f"{len(errors)} file(s) could not be fully parsed (e.g. {errors[0][:120]})"
    except (ScannerUnavailable, ValueError) as exc:
        scans["semgrep"], notes["semgrep"] = "failed", str(exc)[:300]
    try:
        hits, values = parse_gitleaks(_run(
            "gitleaks", base, ["dir", target, "-f", "json", "-r", "/dev/stdout", "--no-banner", "--exit-code", "0"],
            [], label))
        findings += hits
        scans["gitleaks"] = "ran"
    except (ScannerUnavailable, ValueError) as exc:
        scans["gitleaks"], notes["gitleaks"] = "failed", str(exc)[:300]
    return {"scans": scans, "notes": notes, "findings": findings, "sbom": sbom, "secret_values": values,
            "versions": dict(VERSIONS)}


def available() -> Optional[str]:
    """None when Docker answers, else why not."""
    try:
        proc = docker("info", check=False, timeout=30)
    except CaptureFailed as exc:
        return str(exc)
    return None if proc.returncode == 0 else "Docker is not running on this server."
