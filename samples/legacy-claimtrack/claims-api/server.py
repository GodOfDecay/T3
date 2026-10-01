# -*- coding: utf-8 -*-
"""ClaimTrack claims API — legacy, Python 2.7 standard library only.

GET  /health
GET  /api/claims/<id>
POST /api/claims/<id>/settle     asks the fraud-score service first; pays amount x coverage
"""
import BaseHTTPServer
import datetime
import json
import os
import re
import sqlite3
import urllib2
import uuid

DB = os.environ.get("CLAIMTRACK_DB", "/data/claimtrack.db")
FRAUD_URL = os.environ.get("FRAUD_URL", "http://fraudscore:9000")
REFER_ABOVE = 80


def now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def payout(amount, rate):
    # The legacy rule: Python 2 round() — halves away from zero. round(0.125, 2) == 0.13 here.
    return round(amount * rate, 2)


def fraud_score(claim_id):
    reply = urllib2.urlopen("%s/score?claim=%s" % (FRAUD_URL, claim_id), timeout=5).read()
    return json.loads(reply)["score"]


def load(conn, claim_id):
    row = conn.execute("SELECT id, claimant, amount, coverage_rate, status, payout FROM claims WHERE id = ?",
                       (claim_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "claimant": row[1], "amount": row[2], "coverageRate": row[3],
            "status": row[4], "payout": row[5]}


class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
    def reply(self, status, body):
        body["requestId"] = str(uuid.uuid4())
        data = json.dumps(body, sort_keys=True)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"status": "ok"})
        m = re.match(r"^/api/claims/([A-Z0-9-]+)$", self.path)
        if not m:
            return self.reply(404, {"error": "not found"})
        conn = sqlite3.connect(DB)
        claim = load(conn, m.group(1))
        conn.close()
        if claim is None:
            return self.reply(404, {"error": "claim not found"})
        return self.reply(200, {"claim": claim, "generatedAt": now()})

    def do_POST(self):
        m = re.match(r"^/api/claims/([A-Z0-9-]+)/settle$", self.path)
        if not m:
            return self.reply(404, {"error": "not found"})
        conn = sqlite3.connect(DB)
        claim = load(conn, m.group(1))
        if claim is None:
            conn.close()
            return self.reply(404, {"error": "claim not found"})
        if claim["status"] != "open":
            conn.close()
            return self.reply(409, {"error": "claim is %s" % claim["status"]})
        score = fraud_score(claim["id"])
        if score > REFER_ABOVE:
            conn.execute("UPDATE claims SET status = 'referred' WHERE id = ?", (claim["id"],))
            conn.commit()
            conn.close()
            return self.reply(200, {"claimId": claim["id"], "status": "referred", "fraudScore": score})
        paid = payout(claim["amount"], claim["coverageRate"])
        conn.execute("UPDATE claims SET status = 'settled', payout = ? WHERE id = ?", (paid, claim["id"]))
        conn.commit()
        conn.close()
        return self.reply(200, {"claimId": claim["id"], "status": "settled", "payout": paid,
                                "fraudScore": score, "settledAt": now()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    BaseHTTPServer.HTTPServer(("0.0.0.0", port), Handler).serve_forever()
