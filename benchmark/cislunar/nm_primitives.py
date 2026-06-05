"""
Nervous Machine framework primitives — standalone extraction.

This module is a verbatim, dependency-free extraction of the two functions
that constitute the framework's per-edge learning math, as implemented in
the operational MCP server (~/NM-learning-loop/mcp_validation.py, class
ValidationMCPServerEnhanced). It is provided so this benchmark is
self-contained and reproducible without the MCP server, MongoDB, or any
network dependency.

The math here is the source of truth for the four primitives:
    ε  (error signal)     — caller-supplied signed dimensionless residual
    η  (learning rate)    — sigmoid-decreasing function of certainty Z
    ΔW (weight update)    — ΔW = -η · ε · W_STEP, W clamped to [-1, +1]
    Z  (certainty)        — evolves on the distribution of recent signed ε's
                            with an SEM-scaled bias-significance test

If this disagrees with mcp_validation.py, the MCP server wins; this file
is a mirror for reproducibility, not an independent implementation.

Constants below are the framework defaults. They are calibrated for a
relative-residual ε convention (typical |ε| ~ 0.1). A caller using a
different ε convention (e.g. z-score ε, typical |ε| ~ 1) must rescale
W_STEP, Z_BIAS_TOL, and Z_STD_TOL together — see README.md and the
learn_gracefo_full_year.py pipeline, which uses z-score ε.
"""

import math
from datetime import datetime, timezone


# --- Framework constants (mcp_validation.py:32-41) ---
Z_WINDOW = 10          # recent observations considered for the bias test
Z_MIN_HISTORY = 5      # don't move Z until at least this many ε's
Z_BIAS_TOL = 0.05      # |mean(ε_window)| absolute floor for bias significance
Z_STD_TOL = 0.15       # std(ε_window) must be ≤ this for Z to climb
Z_UP_STEP = 0.02       # asymmetric: easier to lose certainty than to gain
Z_DOWN_STEP = 0.05
W_STEP = 0.10          # global scale for ΔW = -η·ε·W_STEP


def learning_rate(certainty: float) -> float:
    """η(Z) = 1 / (1 + exp(10·(Z − 0.5))). High when ignorant, ~0 when certain."""
    return 1.0 / (1.0 + math.exp(10.0 * (certainty - 0.5)))


def evolve_certainty(current_z: float, recent_eps: list,
                     z_bias_tol: float = Z_BIAS_TOL,
                     z_std_tol: float = Z_STD_TOL,
                     z_min_history: int = Z_MIN_HISTORY,
                     z_up_step: float = Z_UP_STEP,
                     z_down_step: float = Z_DOWN_STEP):
    """
    Evolve Z from the *distribution* of recent signed ε's — the corroboration
    pattern, not the magnitude of a single observation.

    Bias is judged statistically significant only when |mean(ε)| exceeds both
    the absolute floor z_bias_tol AND ~2 standard errors of the mean. The sem
    floor prevents pure noise from being misread as bias in small/noisy windows.

      Z drops on statistically significant bias.
      Z holds on noise-only (bias not significant but std too high) or short history.
      Z climbs only when bias is not significant AND consistency (std) is good.

    Returns (new_z, human_readable_reason). Mirrors
    ValidationMCPServerEnhanced._evolve_certainty (mcp_validation.py:994).
    """
    n = len(recent_eps)
    if n < z_min_history:
        return current_z, f"hold (n={n} < {z_min_history} min history)"

    mean_eps = sum(recent_eps) / n
    var = sum((e - mean_eps) ** 2 for e in recent_eps) / n
    std_eps = var ** 0.5
    sem = std_eps / (n ** 0.5)
    bias_threshold = max(z_bias_tol, 2.0 * sem)

    bias_significant = abs(mean_eps) > bias_threshold
    std_ok = std_eps <= z_std_tol

    if bias_significant:
        new_z = max(0.0, current_z - z_down_step)
        return new_z, (f"-Z (bias |{mean_eps:+.3f}| > threshold "
                       f"{bias_threshold:.3f}; sem={sem:.3f})")
    if not std_ok:
        return current_z, (f"hold (bias |{mean_eps:+.3f}| ≤ {bias_threshold:.3f} "
                           f"— not significant; std {std_eps:.3f} > {z_std_tol})")
    new_z = min(1.0, current_z + z_up_step)
    return new_z, (f"+Z (bias |{mean_eps:+.3f}| ≤ {bias_threshold:.3f}, "
                   f"std {std_eps:.3f} ≤ {z_std_tol} — calibrated + consistent)")


def apply_learning_feedback_in_memory(edge_state: dict, error_signal: float,
                                      w_step: float = W_STEP,
                                      z_window: int = Z_WINDOW,
                                      z_bias_tol: float = Z_BIAS_TOL,
                                      z_std_tol: float = Z_STD_TOL):
    """
    Pure-function fast path. Takes an edge state dict and a signed scalar ε,
    returns a NEW dict with (certainty, weight, validation_history) updated.
    No DB I/O. Mirrors ValidationMCPServerEnhanced.apply_learning_feedback_in_memory
    (mcp_validation.py:941).

        η     = 1 / (1 + exp(10·(Z − 0.5)))
        ΔW    = -η · ε · w_step
        W_new = clamp(W + ΔW, -1, +1)
        Z_new = evolve_certainty(Z, last z_window signed ε's)

    edge_state expected keys: certainty, weight, validation_history (list).
    """
    current_certainty = edge_state.get("certainty", 0.5)
    current_weight = edge_state.get("weight", 0.5)
    history = edge_state.get("validation_history", []) or []

    eta = learning_rate(current_certainty)
    weight_adjustment = -eta * error_signal * w_step
    new_weight = max(-1.0, min(1.0, current_weight + weight_adjustment))

    recent_eps = [
        h.get("signed_error", h.get("error_signal", 0.0))
        for h in history[-(z_window - 1):]
    ]
    recent_eps.append(error_signal)
    new_certainty, z_reason = evolve_certainty(
        current_certainty, recent_eps, z_bias_tol=z_bias_tol, z_std_tol=z_std_tol
    )

    new_history = list(history)
    new_history.append({
        "timestamp": datetime.now(timezone.utc),
        "signed_error": error_signal,
        "error_signal": error_signal,
        "learning_rate": eta,
        "weight_change": weight_adjustment,
        "old_weight": current_weight,
        "new_weight": new_weight,
        "old_certainty": current_certainty,
        "new_certainty": new_certainty,
        "z_reason": z_reason,
    })

    return {
        "certainty": new_certainty,
        "weight": new_weight,
        "validation_history": new_history,
    }


if __name__ == "__main__":
    # Minimal smoke test: feed a consistent small residual and watch Z climb,
    # then a large biased residual and watch Z drop.
    edge = {"certainty": 0.30, "weight": 0.0, "validation_history": []}
    print("Consistent small ε (should climb Z):")
    for _ in range(12):
        edge = apply_learning_feedback_in_memory(edge, 0.02)
    print(f"  Z={edge['certainty']:.3f}  W={edge['weight']:+.4f}")

    print("Large biased ε (should drop Z):")
    for _ in range(6):
        edge = apply_learning_feedback_in_memory(edge, 0.9)
    print(f"  Z={edge['certainty']:.3f}  W={edge['weight']:+.4f}")
