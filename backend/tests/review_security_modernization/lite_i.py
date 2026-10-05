"""ClaimTrack Lite for Migration Review and Security (Phase I).

Phase H's design (`lite_h`), with the two frozen contracts located in the sample (the shared fixture
places them in the full ClaimTrack's Java files), and the claims API migrated to Python 3.12 the way the
Phase H chain does it — both traps handled. `broken_server()` is the same migration with the rounding
trap left in (Python 3's round) and a status code changed: what a review must catch.
"""
from __future__ import annotations

import copy

from tests.development_modernization.lite_h import design as design_h
from tests.testing_modernization import lite


def design() -> dict:
    d = copy.deepcopy(design_h())
    for c in d["frozen_contracts"]:
        if c["id"] == "CT-01":
            c["legacy_location"] = "claims-api/server.py:58"
        if c["id"] == "CT-02":
            c["legacy_location"] = "settlement-batch/run.py:1"
    return d


LEGACY_SERVER = (lite.SAMPLE / "claims-api" / "server.py").read_text(encoding="utf-8")


def migrated_server() -> str:
    s = LEGACY_SERVER
    for old, new in (("import BaseHTTPServer\n", "import http.server\n"), ("import urllib2\n", "import urllib.request\n"),
                     ("import uuid\n", "import uuid\nfrom decimal import Decimal, ROUND_HALF_UP\n"),
                     ("BaseHTTPServer.BaseHTTPRequestHandler", "http.server.BaseHTTPRequestHandler"),
                     ("BaseHTTPServer.HTTPServer", "http.server.HTTPServer"),
                     ("urllib2.urlopen", "urllib.request.urlopen"),
                     ("        self.wfile.write(data)", "        self.wfile.write(data.encode(\"utf-8\"))"),
                     ("    return round(amount * rate, 2)",
                      "    # TR-01: the legacy rule, halves away from zero, on the float's exact value.\n"
                      "    return float(Decimal(amount * rate).quantize(Decimal(\"0.01\"), rounding=ROUND_HALF_UP))")):
        assert old in s, old
        s = s.replace(old, new)
    return s


def broken_server() -> str:
    """TR-01 not handled (Python 3 round), the 409 became a 400, and a new route nobody asked for."""
    s = migrated_server()
    s = s.replace("    # TR-01: the legacy rule, halves away from zero, on the float's exact value.\n"
                  "    return float(Decimal(amount * rate).quantize(Decimal(\"0.01\"), rounding=ROUND_HALF_UP))",
                  "    return round(amount * rate, 2)")
    s = s.replace("return self.reply(409,", "return self.reply(400,")
    s = s.replace('        if self.path == "/health":', '        if self.path == "/metrics":\n'
                  '            return self.reply(200, {"uptime": 1})\n        if self.path == "/health":')
    return s


FILE_MAP = [{"legacy_path": f"claims-api/{f}", "disposition": "mapped", "target_path": f"claims-api/{f}"}
            for f in ("requirements.txt", "runtime.txt", "server.py")]
TRAPS = {"TR-01": "claims-api/server.py payout(): Decimal ROUND_HALF_UP on the exact value",
         "TR-02": "claims-api/server.py Handler.reply(): the JSON is encoded to bytes before the socket write"}
