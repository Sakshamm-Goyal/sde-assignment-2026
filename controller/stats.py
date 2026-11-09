"""Small, deterministic statistics. No randomness anywhere: the same data gives the same decision."""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()


def cdf(z: float) -> float:
    return _N.cdf(z)


def zq(p: float) -> float:
    """Upper quantile: zq(0.01) = 2.326."""
    return _N.inv_cdf(1 - p)


def strat_diff(strata):
    """Stratified difference in proportions, arm A minus arm B.

    strata: iterable of (nA, xA, nB, xB). Each stratum (day x cohort) is weighted by its harmonic size, so a
    change in traffic mix over time (prompt change, campaign day, decay) cannot masquerade as an arm effect.
    Returns (diff, se, nA, nB, pB) with pB the pooled rate of B (for relative lift).
    """
    sw = d = v = 0.0
    na = nb = xb = 0
    for a_n, a_x, b_n, b_x in strata:
        if a_n == 0 or b_n == 0:
            continue
        w = a_n * b_n / (a_n + b_n)
        pa, pb = a_x / a_n, b_x / b_n
        p = (a_x + b_x) / (a_n + b_n)
        var = max(p * (1 - p), 1e-4) * (1 / a_n + 1 / b_n)
        sw += w
        d += w * (pa - pb)
        v += w * w * var
        na += a_n
        nb += b_n
        xb += b_x
    if sw == 0:
        return 0.0, float("inf"), na, nb, 0.0
    return d / sw, math.sqrt(v) / sw, na, nb, xb / nb


def holm(pvals: list[float], alpha: float) -> list[bool]:
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    out = [False] * len(pvals)
    m = len(pvals)
    for rank, i in enumerate(order):
        if pvals[i] <= alpha / (m - rank):
            out[i] = True
        else:
            break
    return out


def binom_upper_z(x: int, n: int, p0: float) -> float:
    """z-score of an observed count against a baseline rate (one-sided, large-n normal approximation)."""
    if n == 0:
        return 0.0
    return (x - n * p0) / math.sqrt(max(n * p0 * (1 - p0), 1e-9))


def wilson_lower(x: int, n: int, z: float = 1.2816) -> float:
    if n == 0:
        return 0.0
    p = x / n
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / den


def chi2_z(chi: float, df: int) -> float:
    """Wilson-Hilferty: chi-square statistic -> approximate standard-normal z."""
    if df <= 0:
        return 0.0
    return ((chi / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))


def n_required(p: float, rel_lift: float, alpha: float = 0.01, power: float = 0.8) -> int:
    d = p * rel_lift
    return math.ceil(2 * (zq(alpha) + zq(1 - power)) ** 2 * p * (1 - p) / d ** 2)


if __name__ == "__main__":  # ponytail: one runnable check for the logic that decides winners
    assert abs(zq(0.01) - 2.326) < 1e-3
    assert holm([0.001, 0.02, 0.04], 0.05) == [True, True, True]
    assert holm([0.03, 0.02, 0.5], 0.05) == [False, False, False]
    d, se, *_ = strat_diff([(1000, 600, 1000, 500), (10, 0, 10, 10)])
    assert 0.08 < d < 0.11 and se < 0.05, (d, se)
    assert n_required(0.55, 0.10, 0.01) in range(1600, 1700)
    assert wilson_lower(990, 1000) > 0.98
    print("stats ok")
