# Credentials Checklist (names only — no secret values)

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
