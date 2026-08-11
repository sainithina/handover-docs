# Zip & Send Checklist

Case2 source now lives in this repo at [`repos/ai-demand-case2/`](./repos/ai-demand-case2/) (no `runs/`, no `.env`). The `_zips/` folder was removed.

## Recommended email / share

| Package | Contents |
|---|---|
| **A — This repo** | Clone or zip `handover-docs` (includes Case2 under `repos/`) |
| **B — Production wiring (optional)** | Slim slice of `gravton-console` (DAGs + vendored case2 + scorecards) **or** full console |
| **C — Frontend (optional)** | `gravton-frontend` (exclude `node_modules`, `dist`, `.env`) |

```bash
# Zip this handover repo (already contains Case2)
cd /Users/sainithinartham/Downloads
zip -r handover-docs.zip handover-docs \
  -x "handover-docs/.git/*" \
  -x "handover-docs/**/.DS_Store" \
  -x "handover-docs/**/__pycache__/*"
```

Optional helper for other stacks (console/frontend experiments):

```bash
bash scripts/make_handover_zips.sh
```

---

## Do NOT email

| Item | Why |
|---|---|
| Any `.env` | Live secrets |
| `gravton-pem-file.pem` | SSH / infra key |
| Full `runs/` directories | Huge + may contain client data |
| Personal financial / identity PDFs | Not Gravton IP |

Transfer secrets via vault using [credentials/CREDENTIALS_CHECKLIST.md](./credentials/CREDENTIALS_CHECKLIST.md).
