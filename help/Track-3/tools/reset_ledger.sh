# Run with Git Bash by FULL PATH from Python (see mutate.py header).
cd /c/Users/Aksha/OneDrive/Desktop/PWC/SDLC/backend
set -a; . ./.env.test; set +a
uv run python -m alembic downgrade 0066_track3_owner_rows >/dev/null 2>&1 && uv run python -m alembic upgrade head >/dev/null 2>&1 && echo RESET_OK
