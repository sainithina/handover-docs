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

---

## P1 — Core platform (console)

Groupings from `.env.example` (hand over values separately):

### Databases & Airflow

- `DB_*`, `DB_DIRECT_*`
- `AIRFLOW_DB_*`, `AIRFLOW_USERNAME` / `AIRFLOW_PASSWORD`
- `AIRFLOW_WWW_USER_*`
- `AIRFLOW_BASE_URL`, `DJANGO_BASE_URL`, `FRONTEND_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

### AI providers

- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, …
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`
- `GOOGLE_DEV_API_KEY`

### Data / crawl / cloud

- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`
- `APIFY_API_TOKEN` (+ `AIRFLOW_VAR_APIFY_API_TOKEN`)
- `AWS_S3_ACCESS_KEY_ID`, `AWS_S3_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_STORAGE_BUCKET_NAME`, region
- `CRAWL_SNAPSHOT_S3_BUCKET`, `ECOMMERCE_S3_BUCKET`

### Auth / crypto

- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_SECRET`
- `ENCRYPTION_KEY`
- Frontend: `VITE_GOOGLE_OAUTH_CLIENT_ID`

### Observability

- `LANGFUSE_*` init keys / passwords / project ids

### Host

- `CURRENT_HOST_DOMAIN`, `CURRENT_HOST_IP`

Full key list: run `rg -o '^[A-Z][A-Z0-9_]+' gravton-console/.env.example` on the machine receiving the console repo.

---

## P1 — Frontend

| Variable | Purpose |
|---|---|
| `VITE_AUTH_BASE_URL` | Auth API path |
| `VITE_DEV_PROXY_TARGET` | Local Django proxy |
| `VITE_GOOGLE_OAUTH_CLIENT_ID` | Google login |
| `VITE_DEV_SKIP_API` | Dev stub flag |

---

## Accounts / access to transfer (human checklist)

Ask IT / founders to confirm ownership transfer for:

- [ ] DataForSEO account (billing + API login)  
- [ ] OpenRouter account / credits  
- [ ] AWS IAM user/keys used by local/prod  
- [ ] Apify  
- [ ] Google OAuth client (Cloud Console)  
- [ ] Langfuse project  
- [ ] Anthropic / Gemini / HuggingFace tokens if personal  
- [ ] GitHub org membership (console + frontend remotes)  
- [ ] Production / staging SSH (the `.pem` file)  
- [ ] Airflow UI admin  
- [ ] Supabase / other MCP-linked projects if any were Sai-owned  
- [ ] `app.gravton.ai` admin access for scorecard delivery  

---

## Suggested secure transfer procedure

1. Recipient creates empty vault entries matching the checklist above.  
2. Sai fills values **in the vault UI** (or screen-share once) — not Slack / email.  
3. Rotate: DataForSEO password, OpenRouter key, AWS keys, PEM, OAuth secret, DB passwords that Sai knew.  
4. Delete local copies of `.env` / `.pem` from personal machine after confirmation.  
5. Keep this markdown checklist in git/docs; never commit filled values.
