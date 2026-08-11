"""DataForSEO API client for SV (classic) and ASV (AI) search volume."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import unicodedata
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

from case2_demand.keyword_volume.base import KeywordVolumeResult, KeywordVolumeClient

# DataForSEO API limits: clickstream bulk max 700; Google Ads SV max 1000; ASV max 1000.
# Per docs: https://docs.dataforseo.com/v3/keywords_data/clickstream_data/bulk_search_volume/live/
SV_BATCH_SIZE = 700
GOOGLE_ADS_SV_BATCH_SIZE = 1000
ASV_BATCH_SIZE = 1000
ASV_DEFAULT_TIMEOUT_S = 120.0
ASV_MAX_RETRIES = 3
BATCH_DELAY_SEC = 0.5  # Delay between batches to avoid rate limits
SV_RETRY_BATCH_SIZE = 500  # Retry batches (smaller than initial 700 to reduce synonym grouping)

# Keyword constraints per DataForSEO: SV max 80 chars, max 10 words; ASV max 250 chars
SV_MAX_CHARS = 80
SV_MAX_WORDS = 10
ASV_MAX_CHARS = 250


def _make_auth_header(login: str, password: str) -> str:
    credentials = f"{login}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


_PERCENT_RE = re.compile(r"%+")
_NON_WORD_RE = re.compile(r"[^0-9A-Za-z\s\-']")
_WS_RE = re.compile(r"\s+")


def _sanitize_keyword(keyword: str) -> str:
    """
    Sanitize keyword text to avoid DataForSEO/Google Ads payload validation errors.
    Keeps letters/numbers/space/hyphen/apostrophe, replaces % with 'percent'.
    """
    kw = (keyword or "").strip()
    if not kw:
        return ""
    kw = unicodedata.normalize("NFKC", kw)
    kw = _PERCENT_RE.sub(" percent ", kw)
    kw = _NON_WORD_RE.sub(" ", kw)
    kw = _WS_RE.sub(" ", kw).strip()
    return kw


def _sanitize_keywords(batch: List[str]) -> tuple[list[str], dict[str, str]]:
    """Return (sanitized_unique_keywords, original_to_sanitized)."""
    orig_to_san: dict[str, str] = {}
    sanitized_unique: list[str] = []
    seen: set[str] = set()
    for kw in batch:
        san = _sanitize_keyword(kw)
        orig_to_san[kw] = san
        if not san:
            continue
        key = san.lower()
        if key not in seen:
            seen.add(key)
            sanitized_unique.append(san)
    return sanitized_unique, orig_to_san


def _coerce_keyword_sv(keyword: str) -> str:
    """
    Coerce keyword to SV API constraints without dropping it.
    DataForSEO: max 80 chars, max 10 words.
    """
    kw = (keyword or "").strip()
    if not kw:
        return ""

    # Keep at most 10 words (helps payload validation).
    words = kw.split()
    if len(words) > SV_MAX_WORDS:
        words = words[:SV_MAX_WORDS]
    kw = " ".join(words).strip()

    # Keep at most 80 chars.
    if len(kw) > SV_MAX_CHARS:
        kw = kw[:SV_MAX_CHARS].rsplit(" ", 1)[0].strip() or kw[:SV_MAX_CHARS].strip()
    return kw


def _coerce_keyword_asv(keyword: str) -> str:
    """Coerce keyword to ASV API constraints without dropping it."""
    kw = (keyword or "").strip()
    if not kw:
        return ""
    if len(kw) > ASV_MAX_CHARS:
        kw = kw[:ASV_MAX_CHARS].rsplit(" ", 1)[0].strip() or kw[:ASV_MAX_CHARS].strip()
    return kw


def filter_keywords_for_api(
    keywords: List[str],
    *,
    for_sv: bool = True,
) -> tuple[list[str], dict[str, str]]:
    """
    Filter and sanitize keywords for DataForSEO API.
    Returns (keywords_to_send, original_to_sanitized).
    Only keywords that become empty after sanitization are excluded.
    Keywords are coerced (truncated) to match SV/ASV max constraints.
    """
    sanitized_unique: list[str] = []
    orig_to_san: dict[str, str] = {}
    seen: set[str] = set()
    for kw in keywords:
        san = _sanitize_keyword(kw)
        if not san:
            # Drop only if the keyword is effectively "special-char-only" and becomes empty.
            orig_to_san[kw] = ""
            continue

        if for_sv:
            san = _coerce_keyword_sv(san)
        else:
            san = _coerce_keyword_asv(san)

        # If truncation/coercion somehow produces empty, treat as dropped.
        if not san:
            orig_to_san[kw] = ""
            continue

        orig_to_san[kw] = san
        key = san.lower()
        if key not in seen:
            seen.add(key)
            sanitized_unique.append(san)
    return sanitized_unique, orig_to_san

def _normalize_competition(comp, comp_index) -> float | None:
    """
    DataForSEO Google Ads can return competition as:
      - label: "LOW" | "MEDIUM" | "HIGH"
      - numeric (rare)
    It also often returns competition_index in [0,100]. Prefer index when present.
    Returns a float in [0,1] or None if unavailable.
    """
    try:
        if comp_index is not None:
            v = float(comp_index) / 100.0
            return max(0.0, min(1.0, v))
    except Exception:
        pass
    if comp is None:
        return None
    if isinstance(comp, (int, float)):
        v = float(comp)
        # If it's already 0..1 keep; if it's 0..100 scale down.
        if v > 1.0 and v <= 100.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    if isinstance(comp, str):
        m = comp.strip().upper()
        if m == "LOW":
            return 0.0
        if m == "MEDIUM":
            return 0.5
        if m == "HIGH":
            return 1.0
    return None


def _extract_clickstream_sv_items_from_task_result(task_result: dict) -> dict[str, dict]:
    """Parse clickstream bulk SV rows: keyword_lower -> item dict."""
    out: dict[str, dict] = {}
    for block in task_result.get("result", []) or []:
        for item in block.get("items", []) or []:
            kw = str(item.get("keyword") or "").strip().lower()
            if kw:
                out[kw] = item
    return out


def _extract_google_ads_sv_items_from_task_result(task_result: dict) -> dict[str, dict]:
    """Parse Google Ads SV rows: keyword_lower -> item dict."""
    out: dict[str, dict] = {}
    for item in task_result.get("result", []) or []:
        kw = str(item.get("keyword") or "").strip().lower()
        if kw:
            out[kw] = item
    return out


class DataForSEOSVClient(KeywordVolumeClient):
    """Fetch classic search volume (SV) from DataForSEO (clickstream or Google Ads)."""

    def __init__(
        self,
        *,
        login: str,
        password: str,
        base_url: str = "https://api.dataforseo.com/v3",
        timeout_s: float = 30.0,
        sv_source: str = "clickstream",
    ):
        self._login = login
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._auth_header = _make_auth_header(login, password)
        self._sv_source = (sv_source or "clickstream").strip().lower()

    def is_available(self) -> bool:
        return bool(self._login and self._password)

    async def get_volume(
        self,
        keywords: List[str],
        location_code: Optional[int] = 2840,
        language_code: Optional[str] = "en",
        *,
        worldwide: bool = False,
    ) -> List[KeywordVolumeResult]:
        """
        Search volume for a market (``location_code`` required).

        ``sv_source=clickstream`` uses ``clickstream_data/bulk_search_volume/live``.
        ``sv_source=google_ads`` uses ``keywords_data/google_ads/search_volume/live``.
        """
        if not keywords:
            return []
        loc = location_code or 2840
        lang = language_code or "en"

        if self._sv_source == "google_ads":
            return await self._fetch_batch_google_ads(keywords, loc, lang)

        all_results = await self._fetch_batch_clickstream(
            keywords, loc, lang, batch_size=SV_BATCH_SIZE
        )

        # Retry keywords that got "Keyword not found"
        missing = [r.keyword for r in all_results if r.error == "Keyword not found"]
        if missing:
            await asyncio.sleep(BATCH_DELAY_SEC)  # Brief pause before retry
            retry_results = await self._fetch_batch_clickstream(
                missing,
                loc,
                lang,
                batch_size=SV_RETRY_BATCH_SIZE,
            )
            # Build lookup: original keyword (preserve casing) -> result
            retry_map = {r.keyword.lower(): r for r in retry_results}
            # Replace failed results with retry results
            for i, r in enumerate(all_results):
                if r.error == "Keyword not found":
                    retried = retry_map.get(r.keyword.lower())
                    if retried and not retried.error:
                        all_results[i] = retried

        return all_results

    async def _fetch_batch_google_ads(
        self,
        keywords: List[str],
        loc: int,
        lang: str,
        batch_size: int = GOOGLE_ADS_SV_BATCH_SIZE,
    ) -> List[KeywordVolumeResult]:
        """Fetch Google Ads SV for a list of keywords in batches."""
        url = f"{self._base_url}/keywords_data/google_ads/search_volume/live"
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        results: List[KeywordVolumeResult] = []
        for i in range(0, len(keywords), batch_size):
            batch_orig = keywords[i : i + batch_size]
            batch_sanitized, orig_to_san = filter_keywords_for_api(batch_orig, for_sv=True)

            for kw in batch_orig:
                san = orig_to_san.get(kw, "")
                if not san:
                    results.append(KeywordVolumeResult(keyword=kw, error="Keyword filtered or empty"))

            if not batch_sanitized:
                if i + batch_size < len(keywords):
                    await asyncio.sleep(BATCH_DELAY_SEC)
                continue

            task_body = {
                "keywords": batch_sanitized,
                "location_code": loc,
                "language_code": lang,
                "search_partners": True,
            }
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, headers=headers, json=[task_body])
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                for kw in batch_orig:
                    if orig_to_san.get(kw):
                        results.append(KeywordVolumeResult(keyword=kw, error=str(e)))
                if i + batch_size < len(keywords):
                    await asyncio.sleep(BATCH_DELAY_SEC)
                continue

            if not data or "tasks" not in data or not data["tasks"]:
                for kw in batch_orig:
                    if orig_to_san.get(kw):
                        results.append(KeywordVolumeResult(keyword=kw, error="No data"))
            else:
                task_result = data["tasks"][0]
                if task_result.get("status_code") != 20000:
                    err = task_result.get("status_message", "Unknown error")
                    for kw in batch_orig:
                        if orig_to_san.get(kw):
                            results.append(KeywordVolumeResult(keyword=kw, error=err))
                else:
                    kw_map = _extract_google_ads_sv_items_from_task_result(task_result)
                    for kw in batch_orig:
                        san = orig_to_san.get(kw, "")
                        if not san:
                            continue
                        item = kw_map.get(san.lower())
                        if item:
                            vol = item.get("search_volume")
                            if vol is None:
                                results.append(KeywordVolumeResult(keyword=kw, error="Keyword not found"))
                            else:
                                monthly = item.get("monthly_searches") or []
                                cpc = item.get("cpc")
                                comp = _normalize_competition(
                                    item.get("competition"),
                                    item.get("competition_index"),
                                )
                                results.append(KeywordVolumeResult(
                                    keyword=kw,
                                    search_volume=vol,
                                    cpc=float(cpc) if cpc is not None else None,
                                    competition=comp,
                                    monthly_searches=monthly if monthly else None,
                                ))
                        else:
                            results.append(KeywordVolumeResult(keyword=kw, error="Keyword not found"))

            if i + batch_size < len(keywords):
                await asyncio.sleep(BATCH_DELAY_SEC)

        return results

    async def _fetch_batch_clickstream(
        self,
        keywords: List[str],
        loc: int,
        lang: str,
        batch_size: int = SV_BATCH_SIZE,
    ) -> List[KeywordVolumeResult]:
        """Fetch clickstream SV for a list of keywords in batches."""
        url = f"{self._base_url}/keywords_data/clickstream_data/bulk_search_volume/live"
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        results: List[KeywordVolumeResult] = []
        for i in range(0, len(keywords), batch_size):
            batch_orig = keywords[i : i + batch_size]
            batch_sanitized, orig_to_san = filter_keywords_for_api(batch_orig, for_sv=True)

            # Emit errors for keywords filtered or empty after sanitization
            for kw in batch_orig:
                san = orig_to_san.get(kw, "")
                if not san:
                    results.append(KeywordVolumeResult(keyword=kw, error="Keyword filtered or empty"))

            # If nothing valid to query, skip API call
            if not batch_sanitized:
                if i + batch_size < len(keywords):
                    await asyncio.sleep(BATCH_DELAY_SEC)
                continue

            task_body: dict = {
                "location_code": loc,
                "keywords": batch_sanitized,
            }
            tasks = [task_body]
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, headers=headers, json=tasks)
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                # Only emit for keywords we actually sent (not filtered)
                for kw in batch_orig:
                    if orig_to_san.get(kw):
                        results.append(KeywordVolumeResult(keyword=kw, error=str(e)))
                if i + batch_size < len(keywords):
                    await asyncio.sleep(BATCH_DELAY_SEC)
                continue

            if not data or "tasks" not in data or not data["tasks"]:
                for kw in batch_orig:
                    if orig_to_san.get(kw):
                        results.append(KeywordVolumeResult(keyword=kw, error="No data"))
            else:
                task_result = data["tasks"][0]
                if task_result.get("status_code") != 20000:
                    err = task_result.get("status_message", "Unknown error")
                    for kw in batch_orig:
                        if orig_to_san.get(kw):
                            results.append(KeywordVolumeResult(keyword=kw, error=err))
                else:
                    kw_map = _extract_clickstream_sv_items_from_task_result(task_result)
                    for kw in batch_orig:
                        san = orig_to_san.get(kw, "")
                        if not san:
                            continue  # already emitted error
                        item = kw_map.get(san.lower())
                        if item:
                            vol = item.get("search_volume")
                            if vol is None:
                                results.append(KeywordVolumeResult(keyword=kw, error="Keyword not found"))
                            else:
                                monthly = item.get("monthly_searches") or []
                                results.append(KeywordVolumeResult(
                                    keyword=kw,
                                    search_volume=vol,
                                    monthly_searches=monthly if monthly else None,
                                ))
                        else:
                            results.append(KeywordVolumeResult(keyword=kw, error="Keyword not found"))

            if i + batch_size < len(keywords):
                await asyncio.sleep(BATCH_DELAY_SEC)

        return results


def _extract_asv_items_from_task_result(task_result: dict) -> List[dict]:
    """Parse ASV keyword rows from a DataForSEO task result (nested or flat)."""
    items: List[dict] = []
    for r in task_result.get("result", []) or []:
        nested = r.get("items") or []
        if nested:
            items.extend(nested)
        elif r.get("keyword"):
            items.append(r)
    return items


class DataForSEOASVClient(KeywordVolumeClient):
    """Fetch AI search volume (ASV) from DataForSEO AI Keyword Data API."""

    def __init__(
        self,
        *,
        login: str,
        password: str,
        base_url: str = "https://api.dataforseo.com/v3",
        timeout_s: float = ASV_DEFAULT_TIMEOUT_S,
    ):
        self._login = login
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._auth_header = _make_auth_header(login, password)

    def is_available(self) -> bool:
        return bool(self._login and self._password)

    async def get_volume(
        self,
        keywords: List[str],
        location_code: Optional[int] = 2840,
        language_code: Optional[str] = "en",
    ) -> List[KeywordVolumeResult]:
        if not keywords:
            return []
        batch_sanitized, orig_to_san = filter_keywords_for_api(keywords, for_sv=False)
        items = await self._fetch_asv_batches(batch_sanitized, location_code, language_code)
        kw_map = {item.get("keyword", "").lower(): item for item in items if item.get("keyword")}
        results = []
        for kw in keywords:
            san = orig_to_san.get(kw, "")
            if not san:
                results.append(KeywordVolumeResult(keyword=kw, error="Keyword filtered or empty"))
                continue
            item = kw_map.get(san.lower())
            if item:
                ai_vol = item.get("ai_search_volume")
                results.append(KeywordVolumeResult(keyword=kw, search_volume=ai_vol))
            else:
                results.append(KeywordVolumeResult(keyword=kw, error="Keyword not found"))
        return results

    async def get_volume_with_history(
        self,
        keywords: List[str],
        location_code: Optional[int] = 2840,
        language_code: Optional[str] = "en",
    ) -> List[dict]:
        """
        Fetch AI search volume plus monthly history (ai_monthly_searches).
        Returns list of {keyword, ai_search_volume, ai_monthly_searches}.
        """
        if not keywords:
            return []
        batch_sanitized, orig_to_san = filter_keywords_for_api(keywords, for_sv=False)
        items = await self._fetch_asv_batches(batch_sanitized, location_code, language_code)
        kw_map = {item.get("keyword", "").lower(): item for item in items if item.get("keyword")}
        out: list[dict] = []
        for kw in keywords:
            san = orig_to_san.get(kw, "")
            if not san:
                continue
            item = kw_map.get(san.lower())
            if item:
                copied = dict(item)
                copied["keyword"] = kw  # map back to original keyword text
                out.append(copied)
        return out

    async def _fetch_asv_batches(
        self,
        keywords: List[str],
        location_code: Optional[int] = 2840,
        language_code: Optional[str] = "en",
    ) -> List[dict]:
        """Fetch ASV in batches of ASV_BATCH_SIZE (DataForSEO limit: 1000)."""
        url = f"{self._base_url}/ai_optimization/ai_keyword_data/keywords_search_volume/live"
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        loc = location_code or 2840
        lang = language_code or "en"

        all_items: List[dict] = []
        for i in range(0, len(keywords), ASV_BATCH_SIZE):
            batch = keywords[i : i + ASV_BATCH_SIZE]
            batch_sanitized, _ = _sanitize_keywords(batch)
            if not batch_sanitized:
                if i + ASV_BATCH_SIZE < len(keywords):
                    await asyncio.sleep(BATCH_DELAY_SEC)
                continue

            batch_items: List[dict] = []
            last_err: str | None = None
            for attempt in range(1, ASV_MAX_RETRIES + 1):
                tasks = [{"keywords": batch_sanitized, "location_code": loc, "language_code": lang}]
                try:
                    async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                        response = await client.post(url, headers=headers, json=tasks)
                        response.raise_for_status()
                        data = response.json()
                except Exception as e:
                    last_err = str(e)
                    logger.warning(
                        "ASV batch %d-%d attempt %d/%d failed: %s",
                        i,
                        i + len(batch_sanitized),
                        attempt,
                        ASV_MAX_RETRIES,
                        e,
                    )
                    if attempt < ASV_MAX_RETRIES:
                        await asyncio.sleep(BATCH_DELAY_SEC * attempt)
                    continue

                if not data or "tasks" not in data or not data["tasks"]:
                    last_err = "empty tasks in response"
                    if attempt < ASV_MAX_RETRIES:
                        await asyncio.sleep(BATCH_DELAY_SEC * attempt)
                    continue

                task_result = data["tasks"][0]
                status = task_result.get("status_code")
                if status == 20000:
                    batch_items = _extract_asv_items_from_task_result(task_result)
                    last_err = None
                    break

                last_err = task_result.get("status_message", f"status_code={status}")
                logger.warning(
                    "ASV batch %d-%d attempt %d/%d API status %s: %s",
                    i,
                    i + len(batch_sanitized),
                    attempt,
                    ASV_MAX_RETRIES,
                    status,
                    last_err,
                )
                if attempt < ASV_MAX_RETRIES:
                    await asyncio.sleep(BATCH_DELAY_SEC * attempt)

            if batch_items:
                all_items.extend(batch_items)
            elif last_err:
                logger.error(
                    "ASV batch %d-%d dropped after %d attempts: %s",
                    i,
                    i + len(batch_sanitized),
                    ASV_MAX_RETRIES,
                    last_err,
                )

            if i + ASV_BATCH_SIZE < len(keywords):
                await asyncio.sleep(BATCH_DELAY_SEC)

        return all_items


class DataForSEOSearchIntentClient:
    """Fetch search intent (informational probability I(k)) from DataForSEO Labs."""

    def __init__(
        self,
        *,
        login: str,
        password: str,
        base_url: str = "https://api.dataforseo.com/v3",
        timeout_s: float = 30.0,
    ):
        self._login = login
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._auth_header = _make_auth_header(login, password)

    def is_available(self) -> bool:
        return bool(self._login and self._password)

    async def get_informational_scores(
        self,
        keywords: List[str],
        language_code: Optional[str] = "en",
    ) -> dict[str, float]:
        """
        Get I(k) = informational probability per keyword.
        Returns {keyword: probability} where probability ∈ [0,1].
        Uses 0.5 if keyword not found or no informational intent.
        """
        if not keywords:
            return {}
        url = f"{self._base_url}/dataforseo_labs/google/search_intent/live"
        headers = {"Authorization": self._auth_header, "Content-Type": "application/json"}
        tasks = [{"keywords": keywords, "language_code": language_code or "en"}]
        result_map: dict[str, float] = {kw.lower(): 0.5 for kw in keywords}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(url, headers=headers, json=tasks)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return result_map

        if not data or "tasks" not in data or not data["tasks"]:
            return result_map

        task_result = data["tasks"][0]
        if task_result.get("status_code") != 20000:
            return result_map

        items = []
        for r in task_result.get("result", []):
            items.extend(r.get("items", []))
        for item in items:
            kw = item.get("keyword", "").lower()
            intent = item.get("keyword_intent") or {}
            label = (intent.get("label") or "").lower()
            prob = float(intent.get("probability") or 0)
            if label == "informational":
                result_map[kw] = prob
            else:
                for sec in (item.get("secondary_keyword_intents") or []):
                    if (sec.get("label") or "").lower() == "informational":
                        result_map[kw] = float(sec.get("probability") or 0)
                        break
        return {kw: result_map.get(kw.lower(), 0.5) for kw in keywords}
