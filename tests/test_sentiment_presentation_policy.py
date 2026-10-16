import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cwh_presentation_policy as policy
import report_rules
import formalize_cwh_report as formal


def ready_row():
    return {"sentiment_formal_ready": True, "sentiment_sample_status": "ready",
        "sentiment_authority": "large_scale_sentiment_analysis", "sentiment_denominator": 1000,
        "sentiment": {"positive": 900, "neutral": 90, "negative": 10}}


def test_current_stage_keeps_formal_percentages_blank_even_above_sample_threshold():
    row = ready_row()
    before = copy.deepcopy(row)
    assert not policy.sentiment_percentages_enabled()
    assert not report_rules.formal_sentiment_row_ready(row)
    assert not report_rules.formal_sentiment_available({"topic_stats": [row]})
    assert formal.sentiment_ratio_cells(row) == ["", "", ""]
    assert row == before


def test_explicit_future_policy_still_requires_original_review_gates(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"sentiment_percentages": {"mode": "reviewed"}}))
    monkeypatch.setattr(policy, "POLICY_PATH", path)
    assert report_rules.formal_sentiment_row_ready(ready_row())
    row = ready_row()
    row["sentiment_denominator"] = 0
    assert not report_rules.formal_sentiment_row_ready(row)
