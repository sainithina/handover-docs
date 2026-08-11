# Credentials Checklist (names only — no secret values)

**Policy for this handover:** document *where* credentials live and *which keys* matter.  
**Never** paste live values into this folder, into email, or into a zip.

Transfer actual secrets via **1Password / Bitwarden / company vault**, then rotate anything that was tied to Sai’s personal login.

---

## Local files that currently hold secrets (do not email)

| File | Contains |
|---|---|
| `/Users/sainithinartham/Downloads/gravton-console/.env` | Full stack: DB, Airflow, LLM keys, DataForSEO, AWS, OAuth, Langfuse, … |
| `/Users/sainithinartham/Downloads/ai-demand-case2/.env` | OpenRouter + DataForSEO for Case2 |
| `/Users/sainithinartham/Downloads/gravton-frontend/.env` | Frontend proxy / OAuth client id |
| `/Users/sainithinartham/Downloads/gravton-pem-file.pem` | Infra SSH / PEM — **critical; hand over out-of-band, then revoke** |
| `gravton-console_simple_auth_manager_passwords.json.generated.bak` | Generated Airflow passwords — do not distribute |

Templates (safe to share):

- `gravton-console/.env.example`
- `ai-demand-case2/.env.example`
- `gravton-frontend/.env.example`

---

## P0 — Volume prediction (Case2)

| Secret / variable | Where used | Notes |
|---|---|---|
| `DATAFORSEO_LOGIN` | Case2 + console | SV / ASV / history |
| `DATAFORSEO_PASSWORD` | Case2 + console | |
| `OPENROUTER_API_KEY` | Case2 LLM keywords + console LLMs | |
| `AI_DEMAND_CASE2_HOME` | Airflow | Path override to Case2 tree |
| Airflow Variable `ai_demand_case2_dataforseo_login` | Prod DAGs | Mirror of DataForSEO login |
| Airflow Variable `ai_demand_case2_dataforseo_password` | Prod DAGs | |
| Airflow Variable `ai_demand_case2_openrouter_api_key` | Prod DAGs | |
| `CASE2_*` hyperparameter env vars | Optional overrides | Not secrets, but config |

Case2 `.env.example` minimum:

```bash
OPENROUTER_API_KEY=
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
```
