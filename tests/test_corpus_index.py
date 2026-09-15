import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cwh_corpus_index import prepare_corpus_index, complete_corpus_deferrals
from complete_cwh_evidence_structure import complete_analysis_structure
from run_cwh_resumable_pipeline import validate_analysis_bundle


def corpus():
    return {"candidates": [{"record_id": f"r{i}", "title": f"议题分析{i}", "source": f"来源{i}",
                             "url": f"https://example.test/{i}", "topic_hits": [1], "content": f"完整原文{i}"} for i in range(15)]}


def test_index_retains_all_raw_ids_and_separate_reading_order(tmp_path):
    data = corpus()
    source = tmp_path / "public_article_evidence.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    index = json.loads(prepare_corpus_index(source, data, ["议题"]).read_text(encoding="utf-8"))
    assert index["candidate_count"] == 15
    assert set(index["topics"][0]["record_ids"]) == {x["record_id"] for x in data["candidates"]}
    assert all(Path(row["full_text_path"]).exists() for row in index["topics"][0]["shortlist"])


def test_reading_order_delays_duplicate_fulltexts_without_excluding_records(tmp_path):
    data = corpus()
    data['candidates'][0]['content'] = '甲地区公共服务需要结合人口分布和实际需求进行统筹配置。' * 6
    data['candidates'][1]['content'] = data['candidates'][0]['content']
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(data), encoding='utf-8')
    index = json.loads(prepare_corpus_index(source, data, ['议题']).read_text('utf-8'))
    order = [r['record_id'] for r in index['topics'][0]['shortlist']]
    assert order.index('r1') > order.index('r2')
    assert set(order) == {r['record_id'] for r in data['candidates']}
    assert json.loads(source.read_text('utf-8')) == data


def test_reading_prioritizes_analysis_titles_and_delays_identical_fact_titles(tmp_path):
    data = corpus()
    data['candidates'][0]['title'] = '议题发布要点'
    data['candidates'][1]['title'] = '议题发布要点'
    data['candidates'][2]['title'] = '专家解读议题另一种表达'
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(data), encoding='utf-8')
    index = json.loads(prepare_corpus_index(source, data, ['议题']).read_text('utf-8'))
    order = [r['record_id'] for r in index['topics'][0]['shortlist']]
    assert order[0] == 'r2'
    assert order.index('r1') > order.index('r14')
    assert len(index['topics'][0]['record_ids']) == len(data['candidates'])


def test_bounded_deferral_never_calls_unread_records_reviewed(tmp_path):
    raw = corpus()
    source = tmp_path / "public_article_evidence.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    prepare_corpus_index(source, raw, ["议题"])
    row = {"topic": "议题", "reviewed_record_ids": [f"r{i}" for i in range(12)],
           "retained_record_ids": [], "excluded": [{"record_id": f"r{i}", "reason": "逐篇审核后排除"} for i in range(12)]}
    draft = {"research_audit": {"domestic_media_research": {"public_article_corpus_review": {"topic_reviews": [row]}}}}
    result = complete_corpus_deferrals(draft, raw, ["议题"])
    completed = result["research_audit"]["domestic_media_research"]["public_article_corpus_review"]["topic_reviews"][0]
    assert completed["reviewed_record_ids"] == row["reviewed_record_ids"]
    assert completed["deferred_record_ids"] == ["r12", "r13", "r14"]
    target = tmp_path / "draft.json"
    target.write_text(json.dumps(result), encoding="utf-8")
    strict = validate_analysis_bundle(target, ["议题"], require_semantic_review=False)
    bounded = validate_analysis_bundle(target, ["议题"], require_semantic_review=False, allow_deferred_corpus=True)
    assert any("未逐条审核" in x for x in strict)
    assert not any("未逐条审核" in x for x in bounded)
    assert bounded  # Deferral does not waive all the other evidence gates.
    source.write_text(json.dumps({"candidates": raw["candidates"][:14]}), encoding="utf-8")
    assert any("未逐条审核" in x for x in validate_analysis_bundle(target, ["议题"], require_semantic_review=False, allow_deferred_corpus=True))


def test_professional_body_hint_beats_generic_analysis_title_without_excluding_rows(tmp_path):
    data = corpus()
    data['candidates'][0].update(title='某政策最新部署', content='某研究院副院长张明表示，制度覆盖须保留实际就业群体的适用条件。')
    data['candidates'][1].update(title='专家解读另一新闻', content='另一个事件的简短报道。')
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(data), encoding='utf-8')
    index = json.loads(prepare_corpus_index(source, data, ['议题'], {'议题': ['制度覆盖']}).read_text('utf-8'))
    assert index['topics'][0]['shortlist'][0]['record_id'] == 'r0'
    assert len(index['topics'][0]['record_ids']) == len(data['candidates'])
    assert json.loads(source.read_text('utf-8')) == data


def test_professional_hint_without_current_policy_context_is_not_priority():
    from prepare_cwh_corpus_index import professional_quote_hint
    assert professional_quote_hint('某研究院副院长张明认为应改善另一政策。', ['制度覆盖']) == 0


def test_possible_policy_reasoning_is_read_before_title_only_facts_without_certification(tmp_path):
    data = {'candidates': [
        {'record_id': 'fact', 'title': '公共服务布局最新部署', 'source': '甲', 'topic_hits': [1],
         'content': '会议听取公共服务布局有关情况汇报。'},
        {'record_id': 'possible', 'title': '公共服务布局：四项政策信号观察', 'source': '乙', 'topic_hits': [1],
         'content': '公共服务布局需要配置相应资源。这将影响区域服务差异，实际效果取决于资金到位。'},
        {'record_id': 'named', 'title': '本期政策采访', 'source': '丙', 'topic_hits': [1],
         'content': '教授张明认为，公共服务布局应匹配人口需求。'}]}
    frozen = json.loads(json.dumps(data))
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(data), encoding='utf-8')
    index = json.loads(prepare_corpus_index(source, data, ['公共服务布局']).read_text('utf-8'))
    order = [row['record_id'] for row in index['topics'][0]['shortlist']]
    assert order == ['named', 'possible', 'fact']
    assert len(index['topics'][0]['record_ids']) == 3
    assert data == frozen and json.loads(source.read_text('utf-8')) == frozen
    assert index['topics'][0]['shortlist'][1]['reasoning_reading_hint_count'] == 2
    assert all('decision' not in row for row in index['topics'][0]['shortlist'])


def test_reasoning_reading_hint_does_not_use_distant_unrelated_analysis():
    from prepare_cwh_corpus_index import reasoning_reading_hint
    assert reasoning_reading_hint('公共服务布局最新情况。' + '无关信息。' * 100 + '预计另一产业需求增长。', ['公共服务布局']) == 0
    assert reasoning_reading_hint('公共服务布局实际效果取决于投入。' * 10, ['公共服务布局']) == 3


def test_raw_source_hydration_only_fills_missing_exact_fields():
    candidate = {"raw_evidence_record_id": "r0", "speaker_name": "发言者"}
    draft = {"research_audit": {"domestic_media_research": {"candidate_pool_by_topic": [{"topic": "议题", "candidates": [candidate]}]}}}
    result = complete_analysis_structure(draft, corpus())
    enriched = result["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][0]
    assert enriched["source_snapshot"]["source_text"] == "完整原文0"
    assert enriched["source_snapshot"]["source_text_sha256"]
    assert "url" not in candidate
    enriched["url"] = "https://incorrect.test/"
    second = complete_analysis_structure(result, corpus())
    assert second["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][0]["url"] == "https://incorrect.test/"
