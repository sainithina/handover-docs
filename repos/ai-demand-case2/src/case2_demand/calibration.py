"""
Calibration for Case 2: ρ (AI-share), η (AI-uplift), and SV prior (νc, ωc, σS,c).

ρ: Empirical AI share from volume history — mean(ASV/(η×SV)), floored at 25%; intent-cluster prior for cold start
η: Empirical Bayes from paired (SV, ASV) residuals — Step 8a of spec
SV prior: Empirical Bayes from historical SV (mirrors case1_demand) — si ~ N(νc, ω²c)
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from case2_demand.keyword_volume.dataforseo import (
        DataForSEOASVClient,
        DataForSEOSVClient,
    )


@dataclass
class CalibratedSVParams:
    """SV measurement model params calibrated from historical SV (case1-style Empirical Bayes).

    Prior: si ~ N(νc, ω²c)
    Likelihood: yi | si ~ N(si - b_S, σ²S,c)
    Posterior: σ²s,post = 1/(1/ω²c + 1/σ²S,c), μ(s)i,post = σ²s,post * (νc/ω²c + (yi-b_S)/σ²S,c)
    """
    nu_c: float
    omega_c: float
    b_S: float
    sigma_S_c: float
    num_keywords: int
    num_periods: int


def calibrate_sv_from_matrix(
    historical_sv: np.ndarray,
    b_S: float = 0.0,
) -> CalibratedSVParams:
    """
    Calibrate SV prior (νc, ωc) and measurement noise (σS,c) from historical SV matrix.

    Mirrors case1_demand.calibration.calibrate_from_matrix for ASV.
    Uses Empirical Bayes: within-keyword variance → σ²S,c, between-keyword → ω²c.

    Args:
        historical_sv: Shape (K, T) - K keywords, T time periods. Each row = one keyword's SV over time.
        b_S: Bias (default 0).

    Returns:
        CalibratedSVParams
    """
    y_kt = np.log(np.maximum(historical_sv, 1))
    K, T = y_kt.shape

    # Step 1: Time-averaged log-SV per keyword
    y_bar_k = np.mean(y_kt, axis=1)

    # Step 2: Within-keyword variance (measurement noise σ²S,c)
    sigma_sq_S_k = np.var(y_kt, axis=1, ddof=1)
    sigma_sq_S_k = np.nan_to_num(sigma_sq_S_k, nan=0.0, posinf=0.0, neginf=0.0)
    sigma_sq_S_c = float(np.mean(sigma_sq_S_k))
    sigma_S_c = max(np.sqrt(max(sigma_sq_S_c, 1e-10)), 0.01)

    # Step 3: De-bias and prior mean νc
    s_hat_k = y_bar_k - b_S
    nu_c = float(np.mean(s_hat_k))

    # Step 4: Between-keyword variance with noise correction → ω²c
    between_var_raw = float(np.var(s_hat_k, ddof=1))
    noise_correction = sigma_sq_S_c / T
    omega_sq_c = max(between_var_raw - noise_correction, 0.01)
    omega_c = float(np.sqrt(omega_sq_c))

    return CalibratedSVParams(
        nu_c=nu_c,
        omega_c=omega_c,
        b_S=b_S,
        sigma_S_c=sigma_S_c,
        num_keywords=K,
        num_periods=T,
    )


def calibrate_sv_from_list(
    historical_sv: List[List[float]],
    b_S: float = 0.0,
    min_periods: int = 2,
) -> Optional[CalibratedSVParams]:
    """
    Calibrate SV params from list of lists. Rows may have different lengths;
    truncates to min length for a proper (K,T) matrix.
    """
    if not historical_sv:
        return None
    min_len = min(len(row) for row in historical_sv)
    if min_len < min_periods:
        return None
    truncated = [row[:min_len] for row in historical_sv if len(row) >= min_len]
    if len(truncated) < 2:
        return None
    arr = np.array(truncated)
    return calibrate_sv_from_matrix(arr, b_S=b_S)


@dataclass
class CalibratedASVParams:
    """ASV measurement model params (case1-style). xi ~ N(μc, τ²c), likelihood σ²A,c."""
    mu_c: float
    tau_c: float
    b_A: float
    sigma_A_c: float
    num_keywords: int
    num_periods: int


def calibrate_asv_from_matrix(
    historical_asv: np.ndarray,
    b_A: float = 0.0,
) -> CalibratedASVParams:
    """
    Calibrate ASV prior (μc, τc) and measurement noise (σA,c) from historical ASV.
    Mirrors case1_demand.calibration.calibrate_from_matrix exactly.
    """
    x_kt = np.log(np.maximum(historical_asv, 1))
    K, T = x_kt.shape
    x_bar_k = np.mean(x_kt, axis=1)
    sigma_sq_A_k = np.var(x_kt, axis=1, ddof=1)
    sigma_sq_A_k = np.nan_to_num(sigma_sq_A_k, nan=0.0, posinf=0.0, neginf=0.0)
    sigma_sq_A_c = float(np.mean(sigma_sq_A_k))
    sigma_A_c = floor_sigma_a_c(max(np.sqrt(max(sigma_sq_A_c, 1e-10)), 0.01))
    a_hat_k = x_bar_k - b_A
    mu_c = float(np.mean(a_hat_k))
    between_var_raw = float(np.var(a_hat_k, ddof=1))
    noise_correction = sigma_sq_A_c / T
    tau_sq_c = max(between_var_raw - noise_correction, 0.01)
    tau_c = np.sqrt(tau_sq_c)
    return CalibratedASVParams(
        mu_c=mu_c,
        tau_c=float(tau_c),
        b_A=b_A,
        sigma_A_c=sigma_A_c,
        num_keywords=K,
        num_periods=T,
    )


def calibrate_asv_from_list(
    historical_asv: List[List[float]],
    b_A: float = 0.0,
    min_periods: int = 2,
) -> Optional[CalibratedASVParams]:
    """Calibrate ASV params from list of lists. Truncates to min length."""
    if not historical_asv:
        return None
    valid = [row for row in historical_asv if len(row) >= min_periods]
    if len(valid) < 2:
        return None
    min_len = min(len(row) for row in valid)
    truncated = [row[:min_len] for row in valid]
    arr = np.array(truncated)
    return calibrate_asv_from_matrix(arr, b_A=b_A)


def calibrate_sv_per_intent(
    intent_to_historical_sv: Dict[str, List[List[float]]],
    b_S: float = 0.0,
    min_keywords: int = 2,
) -> Dict[str, CalibratedSVParams]:
    """
    Calibrate SV params per intent class (case1-style).
    For each intent c with keyword set Kc, estimates (νc, ωc, σS,c, b_S) from historical SV.
    Intents with too few keywords use pooled fallback.
    """
    result: Dict[str, CalibratedSVParams] = {}
    pooled_sv: List[List[float]] = []

    for intent_id, sv_list in intent_to_historical_sv.items():
        pooled_sv.extend(sv_list)
        if len(sv_list) >= min_keywords:
            cal = calibrate_sv_from_list(sv_list, b_S=b_S)
            if cal is not None:
                result[intent_id] = cal

    default_cal = (
        calibrate_sv_from_list(pooled_sv, b_S=b_S)
        if pooled_sv and len(pooled_sv) >= min_keywords
        else None
    )

    for intent_id in intent_to_historical_sv:
        if intent_id not in result:
            result[intent_id] = default_cal or CalibratedSVParams(
                nu_c=10.82, omega_c=3.0, b_S=b_S, sigma_S_c=0.20,
                num_keywords=0, num_periods=0,
            )

    return result


def calibrate_asv_per_intent(
    intent_to_historical_asv: Dict[str, List[List[float]]],
    b_A: float = 0.0,
    min_keywords: int = 2,
) -> Dict[str, CalibratedASVParams]:
    """
    Calibrate ASV params per intent class (case1-style).
    For each intent c, estimates (μc, τc, σA,c, b_A) from historical ASV.
    """
    result: Dict[str, CalibratedASVParams] = {}
    pooled_asv: List[List[float]] = []

    for intent_id, asv_list in intent_to_historical_asv.items():
        pooled_asv.extend(asv_list)
        if len(asv_list) >= min_keywords:
            cal = calibrate_asv_from_list(asv_list, b_A=b_A)
            if cal is not None:
                result[intent_id] = cal

    default_cal = (
        calibrate_asv_from_list(pooled_asv, b_A=b_A)
        if pooled_asv and len(pooled_asv) >= min_keywords
        else None
    )

    for intent_id in intent_to_historical_asv:
        if intent_id not in result:
            result[intent_id] = default_cal or CalibratedASVParams(
                mu_c=np.log(1200), tau_c=0.60, b_A=b_A, sigma_A_c=0.35,
                num_keywords=0, num_periods=0,
            )

    return result


@dataclass
class RhoCoefficients:
    """Logistic model coefficients for ρ(k) = 1/(1+e^ℓ), ℓ = α0 + α1·z1 + α2·z2."""
    alpha0: float
    alpha1: float
    alpha2: float


# Default coefficients (spec dry-run used fixed ρ=0.25; these yield moderate ρ for typical z)
DEFAULT_RHO_COEFFS = RhoCoefficients(alpha0=-0.30, alpha1=0.80, alpha2=0.40)

# Floors for calibrated coupling: keep empirical values when above defaults, else use defaults
RHO_CALIBRATION_FLOOR = 0.25
ETA_CALIBRATION_FLOOR = 1.3
MU_ETA_CALIBRATION_FLOOR = math.log(ETA_CALIBRATION_FLOOR)

# Floor ASV measurement noise: higher σ_A,c → less trust in point ASV in fusion (default 0.5)
SIGMA_A_CALIBRATION_FLOOR = 0.5


def floor_sigma_a_c(sigma_A_c: float) -> float:
    """σ_A,c := max(calibrated, SIGMA_A_CALIBRATION_FLOOR)."""
    return max(float(sigma_A_c), SIGMA_A_CALIBRATION_FLOOR)


def _logit(p: float) -> float:
    """Inverse sigmoid: log(p/(1-p)). Clamp p to avoid log(0)."""
    p = max(1e-6, min(1 - 1e-6, p))
    return math.log(p / (1.0 - p))


def _logistic(x: float) -> float:
    """Sigmoid: 1/(1+e^x). Clamp for numerical stability."""
    x = max(-20, min(20, x))
    return 1.0 / (1.0 + math.exp(x))


def estimate_rho_empirical_per_keyword(
    sv_by_month: Dict[Tuple[str, int, int], float],
    asv_by_month: Dict[Tuple[str, int, int], float],
    eta_mean: float,
    *,
    rho_floor: float = RHO_CALIBRATION_FLOOR,
) -> Dict[str, float]:
    """
    Per-keyword empirical AI share from paired monthly history.

    ρ_emp(k) = mean_t(ASV_k,t / (η·SV_k,t)), floored at rho_floor.
    """
    kw_to_ratios: Dict[str, List[float]] = {}
    for (kw, _y, _m), asv in asv_by_month.items():
        sv = sv_by_month.get((kw, _y, _m))
        if sv is None or sv < 1 or asv < 1:
            continue
        ratio = asv / (eta_mean * sv)
        kw_to_ratios.setdefault(kw, []).append(ratio)

    rho_emp: Dict[str, float] = {}
    for kw, ratios in kw_to_ratios.items():
        rho_emp[kw] = max(rho_floor, float(np.mean(ratios)))
    return rho_emp


def apply_rho_intent_cluster_priors(
    keywords: List[str],
    rho_empirical: Dict[str, float],
    intent_to_keywords: Dict[str, List[str]],
    *,
    default_rho: float = RHO_CALIBRATION_FLOOR,
) -> Dict[str, float]:
    """
    Assign ρ per keyword: empirical where history exists, else intent-cluster median.

    Fallback order: intent median → global median of empirical values → default_rho.
    """
    global_prior = (
        float(np.median(list(rho_empirical.values())))
        if rho_empirical
        else default_rho
    )

    intent_priors: Dict[str, float] = {}
    for intent_id, intent_kws in intent_to_keywords.items():
        vals = [rho_empirical[kw] for kw in intent_kws if kw in rho_empirical]
        if vals:
            intent_priors[intent_id] = float(np.median(vals))

    kw_to_intent: Dict[str, str] = {}
    for intent_id, intent_kws in intent_to_keywords.items():
        for kw in intent_kws:
            kw_to_intent.setdefault(kw, intent_id)

    rho_by_keyword: Dict[str, float] = {}
    for kw in keywords:
        if kw in rho_empirical:
            rho_by_keyword[kw] = rho_empirical[kw]
            continue
        intent_id = kw_to_intent.get(kw)
        if intent_id and intent_id in intent_priors:
            rho_by_keyword[kw] = intent_priors[intent_id]
        else:
            rho_by_keyword[kw] = global_prior
    return rho_by_keyword


def _populate_sv_by_month_from_results(
    sv_results: List,
    sv_by_month: Dict[Tuple[str, int, int], float],
) -> None:
    """Extract monthly SV history from volume fetch results into sv_by_month."""
    for r in sv_results:
        kw = r.keyword if hasattr(r, "keyword") else (r.get("keyword", "") if isinstance(r, dict) else "")
        if not kw:
            continue
        monthly = getattr(r, "monthly_searches", None) if not isinstance(r, dict) else r.get("monthly_searches")
        monthly = monthly or []
        for m in monthly:
            y, mo = m.get("year"), m.get("month")
            v = m.get("search_volume")
            if y is not None and mo is not None and v is not None and v >= 1:
                sv_by_month[(kw, y, mo)] = float(v)
        if not monthly and (getattr(r, "search_volume", 0) or 0) >= 1:
            now = datetime.datetime.utcnow()
            y1, m1 = now.year, now.month
            m2 = m1 - 1 if m1 > 1 else 12
            y2 = y1 if m1 > 1 else y1 - 1
            v = float(max(getattr(r, "search_volume", 1), 1))
            sv_by_month[(kw, y2, m2)] = v
            sv_by_month[(kw, y1, m1)] = v


def _populate_asv_by_month_from_items(
    asv_items: List[dict],
    asv_by_month: Dict[Tuple[str, int, int], float],
) -> None:
    """Extract monthly ASV history from ASV fetch results into asv_by_month."""
    for item in asv_items:
        kw = item.get("keyword", "")
        if not kw:
            continue
        monthly = item.get("ai_monthly_searches") or item.get("monthly_searches") or []
        for m in monthly:
            y, mo = m.get("year"), m.get("month")
            v = m.get("ai_search_volume") or m.get("search_volume")
            if y is not None and mo is not None and v is not None and v >= 1:
                asv_by_month[(kw, y, mo)] = float(v)
        if not monthly:
            v = item.get("ai_search_volume") or item.get("search_volume")
            if v is not None and float(v) >= 1:
                now = datetime.datetime.utcnow()
                y1, m1 = now.year, now.month
                m2 = m1 - 1 if m1 > 1 else 12
                y2 = y1 if m1 > 1 else y1 - 1
                vol = float(max(v, 1))
                asv_by_month[(kw, y2, m2)] = vol
                asv_by_month[(kw, y1, m1)] = vol


def compute_rho(
    cpc: float,
    comp: float,
    coeffs: Optional[RhoCoefficients] = None,
) -> float:
    """
    Compute AI-share ρ(k) from features via logistic model (Step 7).

    ρ(k) = σ(−ℓ) = 1/(1+e^ℓ)
    ℓ = α0 + α1·z1 + α2·z2
    z1 = log(1+CPC), z2 = log(1+Comp)

    Args:
        cpc: Cost-per-click (USD)
        comp: Competition (0-1)
        coeffs: Logistic coefficients. Uses defaults if None.

    Returns:
        ρ ∈ (0, 1)
    """
    coeffs = coeffs or DEFAULT_RHO_COEFFS
    z1 = math.log(1.0 + max(0, cpc or 0))
    z2 = math.log(1.0 + max(0, comp or 0))
    # Standardize z1 to avoid scale explosion (spec note: z1 can be very large)
    # Use simple scaling: z1/10 to keep ℓ in reasonable range
    z1_scaled = z1 / 10.0
    ell = coeffs.alpha0 + coeffs.alpha1 * z1_scaled + coeffs.alpha2 * z2
    rho = _logistic(-ell)
    return max(1e-6, min(1 - 1e-6, rho))


def estimate_rho_coeffs_from_data(
    sv_by_month: Dict[Tuple[str, int, int], float],
    asv_by_month: Dict[Tuple[str, int, int], float],
    keyword_to_cpc_comp: Dict[str, Tuple[float, float]],
    eta_mean: float,
    min_keywords: int = 5,
) -> RhoCoefficients:
    """
    Estimate rho_coeffs (α0, α1, α2) from historical SV/ASV via logistic regression.

    Step 7: ρ(k) = σ(−ℓ), ℓ = α0 + α1·z1 + α2·z2, with z1=log(1+CPC), z2=log(1+Comp).
    Empirical target: ρ_emp(k) = mean_t(ASV_k,t / (η·SV_k,t)) from A⋆ ≈ ρ·η·S⋆.
    Fit on logit scale: logit(ρ_emp) = α0 + α1·z1 + α2·z2 (least squares).

    Args:
        sv_by_month: (keyword, year, month) -> SV
        asv_by_month: (keyword, year, month) -> ASV
        keyword_to_cpc_comp: keyword -> (cpc, competition)
        eta_mean: exp(μ_η) for scaling (η in A⋆ = ρ·η·S⋆)
        min_keywords: Minimum keywords with valid data to fit (else return defaults)

    Returns:
        RhoCoefficients
    """
    # Build empirical ρ per keyword: ρ_emp = mean(ASV / (η * SV))
    kw_to_ratios: Dict[str, List[float]] = {}
    for (kw, y, m), asv in asv_by_month.items():
        sv = sv_by_month.get((kw, y, m))
        if sv is None or sv < 1 or asv < 1:
            continue
        ratio = asv / (eta_mean * sv)
        kw_to_ratios.setdefault(kw, []).append(ratio)

    # Keywords with both empirical ρ and (cpc, comp) features
    keywords_valid: List[str] = []
    rho_emp_list: List[float] = []
    z1_list: List[float] = []
    z2_list: List[float] = []

    for kw, ratios in kw_to_ratios.items():
        if kw not in keyword_to_cpc_comp:
            continue
        cpc, comp = keyword_to_cpc_comp[kw]
        rho_emp = float(np.mean(ratios))
        rho_emp = max(1e-4, min(1 - 1e-4, rho_emp))
        z1 = math.log(1.0 + max(0, cpc or 0)) / 10.0
        z2 = math.log(1.0 + max(0, comp or 0))
        keywords_valid.append(kw)
        rho_emp_list.append(rho_emp)
        z1_list.append(z1)
        z2_list.append(z2)

    if len(keywords_valid) < min_keywords:
        return DEFAULT_RHO_COEFFS

    # Fit: logit(ρ_emp) = α0 + α1*z1 + α2*z2  =>  ℓ = -logit(ρ_emp) for ρ = σ(-ℓ)
    # So ℓ = α0 + α1*z1 + α2*z2 should equal -logit(ρ_emp)
    Y = np.array([-_logit(r) for r in rho_emp_list])
    X = np.column_stack([np.ones(len(Y)), z1_list, z2_list])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
        alpha0, alpha1, alpha2 = float(beta[0]), float(beta[1]), float(beta[2])
        # Clamp to avoid extreme coefficients
        alpha0 = max(-5, min(5, alpha0))
        alpha1 = max(-5, min(5, alpha1))
        alpha2 = max(-5, min(5, alpha2))
        return RhoCoefficients(alpha0=alpha0, alpha1=alpha1, alpha2=alpha2)
    except Exception:
        return DEFAULT_RHO_COEFFS


@dataclass
class CalibratedEta:
    """Calibrated η prior: log η ~ N(μ_η, σ²_η)."""
    mu_eta: float
    sigma_eta: float
    num_samples: int
    var_u: float = 0.0  # variance of uplift residuals


def calibrate_eta_from_residuals(
    residuals: List[float],
    sigma_u_sq: Optional[float] = None,
) -> CalibratedEta:
    """
    Estimate (μ_η, σ²_η) from uplift residuals (Step 8a).

    u_k,t = log(ASV_k,t) - log(SV_k,t) - log(ρ_k,t)
    u_k,t ≈ log η + noise

    μ_η = mean(u)
    σ²_η = max(0, Var(u) - E[σ²_u])

    Args:
        residuals: List of u values (one per keyword-period)
        sigma_u_sq: Average measurement variance. If None, uses Var(u)/(N-1) as proxy.

    Returns:
        CalibratedEta
    """
    if not residuals:
        return CalibratedEta(mu_eta=math.log(1.3), sigma_eta=0.25, num_samples=0, var_u=0.0)

    arr = np.array(residuals)
    mu_eta = float(np.mean(arr))
    var_u = float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0

    if sigma_u_sq is not None:
        sigma_eta_sq = max(0, var_u - sigma_u_sq)
    else:
        sigma_eta_sq = max(0, var_u * 0.5)  # heuristic: assume half is signal

    sigma_eta = max(0.01, math.sqrt(sigma_eta_sq))
    return CalibratedEta(mu_eta=mu_eta, sigma_eta=sigma_eta, num_samples=len(residuals), var_u=var_u)


def apply_rho_eta_floors(
    rho_by_keyword: Dict[str, float],
    calibrated_eta: CalibratedEta,
    *,
    rho_floor: float = RHO_CALIBRATION_FLOOR,
    eta_floor: float = ETA_CALIBRATION_FLOOR,
) -> Tuple[Dict[str, float], CalibratedEta, Dict[str, int]]:
    """
    Enforce minimum ρ and η after calibration.

    - Per-keyword ρ(k) := max(calibrated ρ, rho_floor)  (default 0.25)
    - Global μ_η := max(calibrated μ_η, log(eta_floor))  (default log(1.3))

    Calibrated values strictly above the floors are unchanged.
    """
    mu_eta_floor = math.log(eta_floor)
    rho_raised = sum(1 for r in rho_by_keyword.values() if float(r) < rho_floor)
    floored_rho = {kw: max(float(r), rho_floor) for kw, r in rho_by_keyword.items()}
    eta_raised = int(float(calibrated_eta.mu_eta) < mu_eta_floor)
    floored_mu_eta = max(float(calibrated_eta.mu_eta), mu_eta_floor)
    floored_eta = CalibratedEta(
        mu_eta=floored_mu_eta,
        sigma_eta=calibrated_eta.sigma_eta,
        num_samples=calibrated_eta.num_samples,
        var_u=calibrated_eta.var_u,
    )
    return floored_rho, floored_eta, {
        "rho_keywords_raised": rho_raised,
        "eta_floor_applied": eta_raised,
    }


def apply_sigma_a_floor_to_asv_params_by_intent(
    asv_params_by_intent: Dict[str, CalibratedASVParams],
) -> int:
    """Raise σ_A,c per intent to SIGMA_A_CALIBRATION_FLOOR when calibrated lower."""
    raised = 0
    for intent_id, p in list(asv_params_by_intent.items()):
        if p.sigma_A_c < SIGMA_A_CALIBRATION_FLOOR:
            raised += 1
            asv_params_by_intent[intent_id] = CalibratedASVParams(
                mu_c=p.mu_c,
                tau_c=p.tau_c,
                b_A=p.b_A,
                sigma_A_c=SIGMA_A_CALIBRATION_FLOOR,
                num_keywords=p.num_keywords,
                num_periods=p.num_periods,
            )
    return raised


def apply_rho_eta_floors_to_calibration_dict(cal: Dict) -> Dict[str, int]:
    """Apply ρ/η and σ_A,c floors to a loaded calibration dict (mutates cal in place)."""
    stats = {"rho_keywords_raised": 0, "eta_floor_applied": 0, "sigma_a_intents_raised": 0}
    rho_map = cal.get("rho_by_keyword")
    if isinstance(rho_map, dict):
        rho_raised = sum(1 for r in rho_map.values() if float(r) < RHO_CALIBRATION_FLOOR)
        cal["rho_by_keyword"] = {
            kw: max(float(r), RHO_CALIBRATION_FLOOR) for kw, r in rho_map.items()
        }
        stats["rho_keywords_raised"] = rho_raised
    if "mu_eta" in cal:
        mu = float(cal["mu_eta"])
        if mu < MU_ETA_CALIBRATION_FLOOR:
            cal["mu_eta"] = MU_ETA_CALIBRATION_FLOOR
            stats["eta_floor_applied"] = 1
    asv_map = cal.get("asv_params_by_intent")
    if isinstance(asv_map, dict):
        for intent_id, p in asv_map.items():
            if isinstance(p, dict) and "sigma_A_c" in p:
                raw = float(p["sigma_A_c"])
                if raw < SIGMA_A_CALIBRATION_FLOOR:
                    p["sigma_A_c"] = SIGMA_A_CALIBRATION_FLOOR
                    stats["sigma_a_intents_raised"] += 1
    # Backward compat: single global asv_params
    legacy = cal.get("asv_params")
    if isinstance(legacy, dict) and "sigma_A_c" in legacy:
        raw = float(legacy["sigma_A_c"])
        if raw < SIGMA_A_CALIBRATION_FLOOR:
            legacy["sigma_A_c"] = SIGMA_A_CALIBRATION_FLOOR
            stats["sigma_a_intents_raised"] += 1
    return stats


def build_uplift_residuals(
    sv_by_month: Dict[Tuple[str, int, int], float],
    asv_by_month: Dict[Tuple[str, int, int], float],
    rho_by_keyword: Dict[str, float],
) -> List[float]:
    """
    Build uplift residuals u_k,t for calibration keywords over time.

    u_k,t = log(ASV_k,t) - log(SV_k,t) - log(ρ_k)

    Args:
        sv_by_month: (keyword, year, month) -> SV value
        asv_by_month: (keyword, year, month) -> ASV value
        rho_by_keyword: keyword -> ρ(k)

    Returns:
        List of residuals (only for (k,t) where both SV and ASV exist)
    """
    residuals = []
    for (kw, y, m), asv in asv_by_month.items():
        sv = sv_by_month.get((kw, y, m))
        if sv is None or sv < 1 or asv < 1:
            continue
        rho = rho_by_keyword.get(kw, 0.25)
        rho = max(1e-6, min(1 - 1e-6, rho))
        u = math.log(asv) - math.log(sv) - math.log(rho)
        residuals.append(u)
    return residuals


def _build_historical_matrices(
    sv_by_month: Dict[Tuple[str, int, int], float],
    asv_by_month: Dict[Tuple[str, int, int], float],
) -> Tuple[List[List[float]], List[List[float]]]:
    """Build historical_sv and historical_asv as list of lists (keywords × periods)."""
    kw_to_sv: Dict[str, List[Tuple[int, int, float]]] = {}
    kw_to_asv: Dict[str, List[Tuple[int, int, float]]] = {}
    for (kw, y, m), v in sv_by_month.items():
        if v >= 1:
            kw_to_sv.setdefault(kw, []).append((y, m, float(v)))
    for (kw, y, m), v in asv_by_month.items():
        if v >= 1:
            kw_to_asv.setdefault(kw, []).append((y, m, float(v)))
    historical_sv: List[List[float]] = []
    for kw in sorted(kw_to_sv):
        sv_vals = sorted(kw_to_sv[kw], key=lambda x: (x[0], x[1]))
        historical_sv.append([v for _, _, v in sv_vals])
    historical_asv: List[List[float]] = []
    for kw in sorted(kw_to_asv):
        asv_vals = sorted(kw_to_asv[kw], key=lambda x: (x[0], x[1]))
        historical_asv.append([v for _, _, v in asv_vals])
    return historical_sv, historical_asv


def _build_intent_to_historical_matrices(
    sv_by_month: Dict[Tuple[str, int, int], float],
    asv_by_month: Dict[Tuple[str, int, int], float],
    intent_to_keywords: Dict[str, List[str]],
) -> Tuple[Dict[str, List[List[float]]], Dict[str, List[List[float]]]]:
    """
    Build intent -> historical_sv and intent -> historical_asv.
    intent_to_keywords: intent_id -> list of keywords belonging to that intent.
    """
    kw_to_sv: Dict[str, List[Tuple[int, int, float]]] = {}
    kw_to_asv: Dict[str, List[Tuple[int, int, float]]] = {}
    for (kw, y, m), v in sv_by_month.items():
        if v >= 1:
            kw_to_sv.setdefault(kw, []).append((y, m, float(v)))
    for (kw, y, m), v in asv_by_month.items():
        if v >= 1:
            kw_to_asv.setdefault(kw, []).append((y, m, float(v)))

    intent_to_sv: Dict[str, List[List[float]]] = {}
    intent_to_asv: Dict[str, List[List[float]]] = {}
    for intent_id, keywords in intent_to_keywords.items():
        sv_list: List[List[float]] = []
        asv_list: List[List[float]] = []
        for kw in keywords:
            if kw in kw_to_sv:
                sv_vals = sorted(kw_to_sv[kw], key=lambda x: (x[0], x[1]))
                sv_list.append([v for _, _, v in sv_vals])
            if kw in kw_to_asv:
                asv_vals = sorted(kw_to_asv[kw], key=lambda x: (x[0], x[1]))
                asv_list.append([v for _, _, v in asv_vals])
        intent_to_sv[intent_id] = sv_list
        intent_to_asv[intent_id] = asv_list
    return intent_to_sv, intent_to_asv


def _build_intent_to_keywords(extractions: List[dict]) -> Dict[str, List[str]]:
    """Build intent_id -> list of unique keywords from extractions (prompts with intent)."""
    intent_to_kw: Dict[str, List[str]] = {}
    for ext in extractions:
        intent_id = ext.get("intent_cluster_id") or "_unknown"
        for kw_obj in ext.get("keywords", []):
            kw = kw_obj.get("keyword") if isinstance(kw_obj, dict) else getattr(kw_obj, "keyword", None)
            if kw:
                intent_to_kw.setdefault(intent_id, []).append(kw)
    return {i: list(dict.fromkeys(kws)) for i, kws in intent_to_kw.items()}


async def run_calibration(
    keywords: List[str],
    sv_client: "DataForSEOSVClient",
    asv_client: "DataForSEOASVClient",
    location_code: int = 2840,
    language_code: str = "en",
    rho_coeffs: Optional[RhoCoefficients] = None,
    sv_results: Optional[List] = None,
    asv_items: Optional[List[dict]] = None,
    extractions: Optional[List[dict]] = None,
) -> Tuple[
    Dict[str, float],
    CalibratedEta,
    Optional[RhoCoefficients],
    Dict[str, CalibratedSVParams],
    Dict[str, CalibratedASVParams],
    List[float],
]:
    """
    Run full calibration: fetch SV+ASV monthly data (or use provided), compute ρ per keyword,
    calibrate η, and calibrate SV/ASV measurement model params from historical data (case1-style).

    Returns:
        rho_by_keyword, calibrated_eta, rho_coeffs, calibrated_sv, calibrated_asv, residuals
    """
    if sv_results is None:
        sv_results = await sv_client.get_volume(keywords, location_code, language_code)
    if asv_items is None:
        asv_items = await asv_client.get_volume_with_history(
            keywords, location_code, language_code
        )

    sv_by_month: Dict[Tuple[str, int, int], float] = {}
    asv_by_month: Dict[Tuple[str, int, int], float] = {}
    _populate_sv_by_month_from_results(sv_results, sv_by_month)
    _populate_asv_by_month_from_items(asv_items, asv_by_month)

    intent_to_keywords = _build_intent_to_keywords(extractions) if extractions else {}

    # Pass 1: initial η with uniform ρ prior
    rho_by_keyword: Dict[str, float] = {kw: RHO_CALIBRATION_FLOOR for kw in keywords}
    residuals = build_uplift_residuals(sv_by_month, asv_by_month, rho_by_keyword)
    calibrated_eta = calibrate_eta_from_residuals(residuals)

    # Pass 2: empirical ρ from history + intent-cluster priors for cold start
    eta_mean = math.exp(calibrated_eta.mu_eta)
    rho_empirical = estimate_rho_empirical_per_keyword(
        sv_by_month, asv_by_month, eta_mean, rho_floor=RHO_CALIBRATION_FLOOR
    )
    rho_by_keyword = apply_rho_intent_cluster_priors(
        keywords,
        rho_empirical,
        intent_to_keywords,
        default_rho=RHO_CALIBRATION_FLOOR,
    )

    # Pass 3: refit η with final ρ
    residuals = build_uplift_residuals(sv_by_month, asv_by_month, rho_by_keyword)
    calibrated_eta = calibrate_eta_from_residuals(residuals)

    # Calibrate SV and ASV params: per-intent when extractions have intent info, else pooled
    if intent_to_keywords:
        intent_to_sv, intent_to_asv = _build_intent_to_historical_matrices(
            sv_by_month, asv_by_month, intent_to_keywords
        )
        sv_params_by_intent = calibrate_sv_per_intent(intent_to_sv, b_S=0.0)
        asv_params_by_intent = calibrate_asv_per_intent(intent_to_asv, b_A=0.0)
    else:
        historical_sv, historical_asv = _build_historical_matrices(sv_by_month, asv_by_month)
        calibrated_sv = calibrate_sv_from_list(historical_sv, b_S=0.0)
        calibrated_asv = calibrate_asv_from_list(historical_asv, b_A=0.0)
        sv_params_by_intent = {"_global": calibrated_sv} if calibrated_sv else {}
        asv_params_by_intent = {"_global": calibrated_asv} if calibrated_asv else {}
        if not sv_params_by_intent:
            sv_params_by_intent = {"_global": CalibratedSVParams(nu_c=10.82, omega_c=3.0, b_S=0.0, sigma_S_c=0.20, num_keywords=0, num_periods=0)}
        if not asv_params_by_intent:
            asv_params_by_intent = {"_global": CalibratedASVParams(mu_c=np.log(1200), tau_c=0.60, b_A=0.0, sigma_A_c=0.35, num_keywords=0, num_periods=0)}

    rho_by_keyword, calibrated_eta, floor_stats = apply_rho_eta_floors(rho_by_keyword, calibrated_eta)
    sigma_a_raised = apply_sigma_a_floor_to_asv_params_by_intent(asv_params_by_intent)
    if (
        floor_stats["rho_keywords_raised"]
        or floor_stats["eta_floor_applied"]
        or sigma_a_raised
    ):
        print(
            f"  Applied calibration floors: "
            f"ρ≥{RHO_CALIBRATION_FLOOR} ({floor_stats['rho_keywords_raised']} kw raised), "
            f"η≥{ETA_CALIBRATION_FLOOR} ({'yes' if floor_stats['eta_floor_applied'] else 'no'}), "
            f"σ_A,c≥{SIGMA_A_CALIBRATION_FLOOR} ({sigma_a_raised} intents raised)",
            flush=True,
        )

    return rho_by_keyword, calibrated_eta, None, sv_params_by_intent, asv_params_by_intent, residuals


def load_calibration(path: Path) -> Dict:
    """Load calibration JSON. Expected keys: mu_eta, sigma_eta, rho_coeffs (optional)."""
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_calibration(
    path: Path,
    mu_eta: float,
    sigma_eta: float,
    rho_coeffs: Optional[RhoCoefficients] = None,
    rho_by_keyword: Optional[Dict[str, float]] = None,
    num_samples: int = 0,
    var_u: Optional[float] = None,
    residuals: Optional[List[float]] = None,
    keywords: Optional[List[str]] = None,
    location_code: Optional[int] = None,
    language_code: Optional[str] = None,
    sv_params_by_intent: Optional[Dict[str, CalibratedSVParams]] = None,
    asv_params_by_intent: Optional[Dict[str, CalibratedASVParams]] = None,
) -> None:
    """Save all calibrated parameters to JSON.
    sv_params_by_intent: intent_id -> CalibratedSVParams
    asv_params_by_intent: intent_id -> CalibratedASVParams
    """
    from case2_demand.util.io import write_json
    from datetime import datetime, timezone

    obj: Dict = {
        "mu_eta": mu_eta,
        "sigma_eta": sigma_eta,
        "num_samples": num_samples,
    }
    if sv_params_by_intent:
        obj["sv_params_by_intent"] = {
            intent_id: {
                "nu_c": p.nu_c,
                "omega_c": p.omega_c,
                "b_S": p.b_S,
                "sigma_S_c": p.sigma_S_c,
                "num_keywords": p.num_keywords,
                "num_periods": p.num_periods,
            }
            for intent_id, p in sv_params_by_intent.items()
        }
    if asv_params_by_intent:
        obj["asv_params_by_intent"] = {
            intent_id: {
                "mu_c": p.mu_c,
                "tau_c": p.tau_c,
                "b_A": p.b_A,
                "sigma_A_c": p.sigma_A_c,
                "num_keywords": p.num_keywords,
                "num_periods": p.num_periods,
            }
            for intent_id, p in asv_params_by_intent.items()
        }
    if rho_coeffs:
        obj["rho_coeffs"] = {
            "alpha0": rho_coeffs.alpha0,
            "alpha1": rho_coeffs.alpha1,
            "alpha2": rho_coeffs.alpha2,
        }
    if rho_by_keyword:
        obj["rho_by_keyword"] = rho_by_keyword
    if var_u is not None:
        obj["var_u"] = var_u
    if residuals is not None:
        obj["residuals"] = residuals
    if keywords is not None:
        obj["keywords"] = keywords
    if location_code is not None:
        obj["location_code"] = location_code
    if language_code is not None:
        obj["language_code"] = language_code
    obj["calibrated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(path, obj)
