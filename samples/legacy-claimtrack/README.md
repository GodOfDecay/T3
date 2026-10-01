# ClaimTrack Lite — a small, REAL legacy system for Track 3 (local development only)

An insurer's claims system as it might have been written years ago: **Python 2.7, standard library
only**, SQLite, a fixed-width bank file in Windows-1252. It exists so the Code Modernization agents have
something that actually runs — Equivalence Testing records what it does before anything is migrated.

| Module | Folder | What it does |
|---|---|---|
| Claims API | `claims-api/` | `GET /api/claims/{id}`, `POST /api/claims/{id}/settle` (asks the external fraud-score service, then pays `amount × coverage` rounded the Python 2 way) |
| Settlement batch | `settlement-batch/` | Writes the bank payment file `BANKPAY_<date>.txt` (fixed width, cp1252) for settled claims |
| Database | `db/` | Schema and **synthetic** seed data (`Test Claimant 001` …). No real person is in it |

Deliberate legacy behaviour a migration must keep (or change only by ADR):
- **Rounding** — Python 2's `round()` rounds halves away from zero (`round(0.125, 2) == 0.13`);
  Python 3 rounds to even (`0.12`). Claims CLM-0004 and CLM-0007 hit it.
- **Encoding** — the bank file is cp1252 (`Zoë` is one byte), fixed width, amounts in cents.
- **Nondeterminism** — every response carries `generatedAt`/`settledAt` and a `requestId`; the bank
  file header carries the generation time. Equivalence Testing finds these by running twice.

`sdlc-sandbox.json` tells the platform's sandbox how to build, seed, start and exercise it; `stubs/`
holds the canned fraud-score answers (the sandbox has no internet); `scenarios/` the recorded inputs.

Run it by hand: `docker build -t claimtrack-lite . && docker run --rm -p 8080:8080 claimtrack-lite`.
