# Initial Research & Experiments — Index

Everything below was conducted around AI demand volume, engine behavior, sector signals, hospitality visibility, and scorecard design. Papers/decks are copied into `papers-and-decks/`; experiment plans into `plans/`.

---

## A. Prompt volume / AI demand (core research)

| Artifact | Location in this pack | Source on disk |
|---|---|---|
| Prompt Volume Estimation Research (FINAL) | [papers-and-decks/3_Prompt_Volume_Estimation_Research FINAL.pdf](./papers-and-decks/3_Prompt_Volume_Estimation_Research%20FINAL.pdf) | Downloads |
| Exp-1 Prompt Volume Estimation | [papers-and-decks/Exp-1__Prompt_Volume_Estimation_Research.pdf](./papers-and-decks/Exp-1__Prompt_Volume_Estimation_Research.pdf) | Downloads |
| Prompt Volume deck/PDF | [papers-and-decks/Prompt Volume.pdf](./papers-and-decks/Prompt%20Volume.pdf) | Downloads |
| AI Demand Estimation | [papers-and-decks/AI Demand Estimation.pdf](./papers-and-decks/AI%20Demand%20Estimation.pdf) | Downloads |
| AI Demand Estimation (updated DOCX) | [papers-and-decks/AI_Demand_Estimation_Updated.docx](./papers-and-decks/AI_Demand_Estimation_Updated.docx) | Downloads |
| Framework Demand Volume Comparison | [papers-and-decks/Framework_Demand_Volume_Comparison_Report.docx](./papers-and-decks/Framework_Demand_Volume_Comparison_Report.docx) | Downloads |
| Prompt Volume Confidence Plan (Sai) | [papers-and-decks/Prompt_Volume_Confidence_Plan_Sai.docx](./papers-and-decks/Prompt_Volume_Confidence_Plan_Sai.docx) | Downloads |
| Prompt Metrics Explainer | [papers-and-decks/PROMPT_METRICS_EXPLAINER.pdf](./papers-and-decks/PROMPT_METRICS_EXPLAINER.pdf) | Downloads |
| Algorithm FLOW writeup | [../volume-prediction/FLOW.md](../volume-prediction/FLOW.md) | `ai-demand-case2/FLOW.md` |

**Code experiments tied to this research**

| Experiment | Path |
|---|---|
| Overlap-discount aggregation | `Downloads/ai-demand-case2_overlap_discount` |
| Intent Match Score aggregation | `Downloads/ai-demand-case2_Intent_Match_Score` |
| Offline Analysis scripts | `Downloads/Analysis` |
| Case1 precursor | `Downloads/ai-demand-case1` |

Themes explored: SV vs ASV sensors, Bayesian fusion, calibration floors, fusion β, keyword extraction quality (LLM vs n-gram vs NER), intent rollup without double-counting, confidence/outliers (Pine Labs / Comviva style investigations).

---

## B. Engine & sector research plans (from Case2)

Copied from `ai-demand-case2/docs/research/`:

| Plan | File |
|---|---|
| Sector signal teardown (e-com vs hospitality vs SaaS) | [plans/sector_signal_teardown_plan.md](./plans/sector_signal_teardown_plan.md) |
| Sector source / citation mapping | [plans/sector_source_mapping_plan.md](./plans/sector_source_mapping_plan.md) |
| Engine differences (ChatGPT / Perplexity / Gemini / AIO / Claude) | [plans/engine_differences_plan.md](./plans/engine_differences_plan.md) |
| Live search vs parametric memory | [plans/engine_live_search_vs_memory_plan.md](./plans/engine_live_search_vs_memory_plan.md) |
| Freshness / canary pickup latency | [plans/engine_freshness_pickup_experiment_plan.md](./plans/engine_freshness_pickup_experiment_plan.md) |
| Hospitality shortlist + routing methodology | [plans/hospitality_shortlist_and_routing_metrics.md](./plans/hospitality_shortlist_and_routing_metrics.md) |
| Hospitality metrics package README | [plans/hospitality_metrics_README.md](./plans/hospitality_metrics_README.md) |

---

## C. Visibility / scorecard research

| Artifact | Location |
|---|---|
| AI Visibility Insights Metrics | [papers-and-decks/AI_Visibility_Insights_Metrics.pdf](./papers-and-decks/AI_Visibility_Insights_Metrics.pdf) |
| AI Demand Scorecards 2-page design | [papers-and-decks/AI_Demand_Scorecards_2_Page_Design_Doc.docx](./papers-and-decks/AI_Demand_Scorecards_2_Page_Design_Doc.docx) |
| Scorecard design / feasibility / prompt simplification | [../products/scorecards/](../products/scorecards/) |


---

## D. Suggested reading order for a new owner

1. [../volume-prediction/ALGORITHM.md](../volume-prediction/ALGORITHM.md)  
2. [../volume-prediction/FLOW.md](../volume-prediction/FLOW.md)  
3. `3_Prompt_Volume_Estimation_Research FINAL.pdf`  
4. `Prompt_Volume_Confidence_Plan_Sai.docx`  
5. Hospitality plan (if hospitality GTM continues)  
6. Scorecard feasibility + design (if sales scorecards continue)
