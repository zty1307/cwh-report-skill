import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_cwh_review_delivery import accepted_path, build_review_delivery
from cwh_pipeline_runtime import sha256_file
from run_cwh_inline_review import compact_hotword_packet, response_object, normalize_hotword_transport, normalize_topic_hit_transport, validate_transport_result
from docx import Document


def test_review_snapshot_never_changes_gate_and_missing_counts_stay_unknown(tmp_path):
    state = {"status": "waiting_ai", "input_contract": {"agenda": "本次会议"},
             "stages": [{"stage_id": "workbook", "status": "waiting_ai", "message": "需要审核"}]}
    state_path = tmp_path / "pipeline_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    original = state_path.read_bytes()
    result = build_review_delivery(tmp_path)
    assert state_path.read_bytes() == original
    assert result["status"] == "review_draft"
    payload = json.loads((tmp_path / "review_delivery/report_data.json").read_text(encoding="utf-8"))
    assert payload["audit"]["acceptance"]["ready_for_formal_delivery"] is False
    assert "暂不展示传播量" in "\n".join(p.text for p in Document(result["word"]).paragraphs)
    html = Path(result["dashboard"]).read_text(encoding="utf-8")
    assert "待审核稿 未通过正式交付" in html
    assert '"total_spread":null' in html


def test_modified_or_unaccepted_workbook_is_not_trusted(tmp_path):
    target = tmp_path / "data.xlsx"
    target.write_bytes(b"accepted")
    state = {"stages": [{"stage_id": "workbook", "status": "succeeded", "artifacts": {"workbook": str(target)},
                         "artifact_hashes": {"workbook": sha256_file(target)}}]}
    assert accepted_path(tmp_path, state, "workbook", "workbook") == target
    target.write_bytes(b"changed")
    assert accepted_path(tmp_path, state, "workbook", "workbook") is None


def test_hotword_compaction_keeps_candidates_and_only_exact_source_windows():
    text = "前文" * 100 + "政策工具" + "后文" * 200
    packet = {"candidates": [{"term": "政策工具"}, {"term": "无证据"}],
              "document_samples": [{"source_row": 3, "content_excerpt": text}]}
    result = compact_hotword_packet(packet)
    assert result["candidates"] == packet["candidates"]
    hit = result["candidate_source_windows"][0]["source_windows"][0]
    assert hit["excerpt"] == text[hit["excerpt_start_in_packet"]:hit["excerpt_end_in_packet"]]
    assert result["candidate_source_windows"][1]["source_windows"] == []
    assert "document_samples" in packet


def test_inline_transport_accepts_cli_result_not_unrelated_tool_text():
    payload = {"review_method": "ai_semantic_review", "items": [{"record_id": "real-id"}]}
    result = {"type": "result", "result": json.dumps(payload)}
    assert response_object("notice\n" + json.dumps(result)) == payload
    assert response_object(json.dumps({"result": json.dumps({"output_shape": payload})})) == payload


def test_fixed_hotword_rejection_is_audited_not_silently_padded():
    original = {"review_method": "ai_semantic_review", "selected": [{"term": "城市更新"}, {"term": "中央城市工作会议"}]}
    result = normalize_hotword_transport(original)
    assert [x["term"] for x in result["selected"]] == ["城市更新"]
    assert result["transport_exclusions"][0]["term"] == "中央城市工作会议"
    assert len(original["selected"]) == 2
    import pytest
    with pytest.raises(ValueError, match="below"):
        validate_transport_result("hotword", {"minimum_term_count": 36}, result)


def test_topic_hit_transport_accepts_indices_exact_titles_and_unique_aliases():
    packet = {
        "topic_titles": ["新型电网建设", "核准四个核电项目"],
        "topic_aliases": [["新型电网"], ["核电项目"]],
    }
    result = {"items": [
        {"record_id": "a", "topic_hits": ["核电项目", "2", 2]},
        {"record_id": "b", "topic_hits": ["新型电网建设"]},
    ]}
    normalized = normalize_topic_hit_transport(packet, result, "overseas")
    assert normalized["items"][0]["topic_hits"] == [2]
    assert normalized["items"][1]["topic_hits"] == [1]
    assert result["items"][0]["topic_hits"] == ["核电项目", "2", 2]


def test_topic_hit_transport_rejects_ambiguous_or_unknown_labels():
    import pytest
    packet = {"topic_titles": ["议题一", "议题二"], "topic_aliases": [["共同词"], ["共同词"]]}
    with pytest.raises(ValueError, match="unknown or ambiguous"):
        normalize_topic_hit_transport(packet, {"items": [{"topic_hits": ["共同词"]}]}, "overseas")
