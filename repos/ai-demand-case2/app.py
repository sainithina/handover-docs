"""Gradio app for Case 2: AI Demand Estimation (SV + ASV Bayesian Fusion)."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import gradio as gr

from dotenv import load_dotenv
load_dotenv()

from case2_demand.config import Settings, resolve_run_context
from case2_demand.pipeline import generate_intent_clusters_step, generate_prompts_step, load_company_profile
from case2_demand.profile_generator import generate_profile_from_brand
from case2_demand.util.io import iter_jsonl, write_json

# Import CLI internals for running pipeline
from case2_demand.cli import _run_all_with_calibration, _prompts_dir

MAX_JSONL_PREVIEW = 500


def _load_jsonl_preview(path: Path, max_lines: int = MAX_JSONL_PREVIEW) -> str:
    if not path.exists():
        return ""
    rows = []
    for i, row in enumerate(iter_jsonl(path)):
        if i >= max_lines:
            rows.append({"_truncated": f"... {path.name} has more rows (showing first {max_lines})"})
            break
        rows.append(row)
    return json.dumps(rows, indent=2, ensure_ascii=False)


def run_pipeline(brand_name: str, profile_file, n_intents: int, n_prompts: int, progress=gr.Progress()):
    """Run full Case 2 pipeline with calibration. Use brand name (auto-generate profile) or profile file."""
    company = None

    if brand_name and brand_name.strip():
        try:
            progress(0.05, desc="Generating company profile from brand...")
            settings = Settings()
            company = generate_profile_from_brand(brand_name.strip(), settings)
        except Exception as e:
            import traceback
            err = f"❌ Failed to generate profile for '{brand_name}':\n```\n{traceback.format_exc()}\n```"
            return (err, "", "", "", "", "", "", "", "", "", "", "", "")

    elif profile_file is not None:
        try:
            path = getattr(profile_file, "name", None) or getattr(profile_file, "path", None) or str(profile_file)
            company = load_company_profile(Path(path))
        except Exception as e:
            return (f"❌ Invalid company profile: {e}", "", "", "", "", "", "", "", "", "", "", "", "")

    else:
        return (
            "❌ Enter a brand name (e.g. Agnost.ai, Coditas) OR upload a company profile JSON.",
            "", "", "", "", "", "", "", "", "", "", "", "",
        )

    import os
    from datetime import datetime, timezone
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.environ["CASE2_RUN_ID"] = run_id

    settings = Settings()
    ctx = resolve_run_context(settings)
    ctx.company_profile_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(ctx.company_profile_path, company.model_dump())

    intent_prompt_path = _prompts_dir() / "intent_cluster_generation_system.txt"
    batch_prompt_path = _prompts_dir() / "prompt_batch_for_intent_system.txt"

    try:
        progress(0.1, desc="Generating intent clusters...")
        plan = generate_intent_clusters_step(
            ctx=ctx,
            company=company,
            settings=settings,
            prompt_path=intent_prompt_path,
            n_intents=n_intents if n_intents > 0 else None,
        )

        progress(0.3, desc="Generating prompts...")
        prompts_list = generate_prompts_step(
            ctx=ctx,
            company=company,
            intent_plan=plan,
            settings=settings,
            n_prompts_per_intent=n_prompts,
            prompt_path=batch_prompt_path,
        )

        prompt_items = [
            {
                "prompt": p.prompt,
                "prompt_id": p.prompt_id,
                "intent_cluster_id": p.intent_cluster_id,
                "intent_cluster_name": p.intent_cluster_name,
            }
            for p in prompts_list
        ]

        progress(0.4, desc="Extracting keywords, fetching SV+ASV, calibrating...")
        args = type("Args", (), {
            "location": 2840,
            "language": "en",
            "with_calibration": True,
        })()
        asyncio.run(_run_all_with_calibration(
            prompt_items=prompt_items,
            company_name=company.company_name,
            ctx=ctx,
            settings=settings,
            args=args,
        ))

        if not (ctx.run_dir / "calibrated.json").exists():
            return (
                "❌ Calibration did not complete. Ensure `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` are set in `.env`.",
                "", "", "", "", "", "", "", "", "", "", "", "",
            )

        progress(1.0, desc="Done!")

    except Exception as e:
        import traceback
        err = f"❌ Pipeline error:\n```\n{traceback.format_exc()}\n```"
        return (err, "", "", "", "", "", "", "", "", "", "", "", "")

    # Build outputs
    metrics_data = json.loads(ctx.metrics_path.read_text()) if ctx.metrics_path.exists() else {}
    total_vol = metrics_data.get("total_estimated_volume", 0)
    num_intents = len(metrics_data.get("intent_cluster_estimates", []))
    num_prompts = metrics_data.get("total_prompts", 0)
    num_keywords = metrics_data.get("total_keywords", 0)

    summary = f"""## Summary
- **Company:** {company.company_name}
- **Run ID:** {ctx.run_id}
- **Intent clusters:** {num_intents}
- **Total prompts:** {num_prompts}
- **Total keywords:** {num_keywords}
- **Total estimated volume:** {total_vol:,.0f} units/month
- **Calibration:** ρ (per keyword), η (μ_η, σ_η) from all keywords
"""

    intent_estimates_data = json.loads(ctx.intent_estimates_path.read_text()) if ctx.intent_estimates_path.exists() else []
    rows = [
        "| Intent Cluster | Prompts | Est. Volume | 90% CI |",
        "|----------------|---------|-------------|--------|",
    ]
    for e in intent_estimates_data:
        ci = f"[{e['interval_90'][0]:,.0f}, {e['interval_90'][1]:,.0f}]"
        rows.append(f"| {e['intent_cluster_name']} | {e['num_prompts']} | {e['Y_median']:,.0f} | {ci} |")
    table_md = "\n".join(rows)

    insights_md = ctx.insights_path.read_text(encoding="utf-8") if ctx.insights_path.exists() else ""
    metrics_json = json.dumps(metrics_data, indent=2)
    company_profile_json = json.dumps(company.model_dump(), indent=2, ensure_ascii=False)
    intent_plan_json = ctx.intent_cluster_plan_path.read_text(encoding="utf-8") if ctx.intent_cluster_plan_path.exists() else ""
    synthetic_prompts_json = _load_jsonl_preview(ctx.synthetic_prompts_path)
    keyword_extractions_json = _load_jsonl_preview(ctx.keyword_extractions_path)
    sv_data_json = _load_jsonl_preview(ctx.sv_data_path)
    asv_data_json = _load_jsonl_preview(ctx.asv_data_path)
    prompt_estimates_json = _load_jsonl_preview(ctx.prompt_estimates_path)
    intent_estimates_json = ctx.intent_estimates_path.read_text(encoding="utf-8") if ctx.intent_estimates_path.exists() else ""

    calibrated_json = ""
    if (ctx.run_dir / "calibrated.json").exists():
        calibrated_json = (ctx.run_dir / "calibrated.json").read_text(encoding="utf-8")

    return (
        summary,
        table_md,
        insights_md,
        metrics_json,
        company_profile_json,
        intent_plan_json,
        synthetic_prompts_json,
        keyword_extractions_json,
        sv_data_json,
        asv_data_json,
        prompt_estimates_json,
        intent_estimates_json,
        calibrated_json,
    )


def build_ui():
    try:
        theme = gr.themes.Soft(
            primary_hue="teal",
            secondary_hue="slate",
            font=gr.themes.GoogleFont("Inter"),
            font_mono=gr.themes.GoogleFont("JetBrains Mono"),
            radius_size="lg",
            spacing_size="lg",
        )
    except (AttributeError, TypeError):
        theme = gr.themes.Soft(primary_hue="teal", secondary_hue="slate")

    css = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .gradio-container { max-width: 1400px !important; margin: 0 auto !important; padding: 1.5rem !important;
        background: linear-gradient(180deg, #f0fdfa 0%, #ecfeff 100%) !important;
        min-height: 100vh !important; border-radius: 16px !important; }
    .header-card {
        background: linear-gradient(135deg, #0d9488 0%, #14b8a6 50%, #2dd4bf 100%);
        border-radius: 16px; padding: 2rem; margin-bottom: 1.5rem;
        box-shadow: 0 10px 40px -10px rgba(13, 148, 136, 0.4);
    }
    .header-card h1 { color: white !important; font-size: 1.75rem !important; font-weight: 700 !important; margin: 0 !important; }
    .header-card p { color: rgba(255,255,255,0.9) !important; font-size: 0.95rem !important; margin: 0.5rem 0 0 0 !important; }
    .input-panel {
        background: var(--block-background-fill, #fff);
        border-radius: 12px; padding: 1.25rem;
        border: 1px solid var(--block-border-color, #e5e7eb);
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .tabs-container > div { border-radius: 12px !important; }
    .primary-btn { font-weight: 600 !important; padding: 0.75rem 1.5rem !important; }
    """

    with gr.Blocks(title="AI Demand Estimation (Case 2)") as demo:
        with gr.Group(elem_classes="header-card"):
            gr.Markdown(
                "# AI Demand Estimation (Case 2)\n"
                "SV + ASV Bayesian fusion: intent clusters → prompts → keywords → SV+ASV fetch → calibrate ρ,η → estimate."
            )

        with gr.Row():
            with gr.Column(scale=1, elem_classes="input-panel"):
                brand_name = gr.Textbox(
                    label="Brand / Company Name",
                    placeholder="e.g. Agnost.ai, Coditas, Angel One",
                    info="Enter name → profile is auto-generated, then full pipeline runs",
                )
                profile_upload = gr.File(label="OR upload Company Profile (JSON)", file_types=[".json"])
                gr.Examples(examples=[["Agnost.ai"], ["Coditas"]], inputs=brand_name, label="Try these brands")
                n_intents = gr.Slider(minimum=0, maximum=20, value=2, step=1, label="Number of intent clusters (0 = auto)")
                n_prompts = gr.Slider(minimum=1, maximum=100, value=2, step=1, label="Prompts per intent")
                run_btn = gr.Button("Run Pipeline (with Calibration)", variant="primary", elem_classes="primary-btn")

        with gr.Tabs(elem_classes="tabs-container"):
            with gr.Tab("Summary"):
                summary_out = gr.Markdown()
            with gr.Tab("Intent Estimates"):
                table_out = gr.Markdown()
            with gr.Tab("Insights"):
                insights_out = gr.Markdown()
            with gr.Tab("Company Profile"):
                company_profile_out = gr.Code(language="json", label="Company profile (JSON)")
            with gr.Tab("Intent Cluster Plan"):
                intent_plan_out = gr.Code(language="json", label="Intent clusters (JSON)")
            with gr.Tab("Synthetic Prompts"):
                synthetic_prompts_out = gr.Code(language="json", label="Prompts per intent (JSONL)")
            with gr.Tab("Keyword Extractions"):
                keyword_extractions_out = gr.Code(language="json", label="Keywords per prompt (JSONL)")
            with gr.Tab("SV Data"):
                sv_data_out = gr.Code(language="json", label="Classic search volume (JSONL)")
            with gr.Tab("ASV Data"):
                asv_data_out = gr.Code(language="json", label="AI search volume (JSONL)")
            with gr.Tab("Prompt Estimates"):
                prompt_estimates_out = gr.Code(language="json", label="Demand per prompt (JSONL)")
            with gr.Tab("Intent Estimates (JSON)"):
                intent_estimates_out = gr.Code(language="json", label="Demand per intent (JSON)")
            with gr.Tab("Calibration"):
                calibrated_out = gr.Code(language="json", label="Calibrated ρ, η (JSON)")
            with gr.Tab("Metrics (JSON)"):
                metrics_out = gr.Code(language="json", label="Full metrics")

        run_btn.click(
            fn=run_pipeline,
            inputs=[brand_name, profile_upload, n_intents, n_prompts],
            outputs=[
                summary_out,
                table_out,
                insights_out,
                metrics_out,
                company_profile_out,
                intent_plan_out,
                synthetic_prompts_out,
                keyword_extractions_out,
                sv_data_out,
                asv_data_out,
                prompt_estimates_out,
                intent_estimates_out,
                calibrated_out,
            ],
        )

        gr.Markdown(
            "---\n"
            "**Requirements:** Set `OPENROUTER_API_KEY` in `.env` for intent/prompt generation. "
            "Set `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` for real SV+ASV."
        )

    return demo, theme, css


if __name__ == "__main__":
    demo, theme, css = build_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7862,
        share=True,
        theme=theme,
        css=css,
    )
