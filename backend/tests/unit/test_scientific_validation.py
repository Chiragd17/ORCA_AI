from datetime import datetime

from app.agents.ocean_research.calculations import (
    compare_time_periods,
    compute_series_stats,
    detect_anomalies,
    filter_and_clean_observations,
    get_indian_ocean_season,
    validate_unit_compatibility,
)
from app.utils import haversine_distance_km

# -----------------------------------------------------------------------------
# 1. Independent Ground-Truth Time-Series Statistics Verification
# -----------------------------------------------------------------------------

def test_timeseries_ground_truth_analytic():
    """
    Analytic Ground-Truth:
    Dataset X = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    N = 8
    Sum = 40.0
    Mean = 40.0 / 8 = 5.00
    Min = 2.0, Max = 9.0
    Median: sorted midpoints at index 3 (4.0) and index 4 (5.0) -> (4.0 + 5.0) / 2 = 4.50
    Sample Variance (N-1 = 7 df):
      (2 - 5.0)^2 = 9.0
      3 * (4 - 5.0)^2 = 3 * 1.0 = 3.0
      2 * (5 - 5.0)^2 = 0.0
      (7 - 5.0)^2 = 4.0
      (9 - 5.0)^2 = 16.0
      Sum of squares = 9 + 3 + 0 + 4 + 16 = 32.0
      s^2 = 32.0 / 7 = 4.571428...
      s = sqrt(4.571428...) = 2.138089... -> rounded 2.14
    """
    data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    stats = compute_series_stats(data)

    assert stats["count"] == 8
    assert stats["min"] == 2.0
    assert stats["max"] == 9.0
    assert stats["mean"] == 5.0
    assert stats["median"] == 4.5
    assert stats["std_dev"] == 2.14

def test_timeseries_single_observation_ground_truth():
    """Single observation case: N=1, sample variance has 0 degrees of freedom -> std_dev=0.0."""
    stats = compute_series_stats([28.5])
    assert stats["count"] == 1
    assert stats["min"] == 28.5
    assert stats["max"] == 28.5
    assert stats["mean"] == 28.5
    assert stats["median"] == 28.5
    assert stats["std_dev"] == 0.0

def test_timeseries_missing_and_nonfinite_never_zero():
    """
    Ensures missing (None), NaN, +Inf, -Inf, and non-numeric values
    are excluded and NEVER treated as zero.
    Raw: [10.0, None, float('nan'), float('inf'), float('-inf'), 20.0]
    Valid subset: [10.0, 20.0]
    Mean must be 15.0 (NOT 30.0/6 = 5.0).
    """
    raw_vals = [10.0, None, float("nan"), float("inf"), float("-inf"), 20.0]
    cleaned, _, _ = filter_and_clean_observations(raw_vals)
    assert cleaned == [10.0, 20.0]

    stats = compute_series_stats(cleaned)
    assert stats["count"] == 2
    assert stats["mean"] == 15.0
    assert stats["median"] == 15.0
    assert stats["min"] == 10.0
    assert stats["max"] == 20.0

# -----------------------------------------------------------------------------
# 2. Independent Historical Period Comparison Verification
# -----------------------------------------------------------------------------

def test_historical_period_comparison_ground_truth():
    """
    Period A: [1.0, 2.0, 3.0] -> Mean = 2.0, Median = 2.0
    Period B: [3.0, 4.0, 5.0] -> Mean = 4.0, Median = 4.0
    Mean difference: 4.0 - 2.0 = +2.0
    Median difference: 4.0 - 2.0 = +2.0
    Percentage change: (2.0 / 2.0) * 100 = 100.0%
    """
    comp = compare_time_periods(
        period_a_values=[1.0, 2.0, 3.0],
        period_b_values=[3.0, 4.0, 5.0],
        variable_name="wave_height",
        unit="m",
        period_a_name="Baseline Period",
        period_b_name="Active Period",
    )
    assert comp["valid_comparison"] is True
    assert comp["mean_difference"] == 2.0
    assert comp["median_difference"] == 2.0
    assert comp["percentage_change"] == 100.0
    assert comp["period_a"]["name"] == "Baseline Period"
    assert comp["period_b"]["name"] == "Active Period"

# -----------------------------------------------------------------------------
# 3. Seasonal Categorization, Boundaries, and Leap Year Handling
# -----------------------------------------------------------------------------

def test_seasonal_categorization_calendar_boundaries():
    """
    Tests exact calendar transitions across all four Arabian Sea seasons:
    - Southwest Monsoon: June 1 to September 30
    - Post-Monsoon: October 1 to December 31
    - Winter: January 1 to February 28/29 (including Leap Year Feb 29)
    - Pre-Monsoon: March 1 to May 31
    """
    # Southwest Monsoon boundaries
    assert get_indian_ocean_season(datetime(2026, 6, 1)) == "Southwest Monsoon"
    assert get_indian_ocean_season(datetime(2026, 9, 30, 23, 59)) == "Southwest Monsoon"

    # Post-Monsoon boundaries
    assert get_indian_ocean_season(datetime(2026, 10, 1)) == "Post-Monsoon"
    assert get_indian_ocean_season(datetime(2026, 12, 31, 23, 59)) == "Post-Monsoon"

    # Winter boundaries (including leap year)
    assert get_indian_ocean_season(datetime(2026, 1, 1)) == "Winter"
    assert get_indian_ocean_season(datetime(2026, 2, 28)) == "Winter"
    assert get_indian_ocean_season(datetime(2024, 2, 29)) == "Winter"  # Leap year day

    # Pre-Monsoon boundaries
    assert get_indian_ocean_season(datetime(2026, 3, 1)) == "Pre-Monsoon"
    assert get_indian_ocean_season(datetime(2026, 5, 31, 23, 59)) == "Pre-Monsoon"

# -----------------------------------------------------------------------------
# 4. Statistical Anomaly Detection Ground Truth
# -----------------------------------------------------------------------------

def test_anomaly_detection_z_score_analytic():
    """
    Baseline: 10 observations with known distribution:
    5 observations of 20.0, 5 observations of 30.0.
    Mean = (5*20 + 5*30) / 10 = 25.0
    Sample Variance (N-1 = 9 df):
      5 * (20 - 25)^2 + 5 * (30 - 25)^2 = 5*25 + 5*25 = 250
      s^2 = 250 / 9 = 27.7777...
      s = sqrt(27.7777...) = 5.27046...

    Test points at threshold_sigma = 2.0:
    1. x = 25.0: z = |25 - 25| / 5.27 = 0.0 < 2.0 -> NOT ANOMALOUS
    2. x = 36.0: z = |36 - 25| / 5.27 = 11.0 / 5.27 = 2.087 >= 2.0 -> ANOMALOUS
    3. x = 14.0: z = |14 - 25| / 5.27 = 11.0 / 5.27 = 2.087 >= 2.0 -> ANOMALOUS
    """
    baseline = [20.0] * 5 + [30.0] * 5
    test_vals = [25.0, 36.0, 14.0]

    res = detect_anomalies(test_vals, baseline, threshold_sigma=2.0, min_baseline_samples=10)
    assert res["eligible"] is True
    assert res["anomaly_detected"] is True
    assert res["anomaly_count"] == 2
    assert 36.0 in res["anomalous_values"]
    assert 14.0 in res["anomalous_values"]
    assert 25.0 not in res["anomalous_values"]

# -----------------------------------------------------------------------------
# 5. Geodesic Haversine Distance Verification
# -----------------------------------------------------------------------------

def test_haversine_distance_accuracy():
    """
    Verifies great-circle distance:
    - Distance to identical coordinate is exactly 0.0 km.
    - Mangaluru Port (12.87°N, 74.88°E) to Karwar Port (14.80°N, 74.12°E):
      Geodesic distance is approximately 228 km (+/- 5 km WGS84 great-circle tolerance).
    """
    dist_self = haversine_distance_km(12.87, 74.88, 12.87, 74.88)
    assert dist_self == 0.0

    dist_karwar = haversine_distance_km(12.87, 74.88, 14.80, 74.12)
    assert 225.0 <= dist_karwar <= 235.0

# -----------------------------------------------------------------------------
# 6. Scientific Unit Compatibility & Incompatibility
# -----------------------------------------------------------------------------

def test_scientific_unit_compatibility_boundaries():
    # Valid synonym matches
    assert validate_unit_compatibility("°C", "celsius") is True
    assert validate_unit_compatibility("m", "meters") is True
    assert validate_unit_compatibility("knots", "kt") is True
    assert validate_unit_compatibility("s", "seconds") is True

    # Incompatible dimensions
    assert validate_unit_compatibility("°C", "m") is False
    assert validate_unit_compatibility("knots", "°C") is False
    assert validate_unit_compatibility("m", "s") is False

    # Different temperature scales without explicit conversion are incompatible
    assert validate_unit_compatibility("°C", "K") is False
