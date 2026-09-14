import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_worker_observations import permission_denials
from run_cwh_model_worker import write_transport_blocker, run_host_semantic_task
from cwh_host_research import HostModelError
from run_cwh_batched_viewpoints import cached_batch, merge_topic_bundles
from run_cwh_resumable_pipeline import maybe_run_ai_worker, StageSpec
from cwh_authoring_packet import compact_authoring_references
from cwh_json_transport import load_framed_json, normalize_authoring_envelope
from run_cwh_inline_review import response_object


def bundle(topic):
    return {"viewpoints": {"by_topic": [{"topic": topic, "clusters": []}]}, "research_audit": {
        "domestic_media_research": {"registry_version": "test", "execution_profile": "bounded_60m",
            "required_source_ids": ["source"], "open_search_completed": True,
            "coverage_by_topic": [{"topic": topic}],
            "candidate_pool_by_topic": [{"topic": topic, "candidates": []}],
            "public_article_corpus_review": {"topic_reviews": [{"topic": topic}]}}}}


def test_permissions_are_read_from_tool_results_even_with_false_is_error():
    error = "Error: Permission to use WebFetch has been denied because this tool requires approval"
    blocks = [{"type": "tool_use", "id": "fetch-1", "name": "WebFetch"},
              {"type": "tool_result", "tool_use_id": "fetch-1", "is_error": False,
               "content": {"type": "text", "text": error}}]
    log = json.dumps({"message": {"content": blocks}})
    assert permission_denials(log) == [{"tool": "WebFetch", "tool_use_id": "fetch-1", "reason": "host_permission_denied"}]
    assert not permission_denials(json.dumps({"message": {"content": [{"type": "text", "text": error}]}}))
    assert not permission_denials("not json\n[]\n" + json.dumps({"message": {"content": "bad"}}))


def test_merge_requires_all_topics_and_preserves_evidence_boundaries():
    parts = [bundle("甲"), bundle("乙")]
    original = copy.deepcopy(parts)
    merged = merge_topic_bundles(parts, ["甲", "乙"], 100, "host-run")
    assert merged["metadata"]["authoring_run_id"] == "host-run"
    assert "meeting_date" not in merged["metadata"]
    assert len(merged["viewpoints"]["by_topic"]) == 2
    assert "semantic_review" not in merged
    assert merged["research_audit"]["domestic_media_research"]["pool_summary"]["raw_monitoring_candidate_count"] == 100
    assert parts == original
    with pytest.raises(ValueError):
        merge_topic_bundles(parts[:1], ["甲", "乙"], 100, "host-run")
    parts[1]["research_audit"]["domestic_media_research"]["public_article_corpus_review"]["topic_reviews"][0]["topic"] = "甲"
    with pytest.raises(ValueError, match="corpus review"):
        merge_topic_bundles(parts, ["甲", "乙"], 100, "host-run")


def test_cache_checks_inputs_outputs_and_never_certifies_semantics(tmp_path):
    packet = {"topic": "甲", "source_sha256": "hash"}
    digest, result, _ = cached_batch(tmp_path, 1, packet)
    assert result is None
    output = tmp_path / "topic-1.output.json"
    output.write_text(json.dumps(bundle("甲")), encoding="utf-8")
    (tmp_path / "topic-1.cache.json").write_text(json.dumps({"input_sha256": digest,
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "session_id": "prior"}), encoding="utf-8")
    assert cached_batch(tmp_path, 1, packet)[2] == "prior"
    assert cached_batch(tmp_path, 1, dict(packet, source_sha256="changed"))[1] is None
    output.write_text("{}", encoding="utf-8")
    assert cached_batch(tmp_path, 1, packet)[1] is None


def test_compact_contract_retains_source_rules_not_later_stage_templates():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "references/analysis_bundle_schema.md").read_text(encoding="utf-8")
    registry = (root / "config/source_registry.v1.json").read_text(encoding="utf-8")
    result = compact_authoring_references(schema, registry, {"topic": "通用议题",
        "stable_source_tasks": [{"source_id": "test_source", "must_check": True}]})
    assert len(json.dumps(result, ensure_ascii=False)) < 12000
    shape = result["output_shape"]
    assert "comments" not in shape
    research = shape["research_audit"]["domestic_media_research"]
    assert research["required_source_ids"] == ["test_source"]
    assert research["registry_version"] == json.loads(registry)["version"]
    evidence = shape["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    assert "source_excerpt" in evidence and "formal_claim" in evidence
    assert "semantic_review" not in evidence


def test_only_unambiguous_json_framing_is_repaired_with_audit():
    result = response_object(json.dumps({"type": "result", "result":
        '{"metadata":{},"research_audit":{"domestic_media_research":{},"viewpoints":{"by_topic":[]}}'}))
    assert result["viewpoints"] == {"by_topic": []}
    assert [x["kind"] for x in result["transport_repairs"]] == ["closed_containers_at_eof", "moved_unique_misnested_viewpoints"]
    assert normalize_authoring_envelope(result) == result
    for text in ('{"items":[{"text":"unfinished', '{"items":', '{"items":[],', '{"items":[}'):
        with pytest.raises(ValueError):
            load_framed_json(text)


@pytest.mark.parametrize("exit_code", [23, 124])
def test_permission_blockers_and_exhausted_requests_do_not_loop(tmp_path, exit_code):
    runner = mock.Mock()
    runner.root = tmp_path
    runner.input_contract = {"ai_worker_command": ["worker", "{task}"]}
    runner.remaining_budget_seconds.return_value = None
    runner.run_command.return_value = (exit_code, tmp_path / "worker.log")
    outcome = maybe_run_ai_worker(runner, StageSpec("domestic_viewpoints", "viewpoints", transient_exit_codes=(124,)),
                                 tmp_path / "task.json", tmp_path / "output.json")
    assert outcome.retryable is False


def test_rate_limit_becomes_resumable_wait_without_consuming_retry(tmp_path):
    runner = mock.Mock()
    runner.root = tmp_path
    runner.input_contract = {"ai_worker_command": ["worker", "{task}"]}
    runner.remaining_budget_seconds.return_value = None
    runner.run_command.return_value = (29, tmp_path / "worker.log")
    workspace = tmp_path / "worker" / "domestic_viewpoints"
    workspace.mkdir(parents=True)
    (workspace / "compiled_blocker.json").write_text(json.dumps({
        "transport_category": "rate_limited",
        "retry_after": "2026-09-15 00:12:59 UTC+8",
        "exit_code": 29,
    }), encoding="utf-8")
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"stage_workspace": str(workspace)}), encoding="utf-8")
    outcome = maybe_run_ai_worker(
        runner,
        StageSpec("domestic_viewpoints", "viewpoints"),
        task,
        tmp_path / "output.json",
    )
    assert outcome.status == "waiting_ai"
    assert outcome.retryable is False
    assert outcome.details["reason"] == "provider_rate_limited"
    assert outcome.details["retry_after"] == "2026-09-15 00:12:59 UTC+8"


def test_network_failure_becomes_resumable_wait_without_consuming_retry(tmp_path):
    runner = mock.Mock()
    runner.root = tmp_path
    runner.input_contract = {"ai_worker_command": ["worker", "{task}"]}
    runner.remaining_budget_seconds.return_value = None
    runner.run_command.return_value = (28, tmp_path / "worker.log")
    workspace = tmp_path / "worker" / "domestic_evidence_verification"
    workspace.mkdir(parents=True)
    (workspace / "compiled_blocker.json").write_text(json.dumps({
        "transport_category": "network_unavailable",
        "retry_after": "",
        "exit_code": 28,
    }), encoding="utf-8")
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"stage_workspace": str(workspace)}), encoding="utf-8")
    outcome = maybe_run_ai_worker(
        runner,
        StageSpec("domestic_evidence_verification", "review"),
        task,
        tmp_path / "output.json",
    )
    assert outcome.status == "waiting_ai"
    assert outcome.retryable is False
    assert outcome.details["reason"] == "provider_network_unavailable"
    assert outcome.details["transport_category"] == "network_unavailable"


def test_generic_worker_blocker_contains_only_sanitized_transport_fields(tmp_path):
    write_transport_blocker(tmp_path, {
        "category": "rate_limited",
        "retry_after": "2026-09-15 00:12:59 UTC+8",
        "exit_code": 29,
        "provider_private_message": "must not persist",
    })
    blocker = json.loads((tmp_path / "blocker.json").read_text(encoding="utf-8"))
    assert blocker == {
        "blocker": True,
        "type": "model_transport_error",
        "transport_category": "rate_limited",
        "retry_after": "2026-09-15 00:12:59 UTC+8",
        "exit_code": 29,
    }


def test_direct_comment_or_hotword_adapter_propagates_rate_limit(tmp_path):
    workspace = tmp_path / "worker"
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"stage_workspace": str(workspace)}), encoding="utf-8")
    def limited(_):
        raise HostModelError("rate limited", 29, category="rate_limited", retry_after="soon")
    with pytest.raises(SystemExit) as error:
        run_host_semantic_task(task, limited)
    assert error.value.code == 29
    blocker = json.loads((workspace / "blocker.json").read_text(encoding="utf-8"))
    assert blocker["transport_category"] == "rate_limited"
    assert blocker["retry_after"] == "soon"
