"""Pool coverage is distinct from semantic eligibility and final voice count."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_research_plan import load_source_registry, research_queries, stable_source_tasks
from cwh_host_research import topic_search_tasks
from run_cwh_compiled_worker import domestic_reading_limits, balanced_fetch_urls
from prepare_cwh_corpus_index import prepare_corpus_index
from cwh_model_contract import execution_profile
from cwh_semantic_compiler import web_metadata_errors


def test_real_registry_plan_searches_academia_and_public_supplement_within_ten_queries():
    topic, date = '公共服务布局', '2026-05-15'
    plan = {'topic': topic, 'queries': research_queries(topic, date), 'query_execution_limit': 10,
            'stable_source_tasks': stable_source_tasks(topic, date, load_source_registry()['sources'],
                                                       profile_name='bounded_60m')}
    tasks = topic_search_tasks(plan, {'start': date})
    assert len(tasks) == 10
    assert {'academic_think_tank', 'public_platform_supplement', 'wechat_public',
            'toutiao_articles', 'baijiahao', 'lane_industry_expert'} <= {row['source_id'] for row in tasks}
    assert len({row['query'] for row in tasks}) == len(tasks)
    plan['query_execution_limit'] = 8
    assert len(topic_search_tasks(plan, {'start': date})) == 8


def test_profile_reading_pool_grows_without_changing_formal_cap_or_deadline():
    for name, expected in [('bounded_40m', (16, 8)), ('bounded_60m', (20, 10))]:
        _, profile = execution_profile(name)
        assert domestic_reading_limits({'execution_budget': profile['research']}) == expected
        assert profile['research']['max_formal_voices_per_topic'] == 12
    assert domestic_reading_limits({}) == (12, 4)
    assert domestic_reading_limits({'execution_budget': {'initial_public_page_fetches_per_topic': 10,
                                                       'max_full_page_fetches_per_topic': 3}}) == (12, 3)


def test_larger_reading_index_preserves_all_ids_and_full_original_articles(tmp_path):
    rows = [{'record_id': f'r{i}', 'source': f'来源{i}', 'title': f'议题分析{i}', 'topic_hits': [1],
             'content': f'这是第{i}篇完整原文，不允许截掉后半篇。' * 20} for i in range(45)]
    corpus = {'candidates': rows}
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(corpus, ensure_ascii=False), encoding='utf-8')
    original = source.read_bytes()
    index = json.loads(prepare_corpus_index(source, corpus, ['议题']).read_text('utf-8'))
    assert len(index['topics'][0]['shortlist']) == 40
    assert set(index['topics'][0]['record_ids']) == {r['record_id'] for r in rows}
    for row in index['topics'][0]['shortlist']:
        actual = json.loads(Path(row['full_text_path']).read_text('utf-8'))
        assert actual == next(r for r in rows if r['record_id'] == row['record_id'])
    assert source.read_bytes() == original


def test_ten_page_slots_cover_ten_observed_queries_before_second_results():
    obs = {'queries': [{'results': [{'url': f'a{i}'}, {'url': f'b{i}'}]} for i in range(10)]}
    assert balanced_fetch_urls(obs, 10) == [f'a{i}' for i in range(10)]


def test_month_day_header_cannot_borrow_year_from_body_or_url():
    packet = {'period': {'start': '2026-07-31', 'end': '2026-08-03'},
              'items': [{'id': 'w1', 'origin': 'web', 'content': '某报07-31 19:16\n2026年项目开始建设。',
                         'url': 'https://example.test/2026/07/31/a'}]}
    decision = {'items': [{'id': 'w1', 'decision': 'eligible', 'source': '某报',
                          'published_at': '2026-07-31', 'date_quote': '某报07-31 19:16'}]}
    assert len(web_metadata_errors(packet, decision)) == 1
    decision['items'][0].update(decision='excluded', claims=[])
    assert not web_metadata_errors(packet, decision)
