"""Binary forecast evaluation on supplied, timestamped records only.

Input binary-evaluation.v1 has strict fields. Sources carry {id,url,observed_at}
with UTC ISO timestamps ending Z. Forecasts carry {id,question,issued_at,
resolves_at,probability,outcome,resolved_at,source_ids,outcome_source_ids}.
source_ids are evidence available by issue time; outcome_source_ids are dated
between scheduled resolution and recorded resolution. These timestamps are
caller declarations, not an external verification of source content.

Training includes outcomes available at split_at; holdout includes forecasts
issued at or after split_at. Other records are excluded explicitly. Baseline is
the training outcome rate. Nothing is fitted to holdout. Brier uses original
probabilities; log loss clips to [epsilon,1-epsilon], including the baseline.
Calibration bins are descriptive, fixed ten equal-width bins, left closed and
right open except that the final bin includes one. No calibration is fitted.
"""
from copy import deepcopy
from datetime import datetime
import math
import re
from urllib.parse import urlsplit


EPSILON = 1e-15
_DATASET_KEYS = {"schema_version", "source_mode", "split_at", "sources", "forecasts"}
_SOURCE_KEYS = {"id", "url", "observed_at"}
_FORECAST_KEYS = {"id", "question", "issued_at", "resolves_at", "probability", "outcome", "resolved_at",
                  "source_ids", "outcome_source_ids"}
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{name} has missing or unknown fields")


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"invalid {name}")


def _date(value, name):
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError(f"{name} must be a UTC ISO timestamp ending Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError(f"invalid {name}") from None


def _refs(value, sources, name):
    if type(value) is not list or not value:
        raise ValueError(f"{name} must be nonempty source IDs")
    for source_id in value:
        _text(source_id, name)
        if source_id not in sources:
            raise ValueError(f"unknown {name} reference")
    if len(value) != len(set(value)):
        raise ValueError(f"duplicate {name} references")


def _validate(dataset):
    _keys(dataset, _DATASET_KEYS, "dataset")
    if dataset["schema_version"] != "binary-evaluation.v1":
        raise ValueError("unsupported evaluation schema")
    if type(dataset["source_mode"]) is not str or dataset["source_mode"] not in {"synthetic", "observed"}:
        raise ValueError("source_mode must be synthetic or observed")
    split = _date(dataset["split_at"], "split_at")
    if type(dataset["sources"]) is not list or not dataset["sources"]:
        raise ValueError("dated sources required")
    sources = {}
    for source in dataset["sources"]:
        _keys(source, _SOURCE_KEYS, "source")
        _text(source["id"], "source.id")
        if source["id"] in sources:
            raise ValueError("duplicate source ID")
        _text(source["url"], "source.url")
        try:
            url = urlsplit(source["url"])
            valid_url = url.scheme in {"http", "https"} and bool(url.hostname) and not any(character.isspace() for character in source["url"])
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError("source.url must be HTTP(S)")
        sources[source["id"]] = _date(source["observed_at"], "source.observed_at")
    if type(dataset["forecasts"]) is not list or not dataset["forecasts"]:
        raise ValueError("forecasts required")
    ids, train, holdout, excluded = set(), [], [], []
    for forecast in dataset["forecasts"]:
        _keys(forecast, _FORECAST_KEYS, "forecast")
        _text(forecast["id"], "forecast.id")
        _text(forecast["question"], "forecast.question")
        if forecast["id"] in ids:
            raise ValueError("duplicate forecast ID")
        ids.add(forecast["id"])
        probability = forecast["probability"]
        if type(probability) not in {int, float} or not 0 <= probability <= 1 or not math.isfinite(probability):
            raise ValueError("probability must be finite in [0,1]")
        if type(forecast["outcome"]) is not int or forecast["outcome"] not in {0, 1}:
            raise ValueError("outcome must be integer zero or one")
        issued = _date(forecast["issued_at"], "issued_at")
        resolves = _date(forecast["resolves_at"], "resolves_at")
        resolved = _date(forecast["resolved_at"], "resolved_at")
        if issued >= resolves or resolved < resolves:
            raise ValueError("forecast and resolution chronology invalid")
        _refs(forecast["source_ids"], sources, "source_ids")
        _refs(forecast["outcome_source_ids"], sources, "outcome_source_ids")
        if any(sources[source_id] > issued for source_id in forecast["source_ids"]):
            raise ValueError("future evidence at forecast issue time")
        if any(not resolves <= sources[source_id] <= resolved for source_id in forecast["outcome_source_ids"]):
            raise ValueError("outcome source unavailable at resolution")
        if resolved <= split:
            train.append(forecast)
        elif issued >= split:
            holdout.append(forecast)
        else:
            excluded.append(forecast["id"])
    if not train or not holdout:
        raise ValueError("train and chronological holdout must both be nonempty")
    return train, holdout, excluded


def _scores(forecasts, fixed_probability=None):
    brier, log_loss = [], []
    for forecast in forecasts:
        probability = forecast["probability"] if fixed_probability is None else fixed_probability
        outcome = forecast["outcome"]
        brier.append((probability - outcome) ** 2)
        clipped = min(1 - EPSILON, max(EPSILON, probability))
        log_loss.append(-math.log(clipped) if outcome else -math.log1p(-clipped))
    return {"count": len(forecasts), "brier_score": math.fsum(brier) / len(forecasts),
            "log_loss": math.fsum(log_loss) / len(forecasts)}


def _bins(forecasts):
    result = []
    for index in range(10):
        members = [forecast for forecast in forecasts if min(9, int(forecast["probability"] * 10)) == index]
        result.append({"lower": index / 10, "upper": (index + 1) / 10, "upper_inclusive": index == 9,
                       "count": len(members),
                       "mean_probability": math.fsum(item["probability"] for item in members) / len(members) if members else None,
                       "outcome_rate": sum(item["outcome"] for item in members) / len(members) if members else None})
    return result


def evaluate_forecasts(dataset: dict) -> dict:
    """Validate chronology/provenance and score a holdout against train base rate."""
    train, holdout, excluded = _validate(dataset)
    base_rate = sum(forecast["outcome"] for forecast in train) / len(train)
    return {
        "schema_version": "binary-evaluation-result.v1", "split_at": dataset["split_at"],
        "counts": {"total": len(dataset["forecasts"]), "train": len(train), "holdout": len(holdout), "excluded": len(excluded)},
        "training_base_rate": base_rate, "holdout": _scores(holdout),
        "baseline": {"method": "training_outcome_base_rate", "probability": base_rate, **_scores(holdout, base_rate)},
        "calibration_bins": _bins(holdout), "calibration_method": "ten_fixed_equal_width_bins_no_fitting",
        "log_loss_epsilon": EPSILON, "log_loss_clipping": "[epsilon,1-epsilon]; Brier uses unmodified probabilities",
        "train_ids": [item["id"] for item in train], "holdout_ids": [item["id"] for item in holdout], "excluded_ids": excluded,
        "source_metadata": {"source_mode": dataset["source_mode"],
                            "status": "synthetic_fixture_only" if dataset["source_mode"] == "synthetic" else "caller_reported_unverified",
                            "sources": deepcopy(dataset["sources"])},
        "limitations": [
            "Scores describe supplied records only; relevance and representative historical coverage are not established.",
            "Source URLs, timestamps and outcomes are caller-reported; source content is not fetched or independently verified.",
            "Source observed_at is an unverified point-in-time declaration; source revisions and ingestion availability are not proven.",
            "Synthetic fixtures test scoring mechanics only and do not establish predictive performance.",
            "Descriptive calibration bins do not fit a calibrator or establish causality; no data is used to fit forecast probabilities.",
            "Forecasts issued before the cutoff but resolved after it are excluded from train and holdout.",
            "Training baseline excludes pending outcomes and may have duration or selection bias; it is not a representative population base rate.",
        ],
    }
