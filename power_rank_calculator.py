"""Power Rank Calculator for Prime Communications."""

from __future__ import annotations

import json
import math
from typing import Dict, List, Optional, Tuple

# ── Category max points ───────────────────────────────────────────────────────

METRIC_MAX_POINTS: Dict[str, float] = {
    "opps":        15,
    "ppvga":       35,
    "fiber":       15,
    "aia":         10,
    "accessories": 10,
    "protection":   5,
    "rate_plan":    5,
    "next_up":      5,
}

# ── Scoring tables ────────────────────────────────────────────────────────────

# Sales-to-goal categories: 125 %+ earns full points, each 10-pp tier is -10 %.
SALES_MULTIPLIERS: Dict[float, float] = {
    125: 1.0, 100: 0.9, 90: 0.8, 80: 0.7,
     70: 0.6,  60: 0.5, 50: 0.4, 40: 0.3,
     30: 0.2,  20: 0.1,  0: 0.0,
}
_SALES_THRESHOLDS: List[float] = sorted(SALES_MULTIPLIERS, reverse=True)

# Attach-rate categories use exact percentage breakpoints.
PROTECTION_TABLE: List[Tuple[float, float]] = [
    (70, 5.0), (68, 4.5), (66, 4.0), (63, 3.5), (60, 3.0),
]

RATE_PLAN_TABLE: List[Tuple[float, float]] = [
    (82, 5.0), (80, 4.5), (78, 4.0), (76, 3.5), (74, 3.0),
]

NEXT_UP_TABLE: List[Tuple[float, float]] = [
    (80, 5.0), (78, 4.5), (76, 4.0), (74, 3.5), (72, 3.0),
]

_ATTACH_TABLES: Dict[str, List[Tuple[float, float]]] = {
    "protection": PROTECTION_TABLE,
    "rate_plan":  RATE_PLAN_TABLE,
    "next_up":    NEXT_UP_TABLE,
}

# ── Commission rates by rank tier ─────────────────────────────────────────────

COMMISSION_TIERS: Dict[str, Dict[str, float]] = {
    "rank_8": {
        "new_voice_premium":  35,
        "new_voice_extra":    25,
        "new_voice_starter":  15,
        "fiber_aia":          50,
        "voice_upgrade":       5,
        "accessories_pct":    0.06,
        "pa1":                 3,
        "pa4":                 6,
        "htp":                 6,
    },
    "rank_9": {
        "new_voice_premium":  70,
        "new_voice_extra":    50,
        "new_voice_starter":  25,
        "fiber_aia":          60,
        "voice_upgrade":       5,
        "accessories_pct":    0.07,
        "pa1":                 4,
        "pa4":                10,
        "htp":                10,
    },
}

# ── Core scoring ──────────────────────────────────────────────────────────────

def percent_to_points(metric: str, percent: float) -> float:
    """Return points earned for a metric at a given percent-to-goal or attach rate."""
    if percent is None:
        return 0.0

    table = _ATTACH_TABLES.get(metric)
    if table is not None:
        for threshold, pts in table:
            if percent >= threshold:
                return pts
        return 0.0

    max_pts = METRIC_MAX_POINTS.get(metric)
    if max_pts is None:
        raise KeyError(f"Unknown metric: {metric!r}")

    for threshold in _SALES_THRESHOLDS:
        if percent >= threshold:
            return round(max_pts * SALES_MULTIPLIERS[threshold], 2)
    return 0.0


def compute_points(metrics: Dict[str, float]) -> Dict[str, float]:
    """Return {metric: points} for every recognised metric in *metrics*."""
    return {m: percent_to_points(m, v) for m, v in metrics.items() if m in METRIC_MAX_POINTS}


def compute_power_rank(points: Dict[str, float]) -> Tuple[float, float]:
    """Return (total_points, power_rank)."""
    total = round(sum(points.values()), 2)
    rank  = round(total / 10, 2)
    return total, rank


# ── What-if simulator ─────────────────────────────────────────────────────────

def simulate_what_if(
    metrics: Dict[str, float],
    changes: Dict[str, float],
) -> Dict[str, object]:
    """Apply hypothetical metric changes and return the rank impact.

    *changes* maps metric name → new percent value.
    """
    before_pts              = compute_points(metrics)
    before_total, before_rk = compute_power_rank(before_pts)

    updated                 = {**metrics, **changes}
    after_pts               = compute_points(updated)
    after_total, after_rk   = compute_power_rank(after_pts)

    return {
        "before_rank":    before_rk,
        "after_rank":     after_rk,
        "rank_delta":     round(after_rk - before_rk, 2),
        "before_points":  before_total,
        "after_points":   after_total,
        "points_delta":   round(after_total - before_total, 2),
        "category_deltas": {
            m: round(after_pts.get(m, 0) - before_pts.get(m, 0), 2)
            for m in METRIC_MAX_POINTS
        },
    }


# ── Path to target rank ───────────────────────────────────────────────────────

def path_to_rank(
    metrics: Dict[str, float],
    target_rank: float,
) -> Dict[str, object]:
    """Return the greedy list of metric improvements needed to reach *target_rank*."""
    current_pts            = compute_points(metrics)
    current_total, cur_rk  = compute_power_rank(current_pts)
    target_total           = round(target_rank * 10, 2)
    needed                 = max(0.0, round(target_total - current_total, 2))

    # Maximum gain possible per metric (push to 125 %)
    candidates = []
    for metric in METRIC_MAX_POINTS:
        cur_pct  = metrics.get(metric, 0.0)
        cur_pts  = percent_to_points(metric, cur_pct)
        max_pts  = percent_to_points(metric, 125)
        gain     = round(max_pts - cur_pts, 2)
        if gain > 0:
            candidates.append({"metric": metric, "current_pct": cur_pct,
                                "current_pts": cur_pts, "max_gain": gain})

    candidates.sort(key=lambda x: x["max_gain"], reverse=True)

    actions   = []
    projected = current_total
    for c in candidates:
        if projected >= target_total:
            break
        actions.append({
            "metric":       c["metric"],
            "current_pct":  c["current_pct"],
            "points_added": c["max_gain"],
        })
        projected = round(projected + c["max_gain"], 2)

    return {
        "current_rank":        cur_rk,
        "current_points":      current_total,
        "target_rank":         target_rank,
        "target_points":       target_total,
        "needed_points":       needed,
        "recommended_actions": actions,
        "projected_points":    projected,
        "projected_rank":      round(projected / 10, 2),
    }


# ── Commission projection ─────────────────────────────────────────────────────

def commission_tier_key(rank: float) -> str:
    return "rank_9" if rank >= 9.0 else "rank_8"


def project_commission(
    rank: float,
    sales: Dict[str, float],
) -> Dict[str, object]:
    """Estimate payout at current rank and at rank 9 for the same sales mix.

    Expected *sales* keys:
        new_voice_premium, new_voice_extra, new_voice_starter,
        fiber_aia, voice_upgrade, accessories_revenue, pa1, pa4, htp
    """
    def _calc(tier_key: str) -> float:
        r = COMMISSION_TIERS[tier_key]
        return round(
            sales.get("new_voice_premium",    0) * r["new_voice_premium"]
            + sales.get("new_voice_extra",    0) * r["new_voice_extra"]
            + sales.get("new_voice_starter",  0) * r["new_voice_starter"]
            + sales.get("fiber_aia",          0) * r["fiber_aia"]
            + sales.get("voice_upgrade",      0) * r["voice_upgrade"]
            + sales.get("accessories_revenue",0) * r["accessories_pct"]
            + sales.get("pa1",                0) * r["pa1"]
            + sales.get("pa4",                0) * r["pa4"]
            + sales.get("htp",                0) * r["htp"],
            2,
        )

    current_tier = commission_tier_key(rank)
    current_pay  = _calc(current_tier)
    rank9_pay    = _calc("rank_9")

    return {
        "current_rank":       rank,
        "current_tier":       current_tier,
        "current_commission": current_pay,
        "rank9_commission":   rank9_pay,
        "rank9_uplift":       round(rank9_pay - current_pay, 2),
    }


# ── Report helper ─────────────────────────────────────────────────────────────

def generate_report(metrics: Dict[str, float]) -> str:
    pts          = compute_points(metrics)
    total, rank  = compute_power_rank(pts)
    lines        = ["Power Rank Report", "=" * 42]
    for m, max_p in METRIC_MAX_POINTS.items():
        pct = metrics.get(m, 0.0)
        p   = pts.get(m, 0.0)
        lines.append(f"  {m:<14} {pct:>6.1f}%  →  {p:>5.2f} / {max_p:.0f} pts")
    lines += [
        "-" * 42,
        f"  Total Points:   {total:.2f}",
        f"  Power Rank:     {rank:.2f}",
    ]
    return "\n".join(lines)


# ── Example ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    snapshot = {
        "opps":        201,
        "ppvga":       237,
        "fiber":        62,
        "aia":         124,
        "accessories": 151,
        "protection":   46,
        "rate_plan":    59,
        "next_up":      76,
    }

    print(generate_report(snapshot))
    print()
    print("Path to 9.0:")
    print(json.dumps(path_to_rank(snapshot, 9.0), indent=2))
    print()

    # What if +1 fiber moves you from 62 % → ~85 %?
    print("What-if: fiber → 85 %:")
    print(json.dumps(simulate_what_if(snapshot, {"fiber": 85}), indent=2))
    print()

    sample_sales = {
        "new_voice_premium": 8, "new_voice_extra": 4, "new_voice_starter": 2,
        "fiber_aia": 3, "voice_upgrade": 5, "accessories_revenue": 350,
        "pa1": 6, "pa4": 3, "htp": 2,
    }
    print("Commission projection:")
    print(json.dumps(project_commission(8.0, sample_sales), indent=2))
