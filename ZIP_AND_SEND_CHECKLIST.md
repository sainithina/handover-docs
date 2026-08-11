# Zip & Send Checklist

Use this when packaging code + docs for email handoff.

## Recommended email packages

Send **2–3 attachments** (or a shared drive link if mail size limits bite):

| Package | Contents | Approx size after clean zip |
|---|---|---|
| **A — Docs pack (this folder)** | `gravton-docs/sai-nithin-departure-handover/` | ~3 MB |
| **B — Volume algorithm (P0)** | Clean `ai-demand-case2` (no `runs/`, no `.env`) | ~tens of MB |
| **C — Production wiring** | Slim slice of `gravton-console` (DAGs + vendored case2 + scorecards app) **or** full console if recipient needs entire stack | full console ~1.9 GB; slim zip much smaller |
| **Optional D** | `gravton-frontend` (exclude `node_modules`, `dist`) | medium |

Run the helper:

```bash
bash /Users/sainithinartham/Downloads/gravton-docs/sai-nithin-departure-handover/scripts/make_handover_zips.sh
```

Zips land in `~/Downloads/gravton-handover-zips/` by default.

---

## Manual zip commands (if you prefer)

```bash
OUT=~/Downloads/gravton-handover-zips
mkdir -p "$OUT"

# A) Docs
cd /Users/sainithinartham/Downloads/gravton-docs
zip -r "$OUT/01-sai-handover-docs.zip" sai-nithin-departure-handover

# B) Volume algorithm — EXCLUDE runs + secrets + caches
cd /Users/sainithinartham/Downloads
zip -r "$OUT/02-ai-demand-case2-algorithm.zip" ai-demand-case2 \
  -x "ai-demand-case2/runs/*" \
  -x "ai-demand-case2/hospitality_metrics/runs/*" \
  -x "ai-demand-case2/.env" \
  -x "ai-demand-case2/**/__pycache__/*" \
  -x "ai-demand-case2/**/.DS_Store" \
  -x "ai-demand-case2/**/*.pyc"

# C) Experiment forks (optional)
zip -r "$OUT/03-case2-experiments.zip" \
  ai-demand-case2_overlap_discount \
  ai-demand-case2_Intent_Match_Score \
  -x "*/runs/*" -x "*/.env" -x "*/**/__pycache__/*"
```

For **gravton-console** / **gravton-frontend**, prefer a clean clone or:

```bash
# Console — exclude huge/local junk; still large because of .git + egg-info + dumps
cd /Users/sainithinartham/Downloads
zip -r "$OUT/04-gravton-console.zip" gravton-console \
  -x "gravton-console/.env" \
  -x "gravton-console/.venv/*" \
  -x "gravton-console/**/__pycache__/*" \
  -x "gravton-console/**/.pytest_cache/*" \
  -x "gravton-console/gravton_dump.sql"

cd /Users/sainithinartham/Downloads
zip -r "$OUT/05-gravton-frontend.zip" gravton-frontend \
  -x "gravton-frontend/.env" \
  -x "gravton-frontend/node_modules/*" \
  -x "gravton-frontend/dist/*" \
  -x "gravton-frontend/.tanstack/*"
```

If email rejects large zips: upload B/C/D to Google Drive / S3 and put the link in the mail; attach package A always.

---

## Mail body template

```text
Subject: Sai Nithin departure handover — volume algorithm + docs

Hi team,

Attached / linked:

1) sai-nithin-departure-handover docs (algorithm writeup, repo list, research, products)
2) ai-demand-case2 source (volume prediction — P0; runs/ and .env excluded)
3) [optional] gravton-console / frontend clean zips

Start with:
  sai-nithin-departure-handover/README.md
  sai-nithin-departure-handover/volume-prediction/ALGORITHM.md

Credentials are NOT in the zip. Use the checklist in
  credentials/CREDENTIALS_CHECKLIST.md
and transfer keys via 1Password / secure channel.

Thanks,
Sai
```

---

## Do NOT email

| Item | Why |
|---|---|
| Any `.env` | Live secrets |
| `gravton-pem-file.pem` | SSH / infra key |
| `gravton-console_simple_auth_manager_passwords.json.generated.bak` | Passwords |
| Full `runs/` directories | Huge + may contain client data |
| Personal financial / identity PDFs in Downloads | Not Gravton IP |

---

## After sending

- [ ] Confirm recipient can unzip package B and run `case2 dry-run`
- [ ] Confirm they know prod path: `gravton-console` → Airflow `prompt_volume` DAG
- [ ] Rotate any personal API keys that were shared into company accounts
- [ ] Hand over DataForSEO / OpenRouter account ownership if keys were under your login
