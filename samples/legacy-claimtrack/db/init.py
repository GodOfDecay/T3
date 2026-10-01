# -*- coding: utf-8 -*-
"""Create the ClaimTrack database from the schema and the synthetic seed (Python 2.7)."""
import io
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("CLAIMTRACK_DB", "/data/claimtrack.db")

if os.path.exists(DB):
    os.remove(DB)
conn = sqlite3.connect(DB)
for name in ("schema.sql", "seed.sql"):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:
        conn.executescript(f.read())
conn.commit()
conn.close()
print "database ready: %s" % DB
