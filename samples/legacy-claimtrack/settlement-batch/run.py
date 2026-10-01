# -*- coding: utf-8 -*-
"""Nightly settlement batch — writes the bank payment file (Python 2.7).

BANKPAY_<yyyymmdd>.txt, Windows-1252, fixed width:
  H<generated yyyymmddHHMMSS><count 6>
  D<claim id 10><payee 30><amount in cents 12>
  T<total cents 14>
"""
import datetime
import io
import os
import sqlite3
import sys

DB = os.environ.get("CLAIMTRACK_DB", "/data/claimtrack.db")
OUT = os.environ.get("CLAIMTRACK_OUT", "/data/out")


def cents(value):
    return int(round(value * 100))


def main(argv):
    run_date = argv[argv.index("--date") + 1] if "--date" in argv else datetime.date.today().isoformat()
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT id, claimant, payout FROM claims WHERE status = 'settled' ORDER BY id").fetchall()
    conn.close()
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    lines = [u"H%s%06d" % (datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"), len(rows))]
    total = 0
    for claim_id, claimant, paid in rows:
        amount = cents(paid)
        total += amount
        lines.append(u"D%-10s%-30s%012d" % (claim_id, claimant[:30], amount))
    lines.append(u"T%014d" % total)
    path = os.path.join(OUT, "BANKPAY_%s.txt" % run_date.replace("-", ""))
    with io.open(path, "w", encoding="cp1252", newline="\r\n") as f:
        f.write(u"\n".join(lines) + u"\n")
    print "wrote %s (%d payments)" % (path, len(rows))


if __name__ == "__main__":
    main(sys.argv)
