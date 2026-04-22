#!/usr/bin/env bash
# Start the backend dev server using the venv's uvicorn directly.
#
# Why not just `uvicorn app.main:app --reload`?
#   On machines with pyenv (or any PATH-shimming Python manager) the bare
#   `uvicorn` command resolves to the shim, NOT the .venv binary, even after
#   `source .venv/bin/activate`. The shim points at a different Python (often
#   3.9), which doesn't have the project's dependencies installed -- the
#   server fails on import with a confusing `ModuleNotFoundError`.
#
# Calling `.venv/bin/uvicorn` by absolute path bypasses every shim.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="${REPO_ROOT}/backend/.venv/bin"

if [[ ! -x "${VENV_BIN}/uvicorn" ]]; then
  echo "error: ${VENV_BIN}/uvicorn not found." >&2
  echo "Create the venv first:" >&2
  echo "  cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

cd "${REPO_ROOT}/backend"
exec "${VENV_BIN}/uvicorn" app.main:app --reload "$@"
