"""OpenAI-compatible LLM client for intent clusters and prompt generation.

Uses OpenRouter by default with DeepSeek R1 (deepseek/deepseek-r1).
Works with any OpenAI-compatible API (OpenRouter, DeepSeek direct, etc.).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.schemas import CompanyProfile, IntentCluster, IntentClusterPlan, KeywordWithImportance


class PromptBatchResponse(BaseModel):
    prompts: List[str]


class KeywordExtractionResponse(BaseModel):
    keywords: List[str]


class KeywordExtractionItem(BaseModel):
    prompt: str
    keywords: List[str]


class KeywordExtractionBatchResponse(BaseModel):
    extractions: List[KeywordExtractionItem]


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_think_tags(text: str) -> str:
    """Remove DeepSeek R1 reasoning blocks before parsing JSON."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict:
    """Extract JSON from text, handling markdown and think tags."""
    text = _strip_think_tags(text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try ```json ... ``` or content after ```json (handles truncated)
    for pattern in [r"```(?:json)?\s*\n?(.*?)```", r"```(?:json)?\s*\n?(.*)"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            raw = match.group(1).strip()
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
    # Try to find {...} in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        raw = match.group(0)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                import json_repair
                return json_repair.loads(raw)
            except Exception:
                pass
    raise ValueError(f"Could not extract valid JSON from response: {text[:500]}...")


def _extract_partial_prompts(text: str) -> List[str]:
    """Salvage prompts from truncated JSON."""
    prompts: List[str] = []
    match = re.search(r'"prompts"\s*:\s*\[', text, re.IGNORECASE)
    if not match:
        return prompts
    after = text[match.end() :]
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', after):
        s = m.group(1)
        if s and len(s) < 500:
            prompts.append(s)
    return prompts


def _prefer_plain_json(model: str) -> bool:
    """Free / router models often hang or truncate on strict JSON schema."""
    m = (model or "").lower()
    return m == "openrouter/free" or m.endswith(":free") or "free" in m


_PROMPT_STOP = {
    "a", "an", "the", "and", "or", "to", "for", "of", "in", "on", "with", "by", "from", "as",
    "at", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "should", "could", "may", "might", "must", "can", "i", "me", "my",
    "we", "our", "you", "your", "they", "their", "it", "its", "this", "that", "these", "those",
    "what", "when", "where", "why", "how", "which", "who", "if", "but", "so", "than", "then",
    "also", "just", "only", "about", "into", "through", "during", "before", "after", "up", "down",
    "out", "off", "over", "under", "again", "still", "already", "usually", "really", "very",
}


def _prompt_tokens(prompt: str) -> set[str]:
    p = (prompt or "").lower()
    return {w for w in re.findall(r"[a-z0-9]+", p) if w not in _PROMPT_STOP and len(w) > 1}


def _word_in_prompt(word: str, p_tokens: set[str], prompt_lower: str) -> bool:
    if word in p_tokens:
        return True
    for pt in p_tokens:
        if len(word) >= 3 and len(pt) >= 3 and (pt.startswith(word) or word.startswith(pt)):
            return True
    return word in prompt_lower


def _is_grounded_in_prompt(keyword: str, prompt: str) -> bool:
    """Keyword must trace to the prompt — no off-topic hallucinations."""
    k = (keyword or "").strip().lower()
    prompt_lower = (prompt or "").lower()
    p_tokens = _prompt_tokens(prompt)
    if not k or not p_tokens:
        return False
    k_words = [w for w in k.split() if w not in _PROMPT_STOP]
    if not k_words:
        return False

    insurers = {
        "digit", "hdfc", "ergo", "niva", "bupa", "acko", "star", "care", "icici", "lombard",
        "bajaj", "allianz", "policybazaar",
    }
    for w in k_words:
        if w in insurers:
            if not _word_in_prompt(w, p_tokens, prompt_lower):
                return False
            continue
        if not _word_in_prompt(w, p_tokens, prompt_lower):
            return False

    if " ".join(k_words) in prompt_lower:
        return True
    return bool(set(k_words) & p_tokens)


def _keywords_are_redundant(k1: str, k2: str) -> bool:
    """True if two keywords overlap too much to keep both."""
    a = (k1 or "").strip().lower()
    b = (k2 or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    w1, w2 = set(a.split()), set(b.split())
    if not w1 or not w2:
        return False
    if w1 <= w2 or w2 <= w1:
        return True
    inter = len(w1 & w2)
    union = len(w1 | w2)
    if union and inter / union >= 0.75:
        return True
    return False


def _is_valid_search_keyword(keyword: str, prompt: str) -> bool:
    """Reject prompt copies, fragments, and non-query phrases."""
    k = (keyword or "").strip().lower()
    if not k or len(k) < 4:
        return False
    if is_generic_phrase(k):
        return False
    words = k.split()
    # Google-style: mostly 2–4 words; allow 5 for brand+product (e.g. digit health insurance)
    if len(words) < 2 or len(words) > 5:
        return False
    if len(k) > 48:
        return False
    filler = {
        "understanding", "choosing", "clarify", "adequate", "explained", "definition",
        "usually", "troubleshooting", "appeal", "reimbursement", "continuity",
    }
    if any(w in filler for w in words):
        return False
    # Digit + long invented tails rarely have SV (see runs/20260520T085606Z vs Gemini zero-volume phrases)
    if k.startswith("digit ") and len(words) >= 4:
        return False
    _low_volume_fragments = (
        "digit health insurance waiting",
        "digit senior citizen insurance",
        "digit parents coverage",
        "digit purchase coverage",
        "digit insurance co pay",
        "digit insurance co-pay",
        "digit health insurance co",
        "parents coverage",
        "parents with",
        "health cover for",
        "purchase coverage",
        "hypertension coverage",
        "diabetes coverage",
        "non cashless",
        "app issue",
        "policy continuity",
        "renew digit",
        "advantages health",
        "pros india",
        "basics india",
        "meaning",
        "elders health",
        "floater pricing",
    )
    if any(frag == k or re.search(r"(?<!\S)" + re.escape(frag) + r"(?!\S)", k) for frag in _low_volume_fragments):
        return False
    if k.startswith("digit ") and ("co pay" in k or "co-pay" in k or "copay" in k):
        return False
    p = (prompt or "").strip().lower()
    # Reject only long verbatim slices of the prompt (not short grounded search phrases)
    if len(k) > 50:
        return False
    if len(k) > 35 and re.search(r"(?<!\S)" + re.escape(k) + r"(?!\S)", p):
        return False
    bad_starts = (
        "i ", "i'm ", "if ", "my ", "we ", "our ", "how ", "what ", "when ", "can ",
        "should ", "do ", "does ", "is ", "are ", "will ", "have ", "am ",
    )
    if any(k.startswith(s) for s in bad_starts):
        return False
    stop = {"the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with"}
    if all(w in stop for w in words):
        return False
    if len(words) == 1 and words[0] in {"insurance", "health", "policy", "cover", "plan"}:
        return False
    if not _is_grounded_in_prompt(k, prompt):
        return False
    return True


def _parse_keyword_string(kw: Any) -> Optional[str]:
    """Accept dict, string, or list-of-strings from heterogeneous LLM JSON (no scores)."""
    if isinstance(kw, dict):
        k = str(kw.get("keyword", kw.get("phrase", ""))).strip()
    elif isinstance(kw, str):
        k = kw.strip()
    elif isinstance(kw, (list, tuple)):
        k = " ".join(str(x).strip() for x in kw if x).strip()
    elif hasattr(kw, "keyword"):
        k = str(getattr(kw, "keyword", "")).strip()
    else:
        return None
    return k.lower() if k else None


def _normalize_batch_extractions(data: Any) -> List[dict]:
    """Normalize free-model JSON into [{prompt?, keywords: [...]}, ...]."""
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("extractions") or data.get("results") or data.get("data") or []
        if isinstance(raw, dict):
            raw = list(raw.values())
    else:
        return []

    out: List[dict] = []
    for ex in raw:
        if isinstance(ex, dict):
            kws = ex.get("keywords") or ex.get("keyword") or []
            if isinstance(kws, dict):
                kws = list(kws.values())
            out.append({"prompt": ex.get("prompt", ""), "keywords": kws if isinstance(kws, list) else [kws]})
        elif isinstance(ex, list):
            out.append({"prompt": "", "keywords": ex})
        elif isinstance(ex, str):
            out.append({"prompt": "", "keywords": [ex]})
    return out


def _filter_valid_keywords(
    keywords: List[KeywordWithImportance],
    prompt: str,
    *,
    max_keywords: int,
) -> List[KeywordWithImportance]:
    """Keep grounded, non-overlapping keywords; prefer higher importance_score."""
    sorted_kw = sorted(
        keywords,
        key=lambda x: (x.importance_score, len(x.keyword.split())),
        reverse=True,
    )
    out: List[KeywordWithImportance] = []
    for kw in sorted_kw:
        if not _is_valid_search_keyword(kw.keyword, prompt):
            continue
        replaced = False
        for i, kept in enumerate(out):
            if not _keywords_are_redundant(kw.keyword, kept.keyword):
                continue
            # Prefer the more specific (longer) grounded phrase over a shorter overlap.
            if len(kw.keyword.split()) > len(kept.keyword.split()):
                out[i] = kw
                replaced = True
            break
        if replaced:
            continue
        if any(_keywords_are_redundant(kw.keyword, kept.keyword) for kept in out):
            continue
        out.append(kw)
        if len(out) >= max_keywords:
            break
    return out


def _pydantic_to_openai_schema(model: type[BaseModel], name: str) -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": model.model_json_schema(),
            "strict": True,
        },
    }


class OpenAIClient:
    """OpenAI-compatible client for DeepSeek R1 (OpenRouter) or other models."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout_sec: float = 180.0,
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("Install openai: pip install openai") from e

        kwargs: Dict[str, Any] = {"api_key": api_key, "timeout": timeout_sec}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def generate_intent_clusters(
        self,
        *,
        model: str,
        company: CompanyProfile,
        system_prompt_path: Path,
        n_intents: Optional[int] = None,
    ) -> IntentClusterPlan:
        system_text = _load_text(system_prompt_path)
        user_payload = {"company_profile": company.model_dump()}
        user_content = (
            "Generate intent clusters for this company profile. "
            "Ensure clusters are mutually exclusive and cover the full customer journey. "
            "Output valid JSON only.\n\n"
        )
        if n_intents is not None:
            user_content += f"CRITICAL: Generate exactly {n_intents} intent clusters.\n\n"
        user_content += json.dumps(user_payload, ensure_ascii=False)

        content = None
        used_structured = True
        for use_structured in (True, False):
            try:
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_text},
                        {"role": "user", "content": user_content},
                    ],
                }
                if use_structured:
                    kwargs["response_format"] = _pydantic_to_openai_schema(
                        IntentClusterPlan, "intent_cluster_plan"
                    )
                else:
                    kwargs["messages"][-1]["content"] = (
                        user_content
                        + '\n\nRespond with valid JSON only: {"rationale": "...", "clusters": [{...}]}'
                    )

                resp = self._client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content if resp.choices else None
                if content and content.strip():
                    used_structured = use_structured
                    break
            except Exception:
                if use_structured:
                    continue
                raise

        if not content or not content.strip():
            raise RuntimeError(
                "LLM returned empty content. Check OPENROUTER_API_KEY and model."
            )

        try:
            data = json.loads(content) if used_structured else _extract_json(content)
        except json.JSONDecodeError:
            data = _extract_json(content)

        # Normalize clusters: LLM may omit "name" but include "cluster_id"
        for c in data.get("clusters", []):
            if isinstance(c, dict) and not c.get("name") and c.get("cluster_id"):
                c["name"] = c["cluster_id"].replace("_", " ").title()

        return IntentClusterPlan.model_validate(data)

    def generate_prompts_for_intent(
        self,
        *,
        model: str,
        company: CompanyProfile,
        intent_cluster: IntentCluster,
        n_prompts: int,
        system_prompt_path: Path,
    ) -> List[str]:
        """Generate n_prompts for an intent cluster. Uses batches of 10."""
        system_text = _load_text(system_prompt_path)
        all_prompts: List[str] = []
        batch_size = min(10, n_prompts)
        remaining = n_prompts

        while remaining > 0:
            this_batch = min(batch_size, remaining)
            user_payload = {
                "company_profile": company.model_dump(),
                "intent_cluster": {
                    "cluster_id": intent_cluster.cluster_id,
                    "name": intent_cluster.name,
                    "description": intent_cluster.description or "",
                    "user_mindset": intent_cluster.user_mindset,
                    "example_prompt": intent_cluster.example_prompt,
                },
                "n_prompts": this_batch,
            }
            user_content = (
                "Generate exactly "
                + str(this_batch)
                + " diverse, realistic prompts for this intent cluster. "
                "Vary length, phrasing, and style. Use competitor names for comparison intents. "
                "Output valid JSON only.\n\n"
                + json.dumps(user_payload, ensure_ascii=False)
            )

            content = None
            last_error: Optional[Exception] = None
            for use_structured in (True, False):
                for attempt in range(3):
                    try:
                        kwargs: Dict[str, Any] = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_text},
                                {"role": "user", "content": user_content},
                            ],
                        }
                        if use_structured:
                            kwargs["response_format"] = _pydantic_to_openai_schema(
                                PromptBatchResponse, "prompt_batch"
                            )
                        else:
                            kwargs["messages"][-1]["content"] = (
                                user_content
                                + '\n\nRespond with valid JSON only: {"prompts": ["prompt1", "prompt2", ...]}'
                            )

                        resp = self._client.chat.completions.create(**kwargs)
                        content = resp.choices[0].message.content if resp.choices else None
                        if content and content.strip():
                            break
                        if attempt < 2:
                            time.sleep(2 + attempt * 2)
                    except Exception as e:
                        last_error = e
                        if attempt < 2:
                            time.sleep(2 + attempt * 2)
                            continue
                        if use_structured:
                            break
                        raise
                if content and content.strip():
                    break

            if not content or not content.strip():
                msg = "LLM returned empty content. Check OPENROUTER_API_KEY and model."
                if last_error:
                    msg += f"\n\nLast error: {last_error}"
                raise RuntimeError(msg)

            try:
                data = json.loads(content) if use_structured else _extract_json(content)
            except (json.JSONDecodeError, ValueError):
                partial = _extract_partial_prompts(content)
                if partial:
                    data = {"prompts": partial}
                else:
                    raise

            batch = PromptBatchResponse.model_validate(data)
            all_prompts.extend(batch.prompts[:this_batch])
            remaining -= len(batch.prompts)
            if len(batch.prompts) < this_batch:
                break

        return all_prompts[:n_prompts]

    def extract_keyword_strings_for_prompt(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt_path: Path,
        max_keywords: int = 3,
    ) -> List[str]:
        """LLM keyword phrases only; score with cross-encoder in extractor.py."""
        if not prompt or not prompt.strip():
            return []

        system_text = _load_text(system_prompt_path)
        user_payload = {
            "prompt": prompt.strip(),
            "max_keywords": max_keywords,
        }
        user_content = (
            "Extract 2-3 Google keywords grounded ONLY in this prompt (never more than 3). "
            "Mutually non-overlapping, 2-4 words each, volume-friendly. No hallucinations. "
            "Output valid JSON only.\n\n"
            + json.dumps(user_payload, ensure_ascii=False)
        )

        content = None
        used_structured = True
        last_error: Optional[Exception] = None
        for use_structured in (True, False):
            for attempt in range(6):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_text},
                            {"role": "user", "content": user_content},
                        ],
                    }
                    if use_structured:
                        kwargs["response_format"] = _pydantic_to_openai_schema(
                            KeywordExtractionResponse, "keyword_extraction"
                        )
                    else:
                        kwargs["messages"][-1]["content"] = (
                            user_content
                            + '\n\nRespond with valid JSON only: {"keywords": ["phrase one", "phrase two", ...]}'
                        )

                    resp = self._client.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content if resp.choices else None
                    if content and content.strip():
                        used_structured = use_structured
                        break
                    if attempt < 2:
                        time.sleep(2 + attempt * 2)
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    is_rate_limit = "429" in err_str or "rate limit" in err_str
                    if is_rate_limit and attempt < 5:
                        # Wait 65s for rate limit reset (OpenRouter: 8 req/min)
                        time.sleep(65)
                        continue
                    if attempt < 2:
                        time.sleep(2 + attempt * 2)
                        continue
                    if use_structured:
                        break
                    raise
            if content and content.strip():
                break

        if not content or not content.strip():
            msg = (
                "LLM returned empty content for keyword extraction. "
                "Ensure OPENROUTER_API_KEY is set in .env and the model supports the request. "
                f"Model: {model}"
            )
            if last_error:
                msg += f" Last error: {last_error}"
            raise RuntimeError(msg)

        try:
            data = json.loads(content) if used_structured else _extract_json(content)
        except json.JSONDecodeError:
            data = _extract_json(content)

        if isinstance(data, list):
            raw_keywords = data
        elif isinstance(data, dict):
            raw_keywords = data.get("keywords", [])
        else:
            raw_keywords = []
        if not raw_keywords:
            return []

        strings: List[str] = []
        seen: set[str] = set()
        for kw in raw_keywords[: max_keywords * 2]:
            parsed = _parse_keyword_string(kw)
            if parsed and parsed not in seen:
                seen.add(parsed)
                strings.append(parsed)
        return strings[:max_keywords]

    def extract_keyword_strings_for_prompts_batch(
        self,
        *,
        model: str,
        prompts: List[str],
        system_prompt_path: Path,
        max_keywords: int = 3,
        max_prompts_per_call: int = 10,
        request_delay_sec: float = 8.0,
    ) -> List[List[str]]:
        """LLM keyword phrases per prompt; score with cross-encoder in extractor.py."""
        prompts = [p.strip() for p in prompts if p and p.strip()]
        if not prompts:
            return []

        all_results: List[List[str]] = []
        n_chunks = (len(prompts) + max_prompts_per_call - 1) // max_prompts_per_call
        for chunk_start in range(0, len(prompts), max_prompts_per_call):
            chunk = prompts[chunk_start : chunk_start + max_prompts_per_call]
            chunk_num = chunk_start // max_prompts_per_call + 1
            print(
                f"  OpenRouter LLM chunk {chunk_num}/{n_chunks}: "
                f"{len(chunk)} prompts, model={model}",
                flush=True,
            )
            system_text = _load_text(system_prompt_path)
            user_payload = {
                "prompts": chunk,
                "max_keywords": max_keywords,
            }
            user_content = (
                "For EACH prompt extract 2-3 Google search keywords only (never more than 3) that are: "
                "(1) grounded ONLY in that prompt's text — no new topics or insurers; "
                "(2) mutually non-overlapping — no near-duplicate phrases; "
                "(3) short volume-friendly queries (2-4 words). "
                "No hallucinations. Output valid JSON only. Same prompt order as input.\n\n"
                + json.dumps(user_payload, ensure_ascii=False)
            )

            content = None
            used_structured = True
            last_error: Optional[Exception] = None
            structured_modes = (False, True) if _prefer_plain_json(model) else (True, False)
            max_attempts = 3 if _prefer_plain_json(model) else 6
            for use_structured in structured_modes:
                for attempt in range(max_attempts):
                    try:
                        kwargs: Dict[str, Any] = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_text},
                                {"role": "user", "content": user_content},
                            ],
                            "max_tokens": 8192,
                        }
                        if use_structured:
                            kwargs["response_format"] = _pydantic_to_openai_schema(
                                KeywordExtractionBatchResponse, "keyword_extraction_batch"
                            )
                        else:
                            kwargs["messages"][-1]["content"] = (
                                user_content
                                + '\n\nRespond with valid JSON only: {"extractions": [{"prompt": "...", "keywords": [...]}, ...]}'
                            )

                        mode = "structured" if use_structured else "plain-json"
                        print(
                            f"  OpenRouter LLM chunk {chunk_num}/{n_chunks}: "
                            f"sending ({mode}, attempt {attempt + 1}/{max_attempts})...",
                            flush=True,
                        )
                        resp = self._client.chat.completions.create(**kwargs)
                        content = resp.choices[0].message.content if resp.choices else None
                        if content and content.strip():
                            used_structured = use_structured
                            break
                        if attempt < 2:
                            time.sleep(2 + attempt * 2)
                    except Exception as e:
                        last_error = e
                        print(
                            f"  OpenRouter LLM chunk {chunk_num}/{n_chunks}: "
                            f"error ({type(e).__name__}): {e}",
                            flush=True,
                        )
                        err_str = str(e).lower()
                        is_rate_limit = "429" in err_str or "rate limit" in err_str
                        is_timeout = "timeout" in err_str or "timed out" in err_str
                        if is_rate_limit and attempt < max_attempts - 1:
                            time.sleep(65)
                            continue
                        if is_timeout:
                            continue
                        if attempt < max_attempts - 1:
                            time.sleep(2 + attempt * 2)
                            continue
                        if use_structured:
                            break
                        raise
                if content and content.strip():
                    break

            if not content or not content.strip():
                msg = "LLM returned empty content for batch keyword extraction."
                if last_error:
                    msg += f" Last error: {last_error}"
                raise RuntimeError(msg)

            print(f"  OpenRouter LLM chunk {chunk_num}/{n_chunks}: response OK", flush=True)

            try:
                data = json.loads(content) if used_structured else _extract_json(content)
            except json.JSONDecodeError:
                data = _extract_json(content)

            normalized = _normalize_batch_extractions(data)
            for i in range(len(chunk)):
                ex = normalized[i] if i < len(normalized) else {"prompt": "", "keywords": []}
                kws = ex.get("keywords", []) if isinstance(ex, dict) else []
                strings: List[str] = []
                seen: set[str] = set()
                for kw in kws[: max_keywords * 2]:
                    parsed = _parse_keyword_string(kw)
                    if parsed and parsed not in seen:
                        seen.add(parsed)
                        strings.append(parsed)
                all_results.append(strings[:max_keywords])

            # Pad missing slots with empty lists (caller may retry per-prompt LLM)
            while len(all_results) < chunk_start + len(chunk):
                all_results.append([])

            # Rate limit: wait between chunks
            if chunk_start + max_prompts_per_call < len(prompts):
                time.sleep(max(request_delay_sec, 0.0))

        return all_results[:len(prompts)]

    def filter_ngram_candidates_for_prompt(
        self,
        *,
        model: str,
        prompt: str,
        candidates: List[str],
        system_prompt_path: Path,
        max_keywords: int = 6,
    ) -> List[str]:
        """Select a subset of n-gram candidates important to the prompt (no new keywords)."""
        if not prompt or not prompt.strip() or not candidates:
            return []

        system_text = _load_text(system_prompt_path)
        user_payload = {
            "prompt": prompt.strip(),
            "candidates": candidates,
            "max_keywords": max_keywords,
        }
        user_content = (
            "Select 2-6 keywords from the candidate list only. Drop irrelevant and overlapping "
            "phrases. Keep keywords central to the prompt's search intent. JSON only.\n\n"
            + json.dumps(user_payload, ensure_ascii=False)
        )

        content = None
        used_structured = True
        last_error: Optional[Exception] = None
        for use_structured in (True, False):
            for attempt in range(6):
                try:
                    kwargs: Dict[str, Any] = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_text},
                            {"role": "user", "content": user_content},
                        ],
                    }
                    if use_structured:
                        kwargs["response_format"] = _pydantic_to_openai_schema(
                            KeywordExtractionResponse, "keyword_filter_ngram"
                        )
                    else:
                        kwargs["messages"][-1]["content"] = (
                            user_content
                            + '\n\nRespond with valid JSON only: {"keywords": ["...", "..."]}'
                        )

                    resp = self._client.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content if resp.choices else None
                    if content and content.strip():
                        used_structured = use_structured
                        break
                    if attempt < 2:
                        time.sleep(2 + attempt * 2)
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    if ("429" in err_str or "rate limit" in err_str) and attempt < 5:
                        time.sleep(65)
                        continue
                    if attempt < 2:
                        time.sleep(2 + attempt * 2)
                        continue
                    if use_structured:
                        break
                    raise
            if content and content.strip():
                break

        if not content or not content.strip():
            msg = "LLM returned empty content for ngram candidate filtering."
            if last_error:
                msg += f" Last error: {last_error}"
            raise RuntimeError(msg)

        try:
            data = json.loads(content) if used_structured else _extract_json(content)
        except json.JSONDecodeError:
            data = _extract_json(content)

        raw_keywords = data.get("keywords", []) if isinstance(data, dict) else data
        strings: List[str] = []
        seen: set[str] = set()
        for kw in raw_keywords[: max_keywords * 2]:
            parsed = _parse_keyword_string(kw)
            if parsed and parsed not in seen:
                seen.add(parsed)
                strings.append(parsed)
        return strings[:max_keywords]

    def filter_ngram_candidates_batch(
        self,
        *,
        model: str,
        items: List[dict],
        system_prompt_path: Path,
        max_keywords: int = 6,
        max_items_per_call: int = 10,
        request_delay_sec: float = 8.0,
    ) -> List[List[str]]:
        """Batch filter n-gram candidates. Each item: {prompt, candidates}."""
        if not items:
            return []

        all_results: List[List[str]] = []
        n_chunks = (len(items) + max_items_per_call - 1) // max_items_per_call
        for chunk_start in range(0, len(items), max_items_per_call):
            chunk = items[chunk_start : chunk_start + max_items_per_call]
            chunk_num = chunk_start // max_items_per_call + 1
            print(
                f"  OpenRouter LLM filter chunk {chunk_num}/{n_chunks}: "
                f"{len(chunk)} prompts, model={model}",
                flush=True,
            )
            system_text = _load_text(system_prompt_path)
            user_payload = {
                "items": [
                    {"prompt": it["prompt"], "candidates": it["candidates"]}
                    for it in chunk
                ],
                "max_keywords": max_keywords,
            }
            user_content = (
                "For EACH item, select 2-6 keywords from that item's candidate list only. "
                "Drop irrelevant and overlapping phrases. Same item order as input. JSON only.\n\n"
                + json.dumps(user_payload, ensure_ascii=False)
            )

            content = None
            used_structured = True
            last_error: Optional[Exception] = None
            structured_modes = (False, True) if _prefer_plain_json(model) else (True, False)
            max_attempts = 3 if _prefer_plain_json(model) else 6
            for use_structured in structured_modes:
                for attempt in range(max_attempts):
                    try:
                        kwargs: Dict[str, Any] = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_text},
                                {"role": "user", "content": user_content},
                            ],
                            "max_tokens": 8192,
                        }
                        if use_structured:
                            kwargs["response_format"] = _pydantic_to_openai_schema(
                                KeywordExtractionBatchResponse, "keyword_filter_ngram_batch"
                            )
                        else:
                            kwargs["messages"][-1]["content"] = (
                                user_content
                                + '\n\nRespond with valid JSON only: {"extractions": [{"prompt": "...", "keywords": [...]}, ...]}'
                            )

                        resp = self._client.chat.completions.create(**kwargs)
                        content = resp.choices[0].message.content if resp.choices else None
                        if content and content.strip():
                            used_structured = use_structured
                            break
                        if attempt < 2:
                            time.sleep(2 + attempt * 2)
                    except Exception as e:
                        last_error = e
                        err_str = str(e).lower()
                        if ("429" in err_str or "rate limit" in err_str) and attempt < max_attempts - 1:
                            time.sleep(65)
                            continue
                        if attempt < max_attempts - 1:
                            time.sleep(2 + attempt * 2)
                            continue
                        if use_structured:
                            break
                        raise
                if content and content.strip():
                    break

            if not content or not content.strip():
                msg = "LLM returned empty content for batch ngram candidate filtering."
                if last_error:
                    msg += f" Last error: {last_error}"
                raise RuntimeError(msg)

            print(f"  OpenRouter LLM filter chunk {chunk_num}/{n_chunks}: response OK", flush=True)

            try:
                data = json.loads(content) if used_structured else _extract_json(content)
            except json.JSONDecodeError:
                data = _extract_json(content)

            normalized = _normalize_batch_extractions(data)
            for i in range(len(chunk)):
                ex = normalized[i] if i < len(normalized) else {"prompt": "", "keywords": []}
                kws = ex.get("keywords", []) if isinstance(ex, dict) else []
                strings: List[str] = []
                seen: set[str] = set()
                for kw in kws[: max_keywords * 2]:
                    parsed = _parse_keyword_string(kw)
                    if parsed and parsed not in seen:
                        seen.add(parsed)
                        strings.append(parsed)
                all_results.append(strings[:max_keywords])

            while len(all_results) < chunk_start + len(chunk):
                all_results.append([])

            if chunk_start + max_items_per_call < len(items):
                time.sleep(max(request_delay_sec, 0.0))

        return all_results[: len(items)]