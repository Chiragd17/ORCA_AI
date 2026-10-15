import math
from datetime import datetime
from typing import List, Dict, Any, Optional

def compute_series_stats(values: List[float]) -> Dict[str, Any]:
    """
    Computes deterministic statistical metrics: count, min, max, mean, and sample standard deviation.
    """
    valid = [v for v in values if v is not None and not math.isnan(v)]
    if not valid:
        return {"count": 0, "min": None, "max": None, "mean": None, "std_dev": None}

    n = len(valid)
    mean_val = sum(valid) / n
    min_val = min(valid)
    max_val = max(valid)

    if n > 1:
        variance = sum((x - mean_val) ** 2 for x in valid) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    return {
        "count": n,
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "mean": round(mean_val, 2),
        "std_dev": round(std_dev, 2),
    }

def get_indian_ocean_season(dt: datetime) -> str:
    """
    Categorizes date into standard North Indian Ocean / Arabian Sea meteorological seasons:
    - Southwest Monsoon: June - September
    - Post-Monsoon: October - December
    - Winter: January - February
    - Pre-Monsoon: March - May
    """
    month = dt.month
    if 6 <= month <= 9:
        return "Southwest Monsoon"
    elif 10 <= month <= 12:
        return "Post-Monsoon"
    elif month in (1, 2):
        return "Winter"
    else:
        return "Pre-Monsoon"

def compute_seasonal_breakdown(
    timestamps: List[datetime], values: List[float]
) -> Dict[str, Dict[str, Any]]:
    """
    Groups observations by Arabian Sea meteorological seasons and calculates summary statistics.
    """
    seasonal_buckets: Dict[str, List[float]] = {
        "Southwest Monsoon": [],
        "Post-Monsoon": [],
        "Winter": [],
        "Pre-Monsoon": [],
    }

    for dt, val in zip(timestamps, values):
        if val is not None and not math.isnan(val):
            season = get_indian_ocean_season(dt)
            seasonal_buckets[season].append(val)

    breakdown = {}
    for season, vals in seasonal_buckets.items():
        breakdown[season] = compute_series_stats(vals)
    return breakdown

def compare_time_periods(
    period_a_values: List[float],
    period_b_values: List[float],
    variable_name: str,
    unit: str,
) -> Dict[str, Any]:
    """
    Compares two time intervals deterministically.
    """
    stats_a = compute_series_stats(period_a_values)
    stats_b = compute_series_stats(period_b_values)

    if stats_a["count"] == 0 or stats_b["count"] == 0:
        return {
            "valid_comparison": False,
            "reason": "Insufficient observations in one or both comparative periods.",
        }

    mean_diff = stats_b["mean"] - stats_a["mean"]
    pct_change = (mean_diff / stats_a["mean"] * 100.0) if stats_a["mean"] != 0 else 0.0

    return {
        "valid_comparison": True,
        "variable": variable_name,
        "unit": unit,
        "period_a_stats": stats_a,
        "period_b_stats": stats_b,
        "mean_difference": round(mean_diff, 2),
        "percentage_change": round(pct_change, 2),
    }

def detect_anomalies(
    values: List[float],
    baseline_values: List[float],
    threshold_sigma: float = 2.0,
    min_baseline_samples: int = 10,
) -> Dict[str, Any]:
    """
    Detects potential oceanographic anomalies against a designated baseline.
    Requires minimum sample depth (min_baseline_samples) to prevent unwarranted anomaly claims.
    """
    baseline_stats = compute_series_stats(baseline_values)
    if baseline_stats["count"] < min_baseline_samples:
        return {
            "has_anomaly": False,
            "anomaly_detected": False,
            "eligible": False,
            "limitation": (
                f"Insufficient baseline data for anomaly detection: {baseline_stats['count']} samples "
                f"provided, minimum required is {min_baseline_samples}."
            ),
        }

    mean = baseline_stats["mean"]
    std = baseline_stats["std_dev"]

    if std == 0.0:
        return {
            "has_anomaly": False,
            "anomaly_detected": False,
            "eligible": False,
            "limitation": "Baseline standard deviation is zero; cannot compute statistical z-score.",
        }

    anomalous_indices = []
    anomalous_values = []

    for idx, v in enumerate(values):
        if v is not None and not math.isnan(v):
            z_score = abs(v - mean) / std
            if z_score >= threshold_sigma:
                anomalous_indices.append(idx)
                anomalous_values.append(v)

    return {
        "has_anomaly": len(anomalous_values) > 0,
        "anomaly_detected": len(anomalous_values) > 0,
        "eligible": True,
        "baseline_mean": mean,
        "baseline_std_dev": std,
        "threshold_sigma": threshold_sigma,
        "anomaly_count": len(anomalous_values),
        "anomalous_values": anomalous_values,
        "indices": anomalous_indices,
    }
