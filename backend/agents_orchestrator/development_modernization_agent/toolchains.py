"""Toolchains and upgrade recipes — DATA, one place (Phase H decision H5).

A toolchain is what a target ecosystem is built, tested and linted with, and the upgrade recipes that
move code onto it. Every command runs inside a digest-pinned image (`sandbox.run`), with no network, so
the same workspace gives the same result anywhere. Adding an ecosystem (Java with OpenRewrite, Node with
a codemod) is a new entry here plus its image, never code in the tools.

`{path}` in a command is the module's path inside the workspace (validated before use, passed as one
argv item — never through a shell).

Only what is catalogued is offered (research §6.6: "Only the recipes list_upgrade_recipes offers"). An
ecosystem with no entry is reported as such: the agent rewrites file by file and nothing is claimed.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Optional

from agents_orchestrator.testing_modernization_agent.sandbox.images import DIGEST_RE

#: Mounted read-only at /sdlc in every toolchain container: the checks that run there.
CHECKS_DIR = pathlib.Path(__file__).resolve().parent / "checks"

#: python:3.12-slim (official), pulled 2026-09-30 — the same image the baseline harness runs on.
_PYTHON_312 = "python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"


@dataclass(frozen=True)
class Recipe:
    id: str
    tool: str
    version: str                      # pinned: the image digest fixes it
    argv: tuple[str, ...]             # `{path}` is replaced by the scope
    describes: str
    from_runtime: str                 # what it upgrades from, for the agent's choice


@dataclass(frozen=True)
class Toolchain:
    ecosystem: str
    runtime: str
    image: str
    build: tuple[str, ...]
    test: tuple[str, ...]
    lint: tuple[str, ...]
    recipes: tuple[Recipe, ...] = field(default_factory=tuple)
    #: Files a test command needs to find before "tests" means anything (else tests are "not run").
    test_marker: str = ""

    def recipe(self, recipe_id: str) -> Optional[Recipe]:
        return next((r for r in self.recipes if r.id == recipe_id), None)


TOOLCHAINS: dict[str, Toolchain] = {
    "python": Toolchain(
        ecosystem="python",
        runtime="Python 3.12",
        image=_PYTHON_312,
        # compile + resolve every import WITHOUT running the module (`checks/python_build.py`): a port's
        # breakages (urllib2, BaseHTTPServer) are valid syntax and only fail at import.
        build=("python", "/sdlc/python_build.py", "{path}"),
        test=("python", "-m", "unittest", "discover", "-s", "{path}", "-t", ".", "-p", "test*.py"),
        lint=("python", "-m", "tabnanny", "-q", "{path}"),
        test_marker="test*.py",
        recipes=(
            Recipe(id="2to3", tool="lib2to3", version="CPython 3.12.14 stdlib (image " + _PYTHON_312[-12:] + ")",
                   argv=("python", "-W", "ignore", "-m", "lib2to3", "-w", "-n", "--no-diffs", "{path}"),
                   describes="Python 2 → 3 syntax and standard-library moves: print, imports (urllib2, "
                             "BaseHTTPServer…), dict methods, except/raise forms, unicode literals",
                   from_runtime="Python 2"),
        ),
    ),
}


def toolchain(ecosystem: str) -> Optional[Toolchain]:
    return TOOLCHAINS.get((ecosystem or "").strip().lower())


def image_for(chain: Toolchain) -> str:
    """The image a toolchain runs in — overridable per ecosystem for an organisation registry
    (`SDLC_TOOLCHAIN_IMAGE_<ECOSYSTEM>`), always pinned by digest."""
    image = os.environ.get(f"SDLC_TOOLCHAIN_IMAGE_{chain.ecosystem.upper()}", "").strip() or chain.image
    if not DIGEST_RE.search(image):
        raise ValueError(f"The {chain.ecosystem} toolchain image {image!r} is not pinned by digest (…@sha256:<64 hex>).")
    return image


def ecosystem_for(runtime_text: str) -> str:
    """'Python 3.12' / 'python 2.7' / 'CPython' → 'python'. Unknown → ''."""
    text = (runtime_text or "").lower()
    if "python" in text:
        return "python"
    return ""


def argv(template: tuple[str, ...], path: str) -> list[str]:
    return [path if a == "{path}" else a for a in template]
