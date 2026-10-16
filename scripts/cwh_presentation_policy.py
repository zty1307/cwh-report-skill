"""Shared output policy; it never changes comment evidence or classification."""
import json
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "config/report_presentation_policy.v1.json"


def sentiment_percentages_enabled():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    mode = policy["sentiment_percentages"]["mode"]
    if mode not in {"withheld", "reviewed"}:
        raise ValueError("Unknown sentiment percentage presentation policy")
    return mode == "reviewed"
