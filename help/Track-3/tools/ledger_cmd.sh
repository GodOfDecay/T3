# Run with Git Bash by FULL PATH from Python (see mutate.py header).
#!/bin/bash
cd /c/Users/Aksha/OneDrive/Desktop/PWC/SDLC/backend
set -a; . ./.env.test; set +a
uv run python -m alembic downgrade 0066_track3_owner_rows >/dev/null 2>&1 || exit 3
uv run python -m alembic upgrade head >/dev/null 2>&1 || exit 4
uv run python -m pytest tests/modernization_common/test_ledger.py -q -p no:cacheprovider; echo "PYTEST_EXIT=$?"; exit 0
