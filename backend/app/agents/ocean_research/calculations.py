import math
from datetime import datetime
from typing import Any

# Physical bound limits for marine variables (plausible physical range)
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "sea_surface_temperature_celsius": (-2.0, 45.0),
    "wave_height_meters": (0.0, 35.0),
    "wave_period_seconds": (0.5, 35.0),
    "wave_direction_degrees": (0.0, 360.0),
    "ocean_current_velocity_mps": (0.0, 10.0),
    "ocean_current_direction_degrees": (0.0, 360.0),
    "wind_speed_knots": (0.0, 200.0),
    "wind_direction_degrees": (0.0, 360.0),
    "chlorophyll_mg_m3": (0.0, 100.0),
}

# Unit compatibility clusters
UNIT_COMPATIBILITY_CLUSTERS: list[set[str]] = [
    {"°c", "c", "celsius", "degc"},
    {"k", "kelvin"},
    {"m", "meter", "meters"},
    {"ft", "feet", "foot"},
    {"knots", "knot", "kt", "kts"},
    {"m/s", "meter_per_second", "meters_per_second"},
    {"s", "sec", "second", "seconds"},
    {"deg", "degree", "degrees", "°"},
    {"mg/m3", "mg_m3", "mg/m^3"},
]

def validate_unit_compatibility(unit_a: str | None, unit_b: str | None) -> bool:
    """
    Checks if two measurement units are compatible for scientific comparison.
    If either is None or empty, compatibility cannot be asserted.
    """
    if not unit_a or not unit_b:
        return False
    ua = unit_a.strip().lower()
    ub = unit_b.strip().lower()
    if ua == ub:
        return True
    for cluster in UNIT_COMPATIBILITY_CLUSTERS:
        if ua in cluster and ub in cluster:
            return True
    return False

def validate_geographic_coordinates(latitude: float | None, longitude: float | None) -> tuple[bool, str | None]:
    """
    Validates latitude (-90 to 90) and longitude (-180 to 180).
    """
    if latitude is None or longitude is None:
        return False, "Missing coordinate: both latitude and longitude must be provided."
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return False, "Coordinates must be numeric values."
    if math.isnan(latitude) or math.isnan(longitude):
        return False, "Coordinates cannot be NaN."
    if not (-90.0 <= latitude <= 90.0):
        return False, f"Latitude {latitude} out of bounds: must be between -90.0 and 90.0."
    if not (-180.0 <= longitude <= 180.0):
        return False, f"Longitude {longitude} out of bounds: must be between -180.0 and 180.0."
    return True, None

def filter_and_clean_observations(
    values: list[Any],
    timestamps: list[datetime] | None = None,
    coordinates: list[tuple[float, float]] | None = None,
    variable_name: str | None = None,
    deduplicate_timestamps: bool = True,
) -> tuple[list[float], list[datetime], list[str]]:
    """
    Cleans an observation series:
    - Rejects non-numeric, None, NaN, and infinite values.
    - Rejects values exceeding physical realistic limits for known marine variables.
    - Deduplicates identical spatial measurements (preserves spatially distinct grid cells at the same timestamp).
    - Returns cleaned (values, timestamps, limitations/warnings).
    Missing observations are NEVER treated as zero.
    """
    cleaned_vals: list[float] = []
    cleaned_times: list[datetime] = []
    issues: list[str] = []

    bounds = PHYSICAL_BOUNDS.get(variable_name) if variable_name else None
    seen_keys = set()

    has_times = timestamps is not None and len(timestamps) == len(values)
    has_coords = coordinates is not None and len(coordinates) == len(values)

    for idx, raw_val in enumerate(values):
        t = timestamps[idx] if has_times else None
        c = coordinates[idx] if has_coords else None

        # Check for None / NaN / Infinity / non-numeric
        if raw_val is None:
            continue
        if not isinstance(raw_val, (int, float)):
            issues.append(f"Ignored non-numeric observation at index {idx}: {raw_val!r}")
            continue
        val = float(raw_val)
        if math.isnan(val) or math.isinf(val):
            issues.append(f"Ignored non-finite observation ({val}) at index {idx}.")
            continue

        # Check physical plausibility bounds
        if bounds:
            min_bound, max_bound = bounds
            if val < min_bound or val > max_bound:
                issues.append(
                    f"Observation {val} at index {idx} violates physical plausibility bounds [{min_bound}, {max_bound}] for {variable_name}."
                )
                continue

        # Check spatial and timestamp deduplication
        if t is not None and deduplicate_timestamps:
            t_iso = t.isoformat()
            if c is not None:
                # Spatially distinct grid cells at same valid time are preserved
                dedup_key = (t_iso, round(c[0], 4), round(c[1], 4))
                if dedup_key in seen_keys:
                    issues.append(f"Ignored duplicate spatial observation at {dedup_key}.")
                    continue
            else:
                dedup_key = t_iso
                if dedup_key in seen_keys:
                    issues.append(f"Ignored duplicate timestamp at {t_iso}.")
                    continue
            seen_keys.add(dedup_key)

        cleaned_vals.append(val)
        if t is not None:
            cleaned_times.append(t)

    return cleaned_vals, cleaned_times, issues

def compute_series_stats(
    values: list[float],
    timestamps: list[datetime] | None = None,
    max_gap_hours: float = 12.0,
) -> dict[str, Any]:
    """
    Computes deterministic statistical metrics:
    - count
    - min, max, mean
    - median (exact midpoint or mean of two midpoints)
    - sample standard deviation (N-1 degrees of freedom)
    - temporal coverage: start_time, end_time, duration_hours
    - sampling gaps: detected intervals where consecutive timestamps exceed max_gap_hours
    Missing observations (None / NaN) are never treated as zero.
    """
    pairs = []
    if timestamps and len(timestamps) == len(values):
        for t, v in zip(timestamps, values):
            if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
                pairs.append((t, float(v)))
    else:
        for v in values:
            if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
                pairs.append((None, float(v)))

    if not pairs:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std_dev": None,
            "temporal_coverage": None,
            "sampling_gaps": [],
        }

    valid_vals = [p[1] for p in pairs]
    valid_times = [p[0] for p in pairs if p[0] is not None]

    n = len(valid_vals)
    mean_val = sum(valid_vals) / n
    min_val = min(valid_vals)
    max_val = max(valid_vals)

    # Median
    sorted_vals = sorted(valid_vals)
    if n % 2 == 1:
        median_val = sorted_vals[n // 2]
    else:
        median_val = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    # Sample standard deviation (N-1 degrees of freedom)
    if n > 1:
        variance = sum((x - mean_val) ** 2 for x in valid_vals) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    # Temporal coverage & sampling gaps
    coverage = None
    gaps = []
    if len(valid_times) >= 2:
        sorted_times = sorted(valid_times)
        start_t = sorted_times[0]
        end_t = sorted_times[-1]
        duration_hrs = (end_t - start_t).total_seconds() / 3600.0
        coverage = {
            "start_time": start_t.isoformat(),
            "end_time": end_t.isoformat(),
            "duration_hours": round(duration_hrs, 2),
        }

        for i in range(len(sorted_times) - 1):
            t_curr = sorted_times[i]
            t_next = sorted_times[i + 1]
            gap_hrs = (t_next - t_curr).total_seconds() / 3600.0
            if gap_hrs > max_gap_hours:
                gaps.append({
                    "from_time": t_curr.isoformat(),
                    "to_time": t_next.isoformat(),
                    "gap_hours": round(gap_hrs, 2),
                })

    return {
        "count": n,
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "mean": round(mean_val, 2),
        "median": round(median_val, 2),
        "std_dev": round(std_dev, 2),
        "temporal_coverage": coverage,
        "sampling_gaps": gaps,
    }

def get_indian_ocean_season(dt: datetime) -> str:
    """
    Categorizes date into standard North Indian Ocean / Arabian Sea meteorological seasons:
    - Southwest Monsoon: June - September (months 6 - 9)
    - Post-Monsoon: October - December (months 10 - 12)
    - Winter: January - February (months 1 - 2)
    - Pre-Monsoon: March - May (months 3 - 5)
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
    timestamps: list[datetime],
    values: list[float],
    min_observations_per_season: int = 1,
) -> dict[str, dict[str, Any]]:
    """
    Groups observations by Arabian Sea meteorological seasons.
    Only computes valid seasonal summaries when minimum observations threshold is met.
    Documents season definitions and sample adequacy explicitly.
    """
    seasonal_buckets: dict[str, list[tuple[datetime, float]]] = {
        "Southwest Monsoon": [],
        "Post-Monsoon": [],
        "Winter": [],
        "Pre-Monsoon": [],
    }

    for dt, val in zip(timestamps, values):
        if val is not None and isinstance(val, (int, float)) and not math.isnan(val):
            season = get_indian_ocean_season(dt)
            seasonal_buckets[season].append((dt, float(val)))

    breakdown = {}
    season_definitions = {
        "Southwest Monsoon": "June through September (high swell, intense rainfall)",
        "Post-Monsoon": "October through December (cyclonic transition, calmer seas)",
        "Winter": "January through February (northeasterly winds, mild SST)",
        "Pre-Monsoon": "March through May (warming SST, thermal convective setup)",
    }

    for season, items in seasonal_buckets.items():
        s_times = [it[0] for it in items]
        s_vals = [it[1] for it in items]
        stats = compute_series_stats(s_vals, s_times)
        stats["season_definition"] = season_definitions.get(season, "")
        if len(items) >= min_observations_per_season:
            stats["is_adequate_coverage"] = True
            stats["limitation"] = None
        elif len(items) > 0:
            stats["is_adequate_coverage"] = False
            stats["limitation"] = (
                f"Insufficient seasonal coverage for {season} ({len(items)} samples; "
                f"minimum required: {min_observations_per_season})."
            )
        else:
            stats["is_adequate_coverage"] = False
            stats["limitation"] = None
        breakdown[season] = stats

    return breakdown

def compare_time_periods(
    period_a_values: list[float],
    period_b_values: list[float],
    variable_name: str,
    unit: str,
    unit_b: str | None = None,
    period_a_name: str = "Period A",
    period_b_name: str = "Period B",
    period_a_times: list[datetime] | None = None,
    period_b_times: list[datetime] | None = None,
) -> dict[str, Any]:
    """
    Compares two time intervals deterministically.
    Preserves period boundaries, sample counts, mean difference, median difference, and percentage change.
    Rejects comparison if units are incompatible or either period lacks valid observations.
    """
    effective_unit_b = unit_b or unit
    if not validate_unit_compatibility(unit, effective_unit_b):
        return {
            "valid_comparison": False,
            "reason": f"Incompatible units between comparative periods: '{unit}' vs '{effective_unit_b}'.",
        }

    stats_a = compute_series_stats(period_a_values, period_a_times)
    stats_b = compute_series_stats(period_b_values, period_b_times)

    if stats_a["count"] == 0 or stats_b["count"] == 0:
        return {
            "valid_comparison": False,
            "reason": (
                f"Insufficient observations: '{period_a_name}' has {stats_a['count']} samples, "
                f"'{period_b_name}' has {stats_b['count']} samples. Both require >= 1 sample."
            ),
        }

    mean_diff = round(stats_b["mean"] - stats_a["mean"], 2)
    pct_change = round((mean_diff / stats_a["mean"] * 100.0), 2) if stats_a["mean"] != 0 else 0.0

    med_a = stats_a["median"]
    med_b = stats_b["median"]
    med_diff = round(med_b - med_a, 2) if med_a is not None and med_b is not None else None

    if mean_diff > 0:
        direction = "higher"
    elif mean_diff < 0:
        direction = "lower"
    else:
        direction = "identical"

    return {
        "valid_comparison": True,
        "variable": variable_name,
        "unit": unit,
        "period_a": {
            "name": period_a_name,
            "stats": stats_a,
        },
        "period_b": {
            "name": period_b_name,
            "stats": stats_b,
        },
        "mean_difference": mean_diff,
        "median_difference": med_diff,
        "percentage_change": pct_change,
        "direction": direction,
        "method": "Deterministic two-interval comparison of mean and median metrics.",
    }

def compare_locations(
    loc_a_values: list[float],
    loc_b_values: list[float],
    loc_a_name: str,
    loc_b_name: str,
    variable_name: str,
    unit: str,
    unit_b: str | None = None,
    loc_a_times: list[datetime] | None = None,
    loc_b_times: list[datetime] | None = None,
) -> dict[str, Any]:
    """
    Compares oceanographic variables across two spatial locations deterministically.
    Preserves sample counts, means, medians, differences, and units.
    """
    effective_unit_b = unit_b or unit
    if not validate_unit_compatibility(unit, effective_unit_b):
        return {
            "valid_comparison": False,
            "reason": f"Incompatible units between comparative locations: '{unit}' vs '{effective_unit_b}'.",
        }

    stats_a = compute_series_stats(loc_a_values, loc_a_times)
    stats_b = compute_series_stats(loc_b_values, loc_b_times)

    if stats_a["count"] == 0 or stats_b["count"] == 0:
        return {
            "valid_comparison": False,
            "reason": (
                f"Insufficient observations: '{loc_a_name}' has {stats_a['count']} samples, "
                f"'{loc_b_name}' has {stats_b['count']} samples. Both require >= 1 sample."
            ),
        }

    diff = round(stats_b["mean"] - stats_a["mean"], 2)
    pct_diff = round((diff / stats_a["mean"] * 100.0), 2) if stats_a["mean"] != 0 else 0.0

    med_a = stats_a["median"]
    med_b = stats_b["median"]
    med_diff = round(med_b - med_a, 2) if med_a is not None and med_b is not None else None

    return {
        "valid_comparison": True,
        "variable": variable_name,
        "unit": unit,
        "location_a": {"name": loc_a_name, "stats": stats_a},
        "location_b": {"name": loc_b_name, "stats": stats_b},
        "mean_difference": diff,
        "median_difference": med_diff,
        "percentage_difference": pct_diff,
        "method": "Deterministic two-location spatial comparison.",
    }

def detect_anomalies(
    values: list[float],
    baseline_values: list[float],
    threshold_sigma: float = 2.0,
    min_baseline_samples: int = 10,
    variable_name: str = "variable",
    unit: str = "",
    assessment_period: str | None = None,
    baseline_period: str | None = None,
    provenance_assessment: str | None = None,
    provenance_baseline: str | None = None,
) -> dict[str, Any]:
    """
    Detects potential oceanographic anomalies against a designated baseline.
    Requires minimum sample depth (min_baseline_samples >= 10) to prevent unwarranted anomaly claims.
    Requires evaluation sample and baseline to be separate datasets based on period identities and provenance.
    """
    if not values:
        return {
            "has_anomaly": False,
            "anomaly_detected": False,
            "eligible": False,
            "limitation": "Insufficient assessment samples (0 provided) for anomaly detection.",
        }

    # 1. Reject identical object reference
    if values is baseline_values:
        return {
            "has_anomaly": False,
            "anomaly_detected": False,
            "eligible": False,
            "limitation": "Anomaly detection requires separate baseline and assessment periods; evaluation sample cannot be identical to the baseline.",
        }

    # 2. Check period and provenance identities
    if assessment_period and baseline_period and assessment_period == baseline_period:
        return {
            "has_anomaly": False,
            "anomaly_detected": False,
            "eligible": False,
            "limitation": f"Anomaly detection requires distinct temporal periods; assessment period '{assessment_period}' matches baseline period.",
        }

    # If no period or provenance is specified and values are identical, reject as unproven distinctness
    if not assessment_period and not baseline_period and not provenance_assessment and not provenance_baseline:
        if len(values) == len(baseline_values) and values == baseline_values:
            return {
                "has_anomaly": False,
                "anomaly_detected": False,
                "eligible": False,
                "limitation": "Anomaly detection requires separate baseline and assessment periods; evaluation sample cannot be identical to the baseline.",
            }

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
        if v is not None and isinstance(v, (int, float)) and not math.isnan(v):
            z_score = abs(v - mean) / std
            if z_score >= threshold_sigma:
                anomalous_indices.append(idx)
                anomalous_values.append(v)

    return {
        "has_anomaly": len(anomalous_values) > 0,
        "anomaly_detected": len(anomalous_values) > 0,
        "eligible": True,
        "variable": variable_name,
        "unit": unit,
        "baseline_mean": mean,
        "baseline_std_dev": std,
        "baseline_sample_count": baseline_stats["count"],
        "threshold_sigma": threshold_sigma,
        "anomaly_count": len(anomalous_values),
        "anomalous_values": anomalous_values,
        "indices": anomalous_indices,
        "method": f"Statistical z-score >= {threshold_sigma} sigma exceedance against verified baseline.",
    }
