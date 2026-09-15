import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_host_research import observed_tools, search_rows, semantic_json, stream_metrics, terminal_transport_error, collect_topic, HostModelError
from cwh_semantic_compiler import make_packet, compile_topic, domain_matches
from cwh_semantic_compiler import web_metadata_errors
from cwh_semantic_compiler import labeled_publication_date, exclude_certain_period_misses
from cwh_semantic_compiler import duplicate_voice_errors
from cwh_json_transport import escape_cjk_internal_quotes
from run_cwh_inline_review import response_object


def test_cjk_quote_transport_repair_preserves_decoded_text_not_claim_content():
    malformed = '{"items":[{"id":"r1","claim":"国民健康"十五五"规划"}]}'
    repaired = response_object(json.dumps({'type': 'result', 'result': malformed}, ensure_ascii=False))
    assert repaired['items'][0]['claim'] == '国民健康"十五五"规划'
    assert repaired['transport_repairs'][0]['kind'] == 'escaped_cjk_internal_quotes'
    assert escape_cjk_internal_quotes('{"items":[{"id":"r1" "claim":"少逗号"}]}') is None
    assert escape_cjk_internal_quotes('{"items":[{"id":"r1","claim":"截断') is None
    assert escape_cjk_internal_quotes('{"items":[{"bad"键":"值"}]}') is None


def test_duplicate_voice_feedback_names_all_conflicting_items_and_clusters():
    result = duplicate_voice_errors({"items": [
        {"id": "r1", "decision": "eligible", "claims": [{"speaker": "同一专家", "cluster": "k1"}]},
        {"id": "r2", "decision": "eligible", "claims": [{"speaker": "同一专家", "cluster": "k2"}]}]})
    assert len(result) == 1
    assert all(value in result[0] for value in ("同一专家", "r1", "r2", "k1", "k2"))


def test_explicit_outside_publication_date_is_excluded_with_verbatim_audit():
    content = "发布日期：\n2026年08月18日\n会议通过日期2026年7月31日"
    evidence = labeled_publication_date(content)
    assert evidence["date"] == "2026-08-18"
    assert content[evidence["start"]:evidence["end"]] == evidence["quote"]
    packet = {"period": {"start": "2026-07-31", "end": "2026-08-03"},
              "items": [{"id": "w1", "origin": "web", "content": content}]}
    original = {"items": [{"id": "w1", "decision": "eligible", "claims": [{"claim": "期外观点"}]}]}
    result = exclude_certain_period_misses(packet, original)
    assert result["items"][0]["decision"] == "excluded"
    assert result["items"][0]["claims"] == []
    assert result["items"][0]["transport_exclusions"][0]["original_review"] == original["items"][0]
    assert original["items"][0]["decision"] == "eligible"
    assert labeled_publication_date("成文日期：2026年08月18日") is None
    assert labeled_publication_date("发布日期：2026-08-18\n发布时间：2026-08-19") is None


def test_web_metadata_precheck_reports_all_fields_and_records():
    packet = {"period": {"start": "2026-01-01", "end": "2026-01-02"},
              "items": [{"id": "w1", "origin": "web", "content": "无来源日期"},
                        {"id": "w2", "origin": "web", "content": "日报 2026-01-02"}]}
    decision = {"items": [{"id": "w1", "decision": "eligible"},
                           {"id": "w2", "decision": "eligible", "source": "日报",
                            "published_at": "2026-01-02", "date_quote": "2026-01-02"}]}
    errors = web_metadata_errors(packet, decision)
    assert len(errors) == 2
    assert errors[0] == "Web publisher not anchored in original text: w1"
    assert errors[1].startswith("Web publication date not anchored in original text: w1 ")
    assert "year-month-day" in errors[1]
from cwh_public_reader import check_public_url
from complete_cwh_evidence_structure import complete_analysis_structure
from normalize_cwh_analysis import normalize_analysis
from domestic_evidence_mapping import validate_analysis_mapping
from run_cwh_compiled_worker import compile_review, balanced_fetch_urls, cached_public_pages, semantic_packet, independent_packet
from run_cwh_compiled_worker import batch_author_contract


def test_batch_contract_names_all_topics_and_item_ids_without_source_text():
    packets = [{"topic": "议题甲", "items": [{"id": "r1", "content": "不重复原文"}]},
               {"topic": "议题乙", "items": [{"id": "r1"}, {"id": "w2"}]}]
    prompt = batch_author_contract(packets)
    manifest = json.loads(prompt.split("清单：", 1)[1])
    assert manifest == [{"topic": "议题甲", "required_item_ids": ["r1"]},
                        {"topic": "议题乙", "required_item_ids": ["r1", "w2"]}]
    assert "不重复原文" not in prompt
    assert '"topics":' in prompt


def fixture():
    text = "本报认为，公共服务布局需要适应人口变化，在加强资源统筹的同时保留必要的服务覆盖，避免仅按常住人口总量机械调整，使实际需求能够得到更充分的回应。"
    raw = [{"record_id": "raw-1", "source": "测试日报", "title": "布局应适应实际需求", "url": "https://example.test/a",
            "published_at": "2026-05-16", "content": text}]
    queries = [{"source_id": "lane", "query_id": "q1", "query": "site:source.test 2026-05-15 公共服务 评论",
                "route": "public_platform", "round": 1, "backend": "observed", "executed_at": "2026-05-16T00:00:00Z",
                "status": "completed", "result_count": 1, "results": [{"url": "https://wrong.test/a", "title": "搜索结果", "snippet": "相关摘要"}],
                "result_urls": ["https://wrong.test/a"]},
               {"source_id": "open_web", "query_id": "q2", "query": "2026-05-15 公共服务 布局 评论", "route": "open_web", "round": 2,
                "backend": "observed", "executed_at": "2026-05-16T00:00:00Z", "status": "completed", "result_count": 0,
                "results": [], "result_urls": []}]
    observation = {"queries": queries}
    packet = make_packet("公共服务", {"start": "2026-05-15", "end": "2026-05-18"}, raw, observation, [])
    decision = {"items": [{"id": "r1", "decision": "eligible", "reason": "有独立政策建议", "relevant": True,
                           "claims": [{"speaker": "测试日报", "role": "", "speaker_type": "media_voice", "quote": text,
                                       "claim": text[5:], "cluster": "k1"}]},
                          {"id": "w1", "decision": "excluded", "reason": "未获取原文", "relevant": True, "claims": []}],
                "heading": "建议按实际需求优化布局", "clusters": [{"key": "k1", "heading": "建议统筹人口变化与服务覆盖"}]}
    plan = {"stable_source_tasks": [{"source_id": "lane", "must_check": True}]}
    return packet, decision, observation, plan


def compiled():
    packet, decision, observation, plan = fixture()
    bundle = compile_topic(packet, decision, observation, plan, "bounded_60m", "v1", "author")
    bundle["metadata"] = {"evidence_mapping_version": "1.0", "authoring_run_id": "author"}
    return normalize_analysis(complete_analysis_structure(bundle))


def test_host_compiler_keeps_source_and_does_not_self_certify():
    bundle = compiled()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    assert "semantic_review" not in evidence
    assert validate_analysis_mapping(bundle, require_semantic_review=False)["status"] == "passed"
    assert validate_analysis_mapping(bundle)["status"] == "blocked"


def test_packet_sends_complete_source_once_and_ranges_compile_exactly():
    packet, decision, observation, plan = fixture()
    outgoing = semantic_packet(packet)
    raw = outgoing['items'][0]
    assert 'content' not in raw and 'capture' not in raw
    assert ''.join(seg['text'] for seg in raw['segments']) == packet['items'][0]['content']
    claim = decision['items'][0]['claims'][0]
    claim.pop('quote')
    claim['quote_range'] = [raw['segments'][0]['id'], raw['segments'][0]['id']]
    bundle = compile_topic(packet, decision, observation, plan, 'bounded_60m', 'v1', 'author')
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    assert ev['source_excerpt'] == packet['items'][0]['content'][ev['source_excerpt_start']:ev['source_excerpt_end']]


def test_fetch_budget_is_distributed_across_queries_and_never_invents_urls():
    obs = {'queries': [{'results': [{'url': 'a'}, {'url': 'b'}, {'url': 'c'}]},
                       {'results': [{'url': 'a'}, {'url': 'd'}]}, {'results': [{'url': 'e'}]}]}
    assert balanced_fetch_urls(obs, 3) == ['a', 'd', 'e']
    assert obs['queries'][0]['results'][0]['url'] == 'a'


def test_site_miss_is_not_counted_as_lane_hit():
    checks = compiled()["research_audit"]["domestic_media_research"]["coverage_by_topic"][0]["checks"]
    assert checks[0]["status"] == "access_failed"
    assert checks[0]["candidate_ids"] == []
    assert domain_matches("https://sub.source.test/a", ["source.test"])
    assert not domain_matches("https://source.test.evil.test/a", ["source.test"])


def test_missing_or_duplicate_semantic_decisions_rejected():
    packet, decision, observation, plan = fixture()
    decision["items"].append(copy.deepcopy(decision["items"][0]))
    with pytest.raises(ValueError, match="exactly once"):
        compile_topic(packet, decision, observation, plan, "bounded_60m", "v1", "author")


def test_same_voice_same_cluster_keeps_first_and_preserves_later_claim_as_reserve():
    packet, decision, observation, plan = fixture()
    later = copy.deepcopy(decision["items"][0]["claims"][0])
    later["claim"] = "另一条观点不得拼接进入第一条正式观点"
    decision["items"][0]["claims"].append(later)
    bundle = compile_topic(packet, decision, observation, plan, "bounded_60m", "v1", "author")
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["formal_claim"] != later["claim"]
    reserve = bundle["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][1]
    assert reserve["formal_use"] == "reserve" and reserve["semantic_claim"] == later
    assert "semantic_review" not in reserve


def test_same_voice_different_clusters_reserves_later_bounded_voice_without_merging():
    packet, decision, observation, plan = fixture()
    later = copy.deepcopy(decision["items"][0]["claims"][0])
    later["cluster"] = "k2"
    decision["items"][0]["claims"].append(later)
    decision["clusters"].append({"key": "k2", "heading": "另一个簇"})
    bounded = compile_topic(packet, decision, observation, plan, "bounded_60m", "v1", "author")
    pool = bounded["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"]
    reserved = [row for row in pool if row.get("formal_use") == "reserve"]
    assert len(reserved) == 1
    assert reserved[0]["semantic_claim"]["cluster"] == "k2"
    assert "不合并或改写" in reserved[0]["reserve_reason"]
    with pytest.raises(ValueError, match="semantic consolidation"):
        compile_topic(packet, decision, observation, plan, "exhaustive", "v1", "author")


def test_search_snippet_never_becomes_full_source():
    packet, decision, observation, plan = fixture()
    decision["items"][1]["decision"] = "eligible"
    decision["items"][1]["claims"] = decision["items"][0]["claims"]
    with pytest.raises(ValueError, match="full text"):
        compile_topic(packet, decision, observation, plan, "bounded_60m", "v1", "author")


def test_metadata_publisher_attribution_does_not_allow_fake_expert():
    bundle = compiled()
    ev = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    ev["speaker_name"] = "捏造媒体"
    ev["attribution"] = "捏造媒体"
    assert any(i["code"] == "speaker_not_in_excerpt" for i in validate_analysis_mapping(bundle, require_semantic_review=False)["issues"])
    ev["speaker_name"] = "测试日报"
    ev["attribution_status"] = "named_person"
    assert any(i["code"] == "speaker_not_in_excerpt" for i in validate_analysis_mapping(bundle, require_semantic_review=False)["issues"])


def test_reviewer_compilation_preserves_rejected_verdict():
    bundle = compiled()
    ev = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    result = {"reviews": [{"id": "e1", "verdict": "unsupported", "rationale": "语义不完全支持", "propositions": [
        {"text": ev["formal_claim"], "verdict": "unsupported", "source_quote": ev["source_excerpt"], "rationale": "不足"}]}]}
    review = compile_review(bundle, result, {"session_id": "reviewer", "completed_at": "2026-05-17"}, "hash")
    assert review["reviews"][0]["verdict"] == "unsupported"
    assert review["reviews"][0]["propositions"][0]["source_quote_start"] == 0
    assert review["source_bundle_sha256"] == "hash"


def test_review_source_lookup_is_topic_scoped():
    bundle = compiled()
    second = copy.deepcopy(bundle["viewpoints"]["by_topic"][0])
    second["topic"] = "另一个议题"
    second_pool = copy.deepcopy(bundle["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0])
    second_pool["topic"] = second["topic"]
    second_pool["candidates"][0]["source_snapshot"]["source_text"] = "前缀。" + second_pool["candidates"][0]["source_snapshot"]["source_text"]
    second_ev = second["clusters"][0]["evidence"][0]
    second_ev.update(evidence_id="second-evidence", source_excerpt_start=3, source_excerpt_end=3 + len(second_ev["source_excerpt"]))
    bundle["viewpoints"]["by_topic"].append(second)
    bundle["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"].append(second_pool)
    reviews = [{"id": f"e{n}", "verdict": "fully_supported", "rationale": "unit fixture", "propositions": [
        {"text": e["formal_claim"], "verdict": "fully_supported", "source_quote": e["source_excerpt"], "rationale": "unit fixture"}]} for n, e in enumerate(
            [bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0], second_ev], 1)]
    result = compile_review(bundle, {"reviews": reviews}, {"session_id": "reviewer", "completed_at": "time"}, "hash")
    assert [r["propositions"][0]["source_quote_start"] for r in result["reviews"]] == [0, 3]


def test_independent_packet_does_not_merge_different_segment_namespaces():
    bundle = compiled()
    rows = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence']
    alternate = copy.deepcopy(rows[0])
    alternate.update(evidence_id='alternate', source_segment_scope='p123', source_segment_scheme='sentence_v2')
    rows.append(alternate)
    packet = independent_packet(bundle)
    assert len(packet['sources']) == 2
    assert packet['claims'][0]['source_id'] != packet['claims'][1]['source_id']
    assert all('source_text' not in source for source in packet['sources'])
    assert all('segments' not in source for source in packet['sources'])
    assert packet['claims'][1]['excerpt_segments'][0]['id'] == 'e2/1'
    assert ''.join(s['text'] for s in packet['claims'][1]['excerpt_segments']) == alternate['source_excerpt']


def test_independent_packet_carries_current_topic_and_original_event_title_without_rewriting_quotes():
    bundle = compiled()
    candidate = bundle['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates'][0]
    candidate['title'] = '另一场会议的公共服务政策解读'
    original = copy.deepcopy(bundle)
    packet = independent_packet(bundle)
    assert packet['agenda_topics'] == ['公共服务']
    assert packet['claims'][0]['topic'] == '公共服务'
    assert packet['sources'][0]['title'] == candidate['title']
    assert packet['sources'][0]['reference_context'] == candidate['source_snapshot']['source_text'][:2000]
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    assert ''.join(row['text'] for row in packet['claims'][0]['excerpt_segments']) == ev['source_excerpt']
    assert bundle == original


def test_independent_reference_context_is_bounded_and_not_added_to_claim_evidence():
    bundle = compiled()
    candidate = bundle['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates'][0]
    candidate['source_snapshot']['source_text'] += '\n背景对象' * 800
    original = copy.deepcopy(bundle)
    packet = independent_packet(bundle)
    assert len(packet['sources'][0]['reference_context']) == 2000
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    assert ''.join(s['text'] for s in packet['claims'][0]['excerpt_segments']) == ev['source_excerpt']
    assert bundle == original


def test_reference_expansion_flag_is_textual_not_a_guessed_meeting_identity():
    bundle = compiled()
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    assert independent_packet(bundle)['claims'][0]['reference_expansion_required'] is False
    ev['formal_claim'] = '本次会议提出，' + ev['formal_claim']
    assert independent_packet(bundle)['claims'][0]['reference_expansion_required'] is True
    ev['formal_claim'] = ev['formal_claim'].replace('本次会议', '另一场工作会议')
    assert independent_packet(bundle)['claims'][0]['reference_expansion_required'] is False


def test_review_range_extracts_frozen_text_without_certifying_support():
    bundle = compiled()
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    result = {'reviews': [{'id': 'e1', 'verdict': 'uncertain', 'rationale': '需要语义确认', 'propositions': [
        {'text': ev['formal_claim'], 'verdict': 'uncertain', 'source_range': [1, 1], 'rationale': '未完全支持'}]}]}
    packet = compile_review(bundle, result, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')
    proposition = packet['reviews'][0]['propositions'][0]
    assert proposition['source_quote'] == ev['source_excerpt']
    assert proposition['verdict'] == 'uncertain'
    ev['source_excerpt_start'] = 1
    with pytest.raises(ValueError, match='within the frozen excerpt'):
        compile_review(bundle, result, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')


def test_claim_local_ranges_extract_only_the_verified_excerpt():
    bundle = compiled()
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    result = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': 'unit', 'propositions': [
        {'text': ev['formal_claim'], 'verdict': 'fully_supported', 'source_range': ['e1/1', 'e1/1'], 'rationale': 'unit'}]}]}
    review = compile_review(bundle, result, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')
    assert review['reviews'][0]['propositions'][0]['source_quote'] == ev['source_excerpt']
    result['reviews'][0]['propositions'][0]['source_range'] = ['e2/1', 'e2/1']
    with pytest.raises(ValueError):
        compile_review(bundle, result, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')


def test_local_excerpt_preserves_nonzero_original_position_and_context():
    bundle = compiled()
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    candidate = bundle['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates'][0]
    prefix, suffix = '开头上下文，不属于允许引用片段。\n', '\n结尾限定条件也必须保留。'
    candidate['source_snapshot']['source_text'] = prefix + ev['source_excerpt'] + suffix
    ev['source_excerpt_start'] += len(prefix)
    ev['source_excerpt_end'] += len(prefix)
    packet = independent_packet(bundle)
    assert 'source_text' not in packet['sources'][0]
    assert ''.join(s['text'] for s in packet['claims'][0]['excerpt_segments']) == ev['source_excerpt']
    decision = {'reviews': [{'id': 'e1', 'verdict': 'uncertain', 'rationale': 'unit', 'propositions': [
        {'text': ev['formal_claim'], 'verdict': 'uncertain', 'source_range': ['e1/1', 'e1/1'], 'rationale': 'unit'}]}]}
    result = compile_review(bundle, decision, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')
    proposition = result['reviews'][0]['propositions'][0]
    assert proposition['source_quote_start'] == len(prefix)
    assert proposition['source_quote_end'] == len(prefix) + len(ev['source_excerpt'])
    ev['source_excerpt'] += '不存在的原文'
    with pytest.raises(ValueError, match='exact declared excerpt'):
        independent_packet(bundle)


def test_compact_review_is_expanded_to_auditable_full_claim_proposition():
    bundle = compiled()
    ev = bundle['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]
    decision = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': '原文完整支持主体和判断。'}]}
    review = compile_review(bundle, decision, {'session_id': 'reviewer', 'completed_at': 'time'}, 'hash')
    proposition = review['reviews'][0]['propositions'][0]
    assert proposition == {
        'text': ev['formal_claim'],
        'verdict': 'fully_supported',
        'rationale': '原文完整支持主体和判断。',
        'source_quote': ev['source_excerpt'],
        'source_quote_start': ev['source_excerpt_start'],
        'source_quote_end': ev['source_excerpt_end'],
    }


def test_model_narrative_cannot_invent_tool_execution():
    events = [{"message": {"content": [{"type": "text", "text": "WebSearch executed successfully"}]}},
              {"message": {"content": [{"type": "tool_use", "id": "c1", "name": "WebSearch", "input": {"query": "real"}}]}},
              {"message": {"content": [{"type": "tool_result", "tool_use_id": "c1", "content": "Found 0 results"}]}}]
    rows = observed_tools("\n".join(json.dumps(x) for x in events))
    assert len(rows) == 1 and rows[0]["input"]["query"] == "real"
    assert search_rows("## 1. [A](https://example.test/a)\nBody\n**URL:** url")[0]["snippet"] == "Body"


@pytest.mark.parametrize("url", ["https://ydata.woa.com/a", "https://sub.ydata.woa.com", "http://127.0.0.1", "file:///tmp/a", "https://user:pass@example.test"])
def test_reader_rejects_restricted_destinations(url):
    with pytest.raises(ValueError):
        check_public_url(url)


def test_semantic_cache_bound_to_prompt_and_result_hash(tmp_path, monkeypatch):
    calls = []
    def invoke(*args):
        calls.append(args)
        return '{"items":[]}', {"exit_code": 0, "session_id": "new"}
    monkeypatch.setattr("cwh_host_research.invoke", invoke)
    semantic_json({"a": 1}, "prompt", [], tmp_path, "test", 10)
    semantic_json({"a": 1}, "prompt", [], tmp_path, "test", 10)
    assert len(calls) == 1
    cache = tmp_path / "test.cache.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["result"] = {"ok": False}
    cache.write_text(json.dumps(data), encoding="utf-8")
    semantic_json({"a": 1}, "prompt", [], tmp_path, "test", 10)
    semantic_json({"a": 1}, "new prompt", [], tmp_path, "test", 10)
    assert len(calls) == 3
    semantic_json({"a": 1}, "new prompt", ["different-model"], tmp_path, "test", 10)
    assert len(calls) == 4


def test_stream_metrics_only_report_activity_counts():
    events = [{"type": "stream_event", "event": {"delta": {"type": "thinking_delta", "thinking": "internal text"}}, "__timestamp": "t1"},
              {"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "{}"}}, "__timestamp": "t2"},
              {"type": "result", "usage": {"output_tokens": 20}}, {"event": []}]
    metrics = stream_metrics("\n".join(json.dumps(x) for x in events))
    assert metrics["streamed_reasoning_characters"] == 13
    assert metrics["streamed_answer_characters"] == 2
    assert metrics["reported_usage"]["output_tokens"] == 20
    assert metrics['first_answer_at'] == metrics['last_answer_at'] == 't2'
    assert "internal text" not in json.dumps(metrics)


def test_terminal_transport_error_detects_rate_limit_without_copying_provider_message():
    log = json.dumps({
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "errors": "429 使用量已超出频率限制，将在 2026-09-15 00:12:59 UTC+8 重置 request-secret",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }, ensure_ascii=False)
    error = terminal_transport_error(log)
    assert error == {
        "category": "rate_limited",
        "exit_code": 29,
        "retry_after": "2026-09-15 00:12:59 UTC+8",
        "subtype": "error_during_execution",
    }
    assert "request-secret" not in json.dumps(error)


def test_terminal_transport_error_detects_transient_network_failure():
    log = json.dumps({
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "errors": ["502 网络连接失败：无法解析服务器地址（getaddrinfo ENOTFOUND api.example.test）"],
        "errors_info": [{"status": 502, "category": "network"}],
    }, ensure_ascii=False)
    error = terminal_transport_error(log)
    assert error == {
        "category": "network_unavailable",
        "exit_code": 28,
        "retry_after": "",
        "subtype": "error_during_execution",
    }
    assert "api.example.test" not in json.dumps(error)


def test_web_packet_uses_fetched_title_not_truncated_search_title():
    packet, _, observation, _ = fixture()
    url = "https://wrong.test/a"
    prepared = make_packet(packet["topic"], packet["period"], [], observation,
                           [{"url": url, "source_text": "完整正文", "page_title": "完整原始标题", "status": "completed"}])
    assert prepared["items"][0]["title"] == "完整原始标题"
    assert prepared["items"][0]["discovered_title"] == "搜索结果"


def test_public_page_snapshot_is_hash_checked_and_reused_for_repairs(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("run_cwh_compiled_worker.read_public_pages", lambda urls, timeout=8: calls.append((urls, timeout)) or [{"url": urls[0], "source_text": "原文"}])
    first = cached_public_pages(tmp_path, ["https://example.test/a"])
    second = cached_public_pages(tmp_path, ["https://example.test/a"])
    assert first == second and len(calls) == 1
    (tmp_path / "public_pages.json").write_text("[]", encoding="utf-8")
    cached_public_pages(tmp_path, ["https://example.test/a"])
    assert len(calls) == 2


@pytest.mark.parametrize("code", [23, 124])
def test_host_model_failures_preserve_nonretryable_transport_code(tmp_path, monkeypatch, code):
    monkeypatch.setattr("cwh_host_research.invoke", lambda *a: ("", {"exit_code": code, "log": "test.log"}))
    with pytest.raises(HostModelError) as error:
        semantic_json({}, "prompt", [], tmp_path, "test", 10)
    assert error.value.exit_code == code


def test_query_cache_rederives_results_and_checks_log_hash(tmp_path, monkeypatch):
    calls = []
    queries = ["2026-05-15 国务院常务会议 测试议题 专家 解读", "2026-05-15 测试议题 国常会 建议 评论 分析"]
    def invoke(*args):
        calls.append(args)
        events = []
        for n, query in enumerate(queries):
            events.extend([{"message": {"content": [{"type": "tool_use", "id": str(n), "name": "WebSearch", "input": {"query": query}}]}},
                           {"message": {"content": [{"type": "tool_result", "tool_use_id": str(n), "content": "Found 0 results"}]}}])
        log = "\n".join(json.dumps(row) for row in events)
        path = tmp_path / f"test-{len(calls)}.jsonl"
        path.write_text(log, encoding="utf-8")
        return log, {"log": str(path), "started_at": "start", "completed_at": "end", "exit_code": 0}
    monkeypatch.setattr("cwh_host_research.invoke", invoke)
    plan, period = {"topic": "测试议题", "stable_source_tasks": []}, {"start": "2026-05-15"}
    first = collect_topic(plan, period, [], tmp_path, 10)
    first["queries"][0]["result_urls"] = ["https://invented.test"]
    (tmp_path / "research_observations.json").write_text(json.dumps(first), encoding="utf-8")
    second = collect_topic(plan, period, [], tmp_path, 10)
    assert second["queries"][0]["result_urls"] == [] and len(calls) == 1
    Path(first["host_run"]["log"]).write_text("tampered", encoding="utf-8")
    collect_topic(plan, period, [], tmp_path, 10)
    assert len(calls) == 2
def test_web_timestamp_format_is_canonicalized_without_guessing_or_touching_raw_dates():
    from cwh_semantic_compiler import normalize_web_publication_dates, web_metadata_errors
    packet = {"period": {"start": "2026-07-31", "end": "2026-08-03"},
        "items": [{"id": "w1", "origin": "web", "content": "新华社 2026-07-31 21:56"},
                  {"id": "r1", "origin": "raw_monitoring"}]}
    decision = {"items": [{"id": "w1", "decision": "eligible", "source": "新华社",
        "published_at": "2026-07-31 21:56", "date_quote": "2026-07-31 21:56"},
        {"id": "r1", "published_at": "2026-07-31 21:56"}]}
    result = normalize_web_publication_dates(packet, decision)
    assert result["items"][0]["published_at"] == "2026-07-31"
    assert result["items"][0]["author_published_at"] == "2026-07-31 21:56"
    assert result["items"][1]["published_at"] == "2026-07-31 21:56"
    assert not web_metadata_errors(packet, result)
    assert decision["items"][0]["published_at"] == "2026-07-31 21:56"
    result["items"][0]["date_quote"] = "2026-08-01 21:56"
    assert web_metadata_errors(packet, result)
