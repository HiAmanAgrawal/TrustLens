# scripts/

Developer convenience scripts. Anything a contributor runs more than twice
should live here so it's discoverable and reviewable.

## Planned scripts

| Script              | Purpose                                                          |
| ------------------- | ---------------------------------------------------------------- |
| `dev.sh`            | Start FastAPI + frontend together with the right env loaded      |
| `lint.sh`           | Run ruff on backend + services, eslint on frontend               |
| `seed.py`           | Insert mock data into the dev DB so dashboards have something to show |
| `whatsapp-tunnel.sh`| Start an `ngrok` tunnel and print the webhook URL to register    |

## Conventions

- Bash scripts: `set -euo pipefail` at the top, exit non-zero on any failure.
- Python scripts: `if __name__ == "__main__":` guard, use `argparse` (no `sys.argv` parsing).
- Document each script's flags in its header comment.
