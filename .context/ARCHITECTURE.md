# Architecture

## Directory Structure
```
.
├── main.py
├── state.json
├── pyproject.toml
└── .github/
    └── workflows/
        └── daily_run.yml
```

## Data Flow
1. Fetch CSV from `AmplifyWeb.40XL.XL_SWAP_Holdings.csv`.
2. Parse CSV for the targeted tickers (`MAPS`, `GRWG`).
3. Load local state (`state.json`).
4. Compare fetched data with local state.
5. If changes are detected, post to Discord via webhook.
6. Commit back `state.json` via GitHub actions to preserve state.
