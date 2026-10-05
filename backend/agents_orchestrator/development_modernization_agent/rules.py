"""Where Migration Development may write, what counts as a build file, and what looks like a secret.

Pure — no git, no Docker, no database. The tools call these on every write and the record tool calls
them again over the whole branch diff, so a rule here is enforced twice (Phase H decisions H3, H4, H7).

WHERE (H4). A module's code is written under its own path in the target (the legacy path, kept: an
in-place upgrade keeps the layout so a reviewer can put the two side by side). Besides that, only the
repository's SHARED BUILD FILES at the root (a Dockerfile, CI definitions): the plan's waves migrate the
build with the module that needs it. Nothing else — never another module's code.

BUILD FILES (H3). The build is its own commit (research §6.6): a commit that mixes build files with code
is refused, so a reviewer sees the build change on its own.

SECRETS (H7). The agent never copies a credential from the legacy code or config: a write whose content
looks like one is refused, and the agent puts a vault reference in its place.
"""
from __future__ import annotations

import fnmatch
import posixpath
import re
from typing import Iterable

#: Build files by name, anywhere (a module's own build) — and the shared ones at the root.
BUILD_NAMES = (
    "Dockerfile", "Dockerfile.*", "*.dockerfile", "docker-compose*.yml", "docker-compose*.yaml",
    "requirements*.txt", "runtime.txt", ".python-version", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "Pipfile.lock", "poetry.lock", "tox.ini",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", ".nvmrc", "tsconfig*.json",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties",
    "*.csproj", "*.sln", "Directory.Build.props", "global.json", "go.mod", "go.sum", "Makefile",
    "azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml", "Jenkinsfile",
)
#: CI definitions live in folders.
BUILD_DIRS = (".github/workflows/", ".azure-pipelines/", ".pipelines/")
#: Root-level files any module's wave may change (the shared build).
SHARED_ROOT = ("Dockerfile", "Dockerfile.*", "docker-compose*.yml", "docker-compose*.yaml", "Makefile",
               "azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml", "Jenkinsfile", ".dockerignore",
               ".gitignore")


class WriteRefused(ValueError):
    """A write outside what this module may touch, or one carrying a secret. The message is for people."""


def clean_path(rel: str) -> str:
    """A repository-relative POSIX path, or WriteRefused (absolute, `..`, a drive, empty, `.git`)."""
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise WriteRefused(f"{rel!r} is not a path inside the target repository (write it relative, like "
                           "claims-api/server.py).")
    norm = posixpath.normpath(raw)
    if norm == "." or norm.startswith("../") or norm == ".." or "/../" in f"/{norm}/":
        raise WriteRefused(f"{rel!r} leaves the target repository.")
    if norm == ".git" or norm.startswith(".git/"):
        raise WriteRefused("The repository's .git folder is never written by hand.")
    return norm


def is_build_file(rel: str) -> bool:
    path = clean_path(rel)
    name = posixpath.basename(path)
    return any(fnmatch.fnmatchcase(name, p) for p in BUILD_NAMES) or any(path.startswith(d) for d in BUILD_DIRS)


def is_shared_build_file(rel: str) -> bool:
    """A root-level build file, or a CI definition — the build every module shares."""
    path = clean_path(rel)
    if any(path.startswith(d) for d in BUILD_DIRS):
        return True
    return "/" not in path and any(fnmatch.fnmatchcase(path, p) for p in SHARED_ROOT)


def in_module(rel: str, module_path: str) -> bool:
    path = clean_path(rel)
    root = clean_path(module_path)
    return path == root or path.startswith(root + "/")


def assert_may_write(rel: str, module_path: str) -> str:
    """The cleaned path, or WriteRefused naming why."""
    path = clean_path(rel)
    if in_module(path, module_path) or is_shared_build_file(path):
        return path
    raise WriteRefused(f"{path} is outside this module ({module_path}/) and is not a shared build file at the "
                       "repository root. A module's migration never touches another module's code.")


def out_of_bounds(changed: Iterable[str], module_path: str) -> list[str]:
    """Every changed path this module may not touch (the record tool's whole-branch check)."""
    bad = []
    for rel in changed:
        try:
            assert_may_write(rel, module_path)
        except WriteRefused:
            bad.append(rel)
    return sorted(bad)


def mixed_commit(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """(build files, code files) of a commit: both non-empty means it mixes concerns."""
    build, code = [], []
    for p in paths:
        (build if is_build_file(p) else code).append(p)
    return sorted(build), sorted(code)


# ── secrets ──────────────────────────────────────────────────────────────────

_SECRET_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("a private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("an Azure storage account key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
    ("a connection string with a password", re.compile(
        r"(?i)\b(?:password|pwd)\s*=\s*(?![\"']?\s*(?:\$\{|\{\{|%\(|<|os\.environ|getenv|env\[|kv://|vault:))[^\s;\"'<>]{4,}")),
    ("a URL with a password in it", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{4,}@[^\s/]+")),
    # A name that CONTAINS the word (DB_PASSWORD, clientSecret), a quoted value (Phase I found the
    # plain `\bpassword\b` form missed both, and quoted passwords altogether).
    ("a hard-coded password", re.compile(
        r"(?i)\b\w*(?:password|passwd|pwd)\w*\s*[:=]\s*[\"'](?!kv://|vault:|keyvault:|secretsmanager:|env:|\$\{)[^\"'\s]{6,}[\"']")),
    ("a hard-coded secret", re.compile(
        r"(?i)\b\w*(?:secret|api[_-]?key|access[_-]?token)\w*\s*[:=]\s*[\"'][A-Za-z0-9+/_\-]{12,}[\"']")),
)


def secrets_in(text: str) -> list[str]:
    """What kinds of credential the text appears to hold (names only — never the value)."""
    return [name for name, rule in _SECRET_RULES if rule.search(text or "")]
