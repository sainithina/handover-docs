# Sai Nithin — Gravton Departure Handover Pack

**Date:** 2026-08-11  
**Owner leaving:** Sai Nithin (`sainithina@gravton.ai`)  
**Purpose:** Single pack to zip / email so the team can continue volume prediction, scorecards, research, and related products without tribal knowledge.

---

## Start here

| Priority | Doc | What it covers |
|---|---|---|
| **P0** | [volume-prediction/ALGORITHM.md](./volume-prediction/ALGORITHM.md) | Current AI demand / prompt-volume algorithm (most important) |
| **P0** | [repos/CODE_REPOS_TO_ZIP.md](./repos/CODE_REPOS_TO_ZIP.md) | Which local folders to zip + what to exclude |
| **P0** | [ZIP_AND_SEND_CHECKLIST.md](./ZIP_AND_SEND_CHECKLIST.md) | Exact zip commands + mail checklist |
| **P1** | [credentials/CREDENTIALS_CHECKLIST.md](./credentials/CREDENTIALS_CHECKLIST.md) | Where secrets live (names only — **do not email raw `.env`**) |
| **P1** | [products/PRODUCTS_BUILT.md](./products/PRODUCTS_BUILT.md) | Products built / launched / in progress |
| **P1** | [research/RESEARCH_INDEX.md](./research/RESEARCH_INDEX.md) | Initial research + experiments + papers |

---

## Folder layout

```text
sai-nithin-departure-handover/
├── README.md                          ← this file
├── ZIP_AND_SEND_CHECKLIST.md
├── volume-prediction/                 ← Case2 algorithm (P0)
│   ├── ALGORITHM.md                   ← handover narrative
│   ├── FLOW.md                        ← full pipeline writeup
│   ├── CASE2_README.md
│   └── README_CUSTOMER.md
├── repos/
│   └── CODE_REPOS_TO_ZIP.md
├── credentials/
│   └── CREDENTIALS_CHECKLIST.md       ← key names + locations only
├── research/
│   ├── RESEARCH_INDEX.md
│   ├── plans/                         ← experiment plans from case2
│   └── papers-and-decks/              ← PDFs / DOCX already copied in
├── products/
│   ├── PRODUCTS_BUILT.md
│   ├── scorecards/                    ← design + feasibility docs
│   ├── product-brain/                 ← module map / glossary
│   └── gravton-l2-social-frontend-handover.md
└── scripts/
    └── make_handover_zips.sh          ← builds clean zips for email
```

---

## Critical distinction: research Case2 vs production Case2

| Tree | Role |
|---|---|
| `Downloads/ai-demand-case2` | **Richest research/dev** algorithm checkout (topic rollups, BGE scorers, hospitality metrics). **Zip this for the algorithm.** |
| `gravton-console/airflow/dags/repos/ai-demand-case2` | **Production-vendored** engine used by Airflow `prompt_volume` / `keyword_volume` DAGs. Slightly behind research (intent method default differs). |

See [volume-prediction/ALGORITHM.md](./volume-prediction/ALGORITHM.md) for the gap and how they connect.

---

## Pre-built zips (ready to attach)

Generated under [`_zips/`](./_zips/) (`.env` and `runs/` excluded):

| Zip | Contents |
|---|---|
| `01-sai-handover-docs-*.zip` | This entire docs pack (~2.4 MB) |
| `02-ai-demand-case2-algorithm-*.zip` | **P0** Case2 source (~0.6 MB compressed) |
| `03-case2-experiments-*.zip` | Overlap-discount + Intent-Match forks (~25 MB) |

To also zip console/frontend:

```bash
INCLUDE_CONSOLE=1 INCLUDE_FRONTEND=1 \
  OUT=/Users/sainithinartham/Downloads/gravton-docs/sai-nithin-departure-handover/_zips \
  bash scripts/make_handover_zips.sh
```

---

## Security rule (read before emailing)

1. **Never** put live API keys, DB passwords, PEM files, or `.env` contents into a zip you email.  
2. Transfer secrets via a password manager / secure channel using [credentials/CREDENTIALS_CHECKLIST.md](./credentials/CREDENTIALS_CHECKLIST.md).  
3. Local secret files that must **stay out of email zips**:
   - `gravton-console/.env`
   - `ai-demand-case2/.env`
   - `gravton-frontend/.env`
   - `Downloads/gravton-pem-file.pem`
   - Airflow password dump backups
