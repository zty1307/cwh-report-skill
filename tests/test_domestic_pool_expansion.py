"""Pool coverage is distinct from semantic eligibility and final voice count."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_research_plan import load_source_registry, research_queries, stable_source_tasks, policy_search_subject
from cwh_host_research import topic_search_tasks


def test_academic_discovery_uses_alternative_source_types_not_all_types_at_once():
    query = research_queries('公共服务政策', '2026-07-31')['academic_and_think_tank_viewpoints'][1]
    assert '(研究院 OR 智库 OR 学者 OR 协会 OR 学会)' in query
    assert '(解读 OR 分析 OR 建议 OR 评论)' in query
    assert '公共服务政策' in query and '2026-07-31' in query


def test_discovery_strips_agenda_wrappers_without_changing_policy_names_or_ids():
    cases = {
        '听取现代流通体系建设进展情况汇报': '现代流通体系建设',
        '研究自然资源保护利用有关工作': '自然资源保护利用',
        '审议通过《甲条例》和《乙条例》': '《甲条例》和《乙条例》',
        '审议《全民健身计划（2026—2030年）》': '《全民健身计划（2026—2030年）》',
        '听取新型电网、物流网建设情况汇报': '新型电网、物流网建设',
        '公共服务改革': '公共服务改革',
        '研究有关工作': '研究有关工作',
    }
    for topic, subject in cases.items():
        assert policy_search_subject(topic) == subject
        queries = research_queries(topic, '2026-07-10')
        assert topic in queries['official_confirmation'][0]
        lanes = stable_source_tasks(topic, '2026-07-10', load_source_registry()['sources'],
                                    profile_name='bounded_60m')
        plan = {'topic': topic, 'queries': queries, 'query_execution_limit': 10,
                'stable_source_tasks': lanes}
        tasks = topic_search_tasks(plan, {'start': '2026-07-10'})
        assert plan['topic'] == topic
        assert len(tasks) == 10
        assert topic in next(t['query'] for t in tasks if t['source_id'] == 'lane_authoritative')
        assert all(subject in t['query'] for t in tasks)
        assert '(解读 OR 评论 OR 政策影响 OR 建议)' in next(t['query'] for t in tasks if t['source_id'] == 'wechat_public')


def test_cross_sector_professional_sources_reach_real_bounded_lane_without_more_queries():
    sources = load_source_registry()['sources']
    lanes = stable_source_tasks('公共服务政策', '2026-07-31', sources, profile_name='bounded_60m')
    industry = next(row for row in lanes if row['source_id'] == 'lane_industry_expert')
    ids = {'medical_society', 'law_society', 'electricity_council', 'logistics_federation'}
    assert ids <= set(industry['source_ids'])
    assert all('site:' + domain in industry['query'] for domain in
               ('cma.org.cn', 'chinalaw.org.cn', 'cec.org.cn', 'chinawuliu.com.cn'))
    assert '公共服务政策' in industry['query']
    assert len(lanes) == 6
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
    by_source = {row['source_id']: row for row in tasks}
    assert '国务院常务会议' in by_source['lane_authoritative']['query']
    for source_id in ['lane_mainstream', 'lane_industry_expert', 'wechat_public', 'toutiao_articles', 'baijiahao']:
        query = by_source[source_id]['query']
        assert date in query and topic in query and 'site:' in query
        assert '国务院常务会议' not in query
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


def test_mirror_headlines_are_delayed_not_excluded_from_discovery():
    import copy
    obs = {'queries': [
        {'results': [{'url': 'https://a.test/story', 'title': '政策专家解读_甲媒体'},
                     {'url': 'https://a.test/different', 'title': '政策落实的条件'}]},
        {'results': [{'url': 'https://b.test/mirror', 'title': '政策专家解读_乙媒体'},
                     {'url': 'https://b.test/interview', 'title': '产业协会谈政策成本'}]},
    ]}
    original = copy.deepcopy(obs)
    assert balanced_fetch_urls(obs, 2) == ['https://a.test/story', 'https://b.test/interview']
    assert balanced_fetch_urls(obs, 4) == ['https://a.test/story', 'https://b.test/interview',
                                         'https://a.test/different', 'https://b.test/mirror']
    assert obs == original


def test_page_reading_prefers_actual_site_hits_and_policy_interpretation_without_editing_results():
    import copy
    obs = {'queries': [
        {'query': 'site:media.test 健康优先发展战略', 'results': [
            {'url': 'https://gov.test/a', 'title': '健康优先发展战略解读'},
            {'url': 'https://media.test/a', 'title': '健康优先发展战略实施安排'}]},
        {'query': '健康优先发展战略 智库 学者 解读', 'results': [
            {'url': 'https://school.test/summit', 'title': '共探健康优先全民数智峰会'},
            {'url': 'https://school.test/gov', 'title': '14位学者解读政府工作报告'},
            {'url': 'https://school.test/expert', 'title': '教授深度解读健康中国优先发展战略'}]}]}
    original = copy.deepcopy(obs)
    assert balanced_fetch_urls(obs, 2, topic='健康优先发展战略') == [
        'https://media.test/a', 'https://school.test/expert']
    assert obs == original
    assert set(balanced_fetch_urls(obs, 10, topic='健康优先发展战略')) == {
        item['url'] for row in obs['queries'] for item in row['results']}


def test_specific_policy_title_is_read_before_generic_weekend_market_analysis(tmp_path):
    corpus = {'candidates': [
        {'record_id': 'market', 'source': '甲账号', 'title': '周末消息解读，下周交易策略分享',
         'topic_hits': [1], 'content': '新闻之一提到公共服务布局；正文其余部分讨论其他市场信息。'},
        {'record_id': 'policy', 'source': '乙账号', 'title': '公共服务布局的实施安排',
         'topic_hits': [1], 'content': '公共服务布局的具体原文，阅读优先不代表独立解读合格。'}]}
    source = tmp_path / 'public_article_evidence.json'
    source.write_text(json.dumps(corpus, ensure_ascii=False), encoding='utf-8')
    index = json.loads(prepare_corpus_index(source, corpus, ['公共服务布局']).read_text('utf-8'))
    assert [row['record_id'] for row in index['topics'][0]['shortlist']] == ['policy', 'market']
    assert set(index['topics'][0]['record_ids']) == {'policy', 'market'}
    assert json.loads(source.read_text('utf-8')) == corpus


def test_month_day_header_cannot_borrow_year_from_body_or_url():
    packet = {'period': {'start': '2026-07-31', 'end': '2026-08-03'},
              'items': [{'id': 'w1', 'origin': 'web', 'content': '某报07-31 19:16\n2026年项目开始建设。',
                         'url': 'https://example.test/2026/07/31/a'}]}
    decision = {'items': [{'id': 'w1', 'decision': 'eligible', 'source': '某报',
                          'published_at': '2026-07-31', 'date_quote': '某报07-31 19:16'}]}
    assert len(web_metadata_errors(packet, decision)) == 1
    decision['items'][0].update(decision='excluded', claims=[])
    assert not web_metadata_errors(packet, decision)
