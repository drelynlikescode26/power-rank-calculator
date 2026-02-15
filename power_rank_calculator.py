"""Power Rank Calculator for Prime Communications.

This module parses CSV input, scores metrics using tiered thresholds,
applies business rules, and generates summary reports.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


THRESHOLDS: List[float] = [125, 100, 90, 80, 70, 60, 50, 40, 30, 20, 0]

METRIC_MAX_POINTS: Dict[str, float] = {
    "opps_pct": 10,
    "ppvga_pct": 30,
    "internet_pct": 20,
    "accessories_pct": 10,
    "protection_pct": 5,
    "rate_plan_pct": 5,
    "next_up_pct": 5,
    "event_opps_pct": 5,
    "plus1_pct": 5,
    "csat_pct": 5,
}

# Multipliers by threshold for most metrics (50% and up).
DEFAULT_MULTIPLIERS: Dict[float, float] = {
    125: 1.0,
    100: 1.0,
    90: 0.9,
    80: 0.8,
    70: 0.7,
    60: 0.6,
    50: 0.5,
    40: 0.4,
    30: 0.3,
    20: 0.2,
    0: 0.0,
}

# Tweaked multipliers for 5-point metrics so 80%+ can earn full points.
FIVE_POINT_MULTIPLIERS: Dict[float, float] = {
    125: 1.0,
    100: 1.0,
    90: 1.0,
    80: 1.0,
    70: 0.8,
    60: 0.6,
    50: 0.4,
    40: 0.2,
    30: 0.0,
    20: 0.0,
    0: 0.0,
}

# Set allow_below_50 to True for metrics that should score below 50%.
METRIC_RULES: Dict[str, Dict[str, object]] = {
    "protection_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
    "rate_plan_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
    "next_up_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
    "event_opps_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
    "plus1_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
    "csat_pct": {"multipliers": FIVE_POINT_MULTIPLIERS, "allow_below_50": False},
}


@dataclass
class Record:
    """Represents a single CSV record with optional parsing errors."""

    data: Dict[str, Optional[float]]
    date: str
    errors: List[str]


def _to_float(value: str, field_name: str, errors: List[str]) -> Optional[float]:
    """Convert a string to float, recording an error if conversion fails."""

    if value is None or value == "":
        errors.append(f"Missing value for {field_name}.")
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"Invalid number for {field_name}: {value!r}.")
        return None


def parse_csv(filepath: str) -> List[Record]:
    """Load CSV and return a list of parsed records."""

    records: List[Record] = []
    with open(filepath, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            errors: List[str] = []
            date_value = (row.get("date") or "").strip()
            if not date_value:
                errors.append("Missing date value.")
                date_value = ""

            data: Dict[str, Optional[float]] = {}
            for field in METRIC_MAX_POINTS:
                data[field] = _to_float(row.get(field, ""), field, errors)
            data["htp_pct"] = _to_float(row.get("htp_pct", ""), "htp_pct", errors)

            records.append(Record(data=data, date=date_value, errors=errors))

    return records


def percent_to_points(metric_name: str, percent: Optional[float]) -> float:
    """Convert a percent value to points using tiered thresholds."""

    if percent is None:
        return 0.0

    max_points = METRIC_MAX_POINTS.get(metric_name)
    if max_points is None:
        raise KeyError(f"Unknown metric: {metric_name}")

    rules = METRIC_RULES.get(metric_name, {})
    multipliers = rules.get("multipliers", DEFAULT_MULTIPLIERS)
    allow_below_50 = rules.get("allow_below_50", False)

    if percent < 50 and not allow_below_50:
        return 0.0

    for threshold in THRESHOLDS:
        if percent >= threshold:
            multiplier = float(multipliers.get(threshold, 0.0))
            return round(max_points * multiplier, 2)

    return 0.0


def compute_points(record: Record) -> Dict[str, float]:
    """Compute points for each metric, applying the HTP rule."""

    points: Dict[str, float] = {}
    for metric in METRIC_MAX_POINTS:
        points_key = metric.replace("_pct", "_points")
        points[points_key] = percent_to_points(metric, record.data.get(metric))

    htp_value = record.data.get("htp_pct")
    if htp_value is not None and htp_value < 6.5:
        points["protection_points"] = round(points.get("protection_points", 0.0) / 2, 2)

    return points


def compute_power_rank(points_dict: Dict[str, float]) -> Tuple[float, float]:
    """Return total points and the Power Rank value."""

    total_points = round(sum(points_dict.values()), 2)
    power_rank = round((total_points / 100.0) * 10, 2)
    return total_points, power_rank


def needed_to_target(
    current_value: float,
    goal: float,
    day_of_month: int,
    days_in_month: int,
    target_pct: float,
) -> int:
    """Return how much more is needed by today to reach a target percent."""

    if days_in_month <= 0:
        raise ValueError("days_in_month must be greater than zero.")

    daily_target = goal / days_in_month
    needed_by_today = daily_target * day_of_month * (target_pct / 100.0)
    required_more = max(0, math.ceil(needed_by_today - current_value))
    return required_more


def generate_report(record: Record, points: Dict[str, float], power_rank: float) -> str:
    """Return a formatted summary report for a single record."""

    total_points = round(sum(points.values()), 2)
    lines: List[str] = [
        f"Date: {record.date}",
        "Metric Summary:",
    ]

    for metric in METRIC_MAX_POINTS:
        percent_value = record.data.get(metric)
        points_key = metric.replace("_pct", "_points")
        points_value = points.get(points_key, 0.0)
        percent_display = "n/a" if percent_value is None else f"{percent_value:.2f}%"
        lines.append(f"- {metric}: {percent_display} -> {points_value:.2f} pts")

    if record.errors:
        lines.append("Errors:")
        lines.extend([f"- {error}" for error in record.errors])

    lines.extend(
        [
            f"Total Points: {total_points:.2f}",
            f"Power Rank: {power_rank:.2f}",
        ]
    )

    return "\n".join(lines)


def calculate_needed_by_date(
    goals: Dict[str, float],
    current: Dict[str, float],
    day_of_month: int,
    days_in_month: int,
    target_rank: float,
) -> Dict[str, object]:
    """Estimate metric targets by today to reach an overall Power Rank.

    This uses the next threshold level per metric and prioritizes metrics
    with the largest point gap.
    """

    current_record = Record(data={**current}, date="", errors=[])
    current_points = compute_points(current_record)
    current_total, _ = compute_power_rank(current_points)

    target_points = (target_rank / 10.0) * 100.0
    shortfall = max(0.0, round(target_points - current_total, 2))

    recommendations: List[Dict[str, object]] = []

    for metric, max_points in METRIC_MAX_POINTS.items():
        current_value = current.get(metric, 0.0)
        goal_value = goals.get(metric)
        if goal_value is None:
            continue

        current_percent = (current_value / goal_value) * 100 if goal_value else 0.0
        current_metric_points = percent_to_points(metric, current_percent)

        rules = METRIC_RULES.get(metric, {})
        allow_below_50 = rules.get("allow_below_50", False)

        next_threshold = None
        for threshold in THRESHOLDS:
            if threshold <= current_percent:
                continue
            if threshold < 50 and not allow_below_50:
                continue
            next_threshold = threshold
            break

        if next_threshold is None:
            continue

        next_points = percent_to_points(metric, next_threshold)
        point_gain = round(max(0.0, next_points - current_metric_points), 2)
        if point_gain <= 0:
            continue

        required_more = needed_to_target(
            current_value=current_value,
            goal=goal_value,
            day_of_month=day_of_month,
            days_in_month=days_in_month,
            target_pct=next_threshold,
        )

        recommendations.append(
            {
                "metric": metric,
                "current_percent": round(current_percent, 2),
                "next_threshold": next_threshold,
                "point_gain": point_gain,
                "needed_more_by_today": required_more,
            }
        )

    recommendations.sort(key=lambda item: item["point_gain"], reverse=True)

    return {
        "target_rank": target_rank,
        "target_points": round(target_points, 2),
        "current_points": current_total,
        "shortfall_points": shortfall,
        "recommendations": recommendations,
    }


if __name__ == "__main__":
    # Example usage with a single CSV row provided in the prompt.
    sample = Record(
        data={
            "opps_pct": 61,
            "ppvga_pct": 35,
            "internet_pct": 36,
            "accessories_pct": 70,
            "protection_pct": 83,
            "rate_plan_pct": 100,
            "next_up_pct": 82,
            "event_opps_pct": 40,
            "plus1_pct": 38,
            "csat_pct": 75,
            "htp_pct": 5.1,
        },
        date="2026-02-14",
        errors=[],
    )

    sample_points = compute_points(sample)
    total_points, rank = compute_power_rank(sample_points)
    sample_points["total_points"] = total_points
    sample_points["power_rank"] = rank
    print(sample_points)
