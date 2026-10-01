"""The sandbox's own images — ONE place, pinned BY DIGEST (Phase G decision G2).

The harness (request driver, stub server) runs in `HARNESS`; the legacy system runs in an image built
from the legacy checkout's own Dockerfile, whose every `FROM` must be digest-pinned too
(`profile.check_dockerfile`). Development uses the official public images; moving to an organisation
registry is a change here (or the `SDLC_SANDBOX_HARNESS_IMAGE` setting), never in code that uses it.
"""
from __future__ import annotations

import os
import re

#: python:3.12-slim (official), pulled 2026-09-30.
_HARNESS_DEFAULT = "python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"

DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")


def harness_image() -> str:
    image = os.environ.get("SDLC_SANDBOX_HARNESS_IMAGE", "").strip() or _HARNESS_DEFAULT
    if not DIGEST_RE.search(image):
        raise ValueError(f"The sandbox harness image {image!r} is not pinned by digest (…@sha256:<64 hex>).")
    return image
