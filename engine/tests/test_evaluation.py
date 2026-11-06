"""Scoring mechanics on hand-calculated synthetic data, never historical claims."""
from copy import deepcopy
import math

import pytest


def dataset():
    return {
        "schema_version": "binary-evaluation.v1", "source_mode": "synthetic",
        "split_at": "2025-02-01T00:00:00Z",
        "sources": [
            {"id": "evidence", "url": "https://example.test/input", "observed_at": "2024-12-01T00:00:00Z"},
            {"id": "train-outcome", "url": "https://example.test/train", "observed_at": "2025-01-15T00:00:00Z"},
            {"id": "test-outcome", "url": "https://example.test/test", "observed_at": "2025-02-15T00:00:00Z"},
        ],
        "forecasts": [
            {"id": "train-0", "question": "Fictional training A?", "issued_at": "2025-01-01T00:00:00Z",
             "resolves_at": "2025-01-15T00:00:00Z", "resolved_at": "2025-01-16T00:00:00Z",
             "probability": 0.4, "outcome": 0, "source_ids": ["evidence"], "outcome_source_ids": ["train-outcome"]},
            {"id": "train-1", "question": "Fictional training B?", "issued_at": "2025-01-01T00:00:00Z",
             "resolves_at": "2025-01-15T00:00:00Z", "resolved_at": "2025-01-16T00:00:00Z",
             "probability": 0.6, "outcome": 1, "source_ids": ["evidence"], "outcome_source_ids": ["train-outcome"]},
            {"id": "test-0", "question": "Fictional holdout A?", "issued_at": "2025-02-01T00:00:00Z",
             "resolves_at": "2025-02-15T00:00:00Z", "resolved_at": "2025-02-16T00:00:00Z",
             "probability": 0.25, "outcome": 0, "source_ids": ["evidence"], "outcome_source_ids": ["test-outcome"]},
            {"id": "test-1", "question": "Fictional holdout B?", "issued_at": "2025-02-02T00:00:00Z",
             "resolves_at": "2025-02-15T00:00:00Z", "resolved_at": "2025-02-16T00:00:00Z",
             "probability": 0.75, "outcome": 1, "source_ids": ["evidence"], "outcome_source_ids": ["test-outcome"]},
        ],
    }


def evaluate(value):
    from decision_lab.evaluation import evaluate_forecasts
    return evaluate_forecasts(value)


def test_hand_calculated_holdout_scores_training_only_baseline_and_fixed_bins():
    value = dataset()
    before = deepcopy(value)
    result = evaluate(value)
    assert value == before
    assert result["counts"] == {"total": 4, "train": 2, "holdout": 2, "excluded": 0}
    assert result["training_base_rate"] == 0.5
    assert result["holdout"]["brier_score"] == 0.0625
    assert result["holdout"]["log_loss"] == pytest.approx(0.2876820724517809)
    assert result["baseline"]["brier_score"] == 0.25
    assert result["baseline"]["log_loss"] == pytest.approx(0.6931471805599453)
    bins = result["calibration_bins"]
    assert len(bins) == 10
    assert sum(row["count"] for row in bins) == 2
    assert bins[2]["count"] == bins[7]["count"] == 1
    assert bins[2]["mean_probability"] == 0.25
    assert bins[2]["outcome_rate"] == 0
    assert bins[7]["outcome_rate"] == 1
    assert bins[0]["mean_probability"] is None
    assert result["source_metadata"]["status"] == "synthetic_fixture_only"
    assert result["source_metadata"]["sources"] == value["sources"]


def test_chronology_excludes_unresolved_training_period_without_leaking_holdout_into_base_rate():
    value = dataset()
    bridge = deepcopy(value["forecasts"][2])
    bridge.update(id="bridge", issued_at="2025-01-25T00:00:00Z", outcome=1)
    value["forecasts"].append(bridge)
    value["forecasts"][0]["outcome"] = 1
    result = evaluate(value)
    assert result["counts"] == {"total": 5, "train": 2, "holdout": 2, "excluded": 1}
    assert result["training_base_rate"] == 1
    assert result["excluded_ids"] == ["bridge"]
    assert math.isfinite(result["baseline"]["log_loss"])


def test_probability_extremes_are_binned_and_log_loss_is_clipped_only_for_scoring():
    value = dataset()
    value["forecasts"][2].update(probability=1, outcome=0)
    value["forecasts"][3].update(probability=0, outcome=1)
    result = evaluate(value)
    assert result["holdout"]["brier_score"] == 1
    assert result["holdout"]["log_loss"] == pytest.approx(-math.log(1e-15), rel=1e-4)
    assert result["log_loss_epsilon"] == 1e-15
    assert result["calibration_bins"][9]["mean_probability"] == 1
    assert result["calibration_bins"][0]["mean_probability"] == 0


@pytest.mark.parametrize("field,value", [
    ("probability", True), ("probability", "0.5"), ("probability", float("nan")),
    ("probability", float("inf")), ("probability", -0.1), ("probability", 1.1),
    ("outcome", True), ("outcome", 0.0), ("outcome", 2), ("question", " "),
    ("id", ""), ("issued_at", "2025-02-01"), ("issued_at", "2025-02-01T00:00:00"),
    ("issued_at", "2025-02-01T00:00:00+02:00"),
    ("issued_at", "2025-02-15T00:00:00Z"), ("resolved_at", "2025-02-14T00:00:00Z"),
    ("source_ids", []), ("source_ids", ["missing"]), ("source_ids", ["evidence", "evidence"]),
    ("source_ids", ["test-outcome"]), ("outcome_source_ids", ["evidence"]),
    ("outcome_source_ids", ["missing"]), ("outcome_source_ids", []), ("extra", "unknown"),
])
def test_rejects_invalid_records_and_future_evidence(field, value):
    raw = dataset()
    raw["forecasts"][2][field] = value
    with pytest.raises(ValueError):
        evaluate(raw)


@pytest.mark.parametrize("change", [
    {"source_mode": "real"}, {"source_mode": []}, {"schema_version": "other"},
    {"split_at": "2024-01-01T00:00:00Z"}, {"split_at": "2026-01-01T00:00:00Z"},
    {"split_at": "2025-02-01"}, {"forecasts": []}, {"sources": []}, {"extra": 1},
])
def test_rejects_invalid_dataset_or_empty_chronological_partition(change):
    value = dataset()
    value.update(change)
    with pytest.raises(ValueError):
        evaluate(value)


@pytest.mark.parametrize("field,value", [("url", "file:///tmp/data"), ("url", "https://"),
                                         ("url", 2), ("observed_at", "tomorrow"), ("id", " ")])
def test_source_references_require_dated_http_provenance(field, value):
    raw = dataset()
    raw["sources"][0][field] = value
    with pytest.raises(ValueError):
        evaluate(raw)


def test_duplicate_forecast_or_source_ids_and_missing_fields_fail_closed():
    for part in ("forecasts", "sources"):
        value = dataset()
        value[part].append(deepcopy(value[part][0]))
        with pytest.raises(ValueError):
            evaluate(value)
    for part, field in (("forecasts", "probability"), ("sources", "observed_at")):
        value = dataset()
        del value[part][0][field]
        with pytest.raises(ValueError):
            evaluate(value)


def test_observed_provenance_stays_caller_reported_and_unverified():
    value = dataset()
    value["source_mode"] = "observed"
    result = evaluate(value)
    assert result["source_metadata"]["status"] == "caller_reported_unverified"
    assert result["source_metadata"]["source_mode"] == "observed"
    assert any("representative" in line for line in result["limitations"])
