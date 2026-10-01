CREATE TABLE claims (
    id            TEXT PRIMARY KEY,
    claimant      TEXT NOT NULL,
    amount        REAL NOT NULL,
    coverage_rate REAL NOT NULL,
    status        TEXT NOT NULL,
    payout        REAL
);
