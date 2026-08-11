"""Case 2: Bayesian fusion of SV (classic) + ASV (AI) sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from case2_demand.schemas import KeywordEstimate


@dataclass
class Case2Hyperparameters:
    """Hyperparameters for Case 2 SV+ASV fusion."""
    # SV sensor
    nu_c: float  # νc = log(prior median SV)
    omega_c: float  # ωc
    b_S: float  # bS
    sigma_S_c: float  # σS,c

    # ASV sensor
    b_A: float  # bA
    sigma_A_c: float  # σA,c

    # Coupling
    delta_c: float  # δc
    sigma_delta: float  # σδ
    beta: float  # softmax sharpness
    rho: float  # AI-share ρ ∈ (0,1)
    mu_eta: float  # log(η) prior mean
    sigma_eta: float  # log(η) prior std (ση)


class Case2Estimator:
    """Bayesian estimator fusing SV and ASV sensors."""

    def __init__(self, hp: Case2Hyperparameters):
        self.hp = hp

    def estimate_demand(
        self,
        prompt: str,
        keywords: List[str],
        similarities: List[float],
        sv_values: List[float],
        asv_values: List[float],
        rho_by_keyword: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, float, float, Tuple[float, float], List[KeywordEstimate], Dict[str, float]]:
        """Estimate AI demand for a prompt using SV+ASV fusion."""
        weights = self._compute_weights(keywords, similarities)
        yi = [np.log(max(sv, 1)) for sv in sv_values]
        xi = [np.log(max(asv, 1)) for asv in asv_values]

        omega_sq = max(self.hp.omega_c ** 2, 1e-10)
        sigma_S_sq = max(self.hp.sigma_S_c ** 2, 1e-10)
        sigma_A_sq = max(self.hp.sigma_A_c ** 2, 1e-10)
        sigma_delta_sq = max(self.hp.sigma_delta ** 2, 1e-10)

        # Step 5-6: SV posterior
        sigma_s_post_sq = 1.0 / (1.0 / omega_sq + 1.0 / sigma_S_sq)
        mu_s_post = [
            sigma_s_post_sq * (self.hp.nu_c / omega_sq + (y - self.hp.b_S) / sigma_S_sq)
            for y in yi
        ]

        # Step 9: Coupling prior for ai (per-keyword ρ when calibrated)
        rho_vals = [
            (rho_by_keyword or {}).get(kw, self.hp.rho) for kw in keywords
        ]
        log_rho_vals = [np.log(max(r, 1e-10)) for r in rho_vals]
        log_eta = self.hp.mu_eta  # use prior mean
        sigma_a_cpl_sq = sigma_s_post_sq + sigma_delta_sq
        mu_a_cpl = [
            m + log_rho + log_eta + self.hp.delta_c
            for m, log_rho in zip(mu_s_post, log_rho_vals)
        ]

        # Step 12: Fuse coupling prior + ASV likelihood
        sigma_a_post_sq = 1.0 / (1.0 / sigma_a_cpl_sq + 1.0 / sigma_A_sq)
        mu_a_post = [
            sigma_a_post_sq * (mu_a_cpl[i] / sigma_a_cpl_sq + (xi[i] - self.hp.b_A) / sigma_A_sq)
            for i in range(len(keywords))
        ]

        sigma_a_post = np.sqrt(sigma_a_post_sq)
        keyword_estimates: List[KeywordEstimate] = []
        for kw, mu, sigma_sq in zip(keywords, mu_a_post, [sigma_a_post_sq] * len(keywords)):
            A_median = np.exp(mu)
            A_mean = np.exp(mu + 0.5 * sigma_sq)
            variance = (np.exp(sigma_sq) - 1) * np.exp(2 * mu + sigma_sq)
            z_90 = 1.645
            interval = (
                max(0, A_mean - z_90 * np.sqrt(variance)),
                A_mean + z_90 * np.sqrt(variance),
            )
            keyword_estimates.append(
                KeywordEstimate(
                    keyword=kw,
                    mu_post=mu,
                    sigma_post=sigma_a_post,
                    A_median=A_median,
                    A_mean=A_mean,
                    variance=variance,
                    interval_90=interval,
                )
            )

        Y_median, Y_mean, Y_std, interval = self._aggregate_to_prompt(weights, keyword_estimates)
        return Y_median, Y_mean, Y_std, interval, keyword_estimates, weights

    def _compute_weights(self, keywords: List[str], similarities: List[float]) -> Dict[str, float]:
        w_tilde = [np.exp(self.hp.beta * s) for s in similarities]
        W_sum = sum(w_tilde)
        return dict(zip(keywords, [w / W_sum for w in w_tilde]))

    def _aggregate_to_prompt(
        self,
        weights: Dict[str, float],
        keyword_estimates: List[KeywordEstimate],
    ) -> Tuple[float, float, float, Tuple[float, float]]:
        w_list = list(weights.values())
        Y_median = sum(w * est.A_median for w, est in zip(w_list, keyword_estimates))
        Y_mean = sum(w * est.A_mean for w, est in zip(w_list, keyword_estimates))
        Y_var = sum((w ** 2) * est.variance for w, est in zip(w_list, keyword_estimates))
        Y_std = np.sqrt(Y_var)
        z_90 = 1.645
        interval = (max(0, Y_mean - z_90 * Y_std), Y_mean + z_90 * Y_std)
        return Y_median, Y_mean, Y_std, interval
