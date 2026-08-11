# Code Repos to Zip

## Already in this handover repo

| Path in handover-docs | What it is |
|---|---|
| [`repos/ai-demand-case2/`](./ai-demand-case2/) | **P0** Case2 volume algorithm source (copied without `runs/`, `.env`) |

Local absolute paths below are on Sai’s machine if you need the originals or other stacks. Prefer **git remotes** when the recipient already has GitHub access.

## Tier 1 — must send (algorithm + products you own)

| # | Local path | Git? | Why | Zip notes |
|---|---|---|---|---|
| 1 | `repos/ai-demand-case2/` **(in this repo)** or `/Users/sainithinartham/Downloads/ai-demand-case2` | in handover-docs | **P0 volume algorithm** + hospitality metrics + research plans | Already included here; local original still has large `runs/` |
| 2 | `/Users/sainithinartham/Downloads/gravton-console` | yes | Production backend, Airflow, vendored Case2, scorecards, demand map, agents | Exclude `.env`, `.venv`, `gravton_dump.sql`; ~1.9G full |
| 3 | `/Users/sainithinartham/Downloads/gravton-frontend` | yes | Scorecard-ops, demand-map, citations, agents UI | Exclude `node_modules/`, `dist/`, `.env` |
| 4 | `/Users/sainithinartham/Downloads/gravton-docs` | no | This handover pack + original scorecard docs | Small; send whole folder |

### Production Case2 slice inside console (if not sending full console)

Must include at least:

```text
gravton-console/airflow/dags/prompt_volume_dag.py
gravton-console/airflow/dags/keyword_volume_dag.py
gravton-console/airflow/dags/utils/case2_gravton_bridge.py
gravton-console/airflow/dags/utils/prompt_volume_gravton_bridge.py
gravton-console/airflow/dags/utils/keyword_volume_utils.py
gravton-console/airflow/dags/repos/ai-demand-case2/   # src + pyproject
gravton-console/backend_src/apps/intent_core/         # Case2DemandRun, prompt_volume
gravton-console/backend_src/apps/scorecards/          # scorecard product
gravton-console/airflow/dags/app/synteticprompt/lite_pipeline.py
```

---

## Tier 2 — experiments / history (send if they want the full research trail)

| Path | Why |
|---|---|
| `/Users/sainithinartham/Downloads/ai-demand-case2_overlap_discount` | Overlap-discount / alternate aggregators experiment |
| `/Users/sainithinartham/Downloads/ai-demand-case2_Intent_Match_Score` | Intent Match Score aggregation experiment (large `runs/` — exclude) |
| `/Users/sainithinartham/Downloads/ai-demand-case1` | Earlier Case1 lineage |
| `/Users/sainithinartham/Downloads/ai-demand-case2-api` | Thin API wrapper packaging |
| `/Users/sainithinartham/Downloads/Analysis` | Offline volume/overlap studies |
| `/Users/sainithinartham/Downloads/main/prompt-volume-estimation` | Older packaging snapshot |
| `/Users/sainithinartham/Downloads/refactoring/prompt-volume-estimation` | Refactor snapshot |
| `/Users/sainithinartham/Downloads/gravton-backend` | Older/smaller backend tree (uncertain vs console — only if needed) |

---

## Tier 3 — sample deliverables (optional, client-facing artifacts)

Under `Downloads/` (not all copied into this docs pack):

- `Approach 1 - Client Specific.html`, `Approach 2 - Industry.html`
- `scorecard-*-gravton-ai.pdf`, `scorecard-4-our-habitas*.pdf`, xlsx siblings
- Pine Labs / Comviva prompt analysis PDFs (client work samples)

Research papers already copied into `../research/papers-and-decks/`.

---

## Do not zip for Gravton handover

- `DriveSafe` and academic / personal projects  
- Personal financial / identity documents  
- Docker installers / IDE dmgs  
- AthenaHQ CSVs (competitive research — confirm with managers before sharing)  
- Any `.pem`, `.env`, password JSON backups  

---

## Remote repos (if GitHub org access remains)

Confirm with team which remotes are canonical (names may differ slightly):

- Gravton console / backend monorepo  
- Gravton frontend  
- Case2 may only exist as the vendored tree inside console + Sai’s local research checkout — **do not assume a separate public Case2 remote exists**

If GitHub access will be revoked on last day: **zip Tier 1 before access ends**.
