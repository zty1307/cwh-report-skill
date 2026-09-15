import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cwh_fast_comment_collection import apply_review_cap, query_variants, relevant_parent_title, topic_fragments


def test_topic_query_variants_are_current_topic_driven():
    queries = query_variants("绿色低碳转型")
    assert queries[0] == "国务院常务会议部署绿色低碳转型工作"
    assert "国务院常务会议研究绿色低碳转型" in queries
    assert all("2026" not in query for query in queries)


def test_declared_aliases_are_searched_inside_default_five_query_cutoff():
    queries = query_variants('某公共服务管理条例修订', ['公共服务', '服务条例', '公共服务', ''])[:5]
    assert queries[0] == '国务院常务会议部署某公共服务管理条例修订工作'
    assert '国务院常务会议公共服务' in queries and '国务院常务会议服务条例' in queries
    assert len(queries) == len(set(queries))


def test_conjoined_topic_exposes_conservative_suffix_alias():
    assert topic_fragments("就业与社会保障") == ["就业与社会保障", "社会保障"]
    assert "国务院常务会议部署加快建设社会保障" in query_variants("就业与社会保障")


def test_parent_title_requires_meeting_and_topic_evidence():
    assert relevant_parent_title("国务院常务会议研究绿色低碳转型有关工作", "绿色低碳转型")
    assert not relevant_parent_title("某公司发布绿色低碳转型年度报告", "绿色低碳转型")
    assert not relevant_parent_title("国务院常务会议研究其他事项", "绿色低碳转型")


def test_shared_action_suffix_does_not_hide_current_topic():
    assert relevant_parent_title('国务院常务会议部署绿色交通网、综合物流网建设', '绿色交通网建设')
    assert relevant_parent_title('国常会研究生态环境条例', '生态环境条例修改')
    assert not relevant_parent_title('某企业介绍绿色交通网建设', '绿色交通网建设')


def test_explicit_current_aliases_are_used_without_historical_topic_dictionary():
    assert relevant_parent_title('国常会核准甲地、乙地四个清洁能源项目', '核准四个清洁能源项目', ['清洁能源项目'])
    assert not relevant_parent_title('国常会研究其他事项', '核准四个清洁能源项目', ['清洁能源项目'])


def test_metadata_aliases_come_only_from_current_owned_pipeline_input(tmp_path):
    import json
    from cwh_fast_comment_collection import metadata_topic_aliases
    tasks = tmp_path / 'tasks'
    tasks.mkdir()
    metadata = tmp_path / 'metadata.json'
    metadata.write_text(json.dumps({'topic_titles': ['动态议题'], 'topic_aliases': [['当期别名']]}), encoding='utf-8')
    (tmp_path / 'pipeline_state.json').write_text(json.dumps({'input_contract': {'metadata': str(metadata)}}), encoding='utf-8')
    aliases, provenance = metadata_topic_aliases(tasks / 'comments.json')
    assert aliases == {'动态议题': ['当期别名']}
    assert provenance['metadata_file'] == str(metadata.resolve())
    assert provenance['metadata_sha256']


def test_multi_topic_parent_cannot_be_frozen_to_first_matching_topic():
    import pytest
    from cwh_comment_semantics import collection_topic_routes
    with pytest.raises(ValueError, match='semantic topic routing'):
        collection_topic_routes({'rows': [], 'posts': []}, ['动态甲', '动态乙'],
            {'multi_topic_parents': [{'parent_post_id': 'p1', 'topic_candidates': ['动态甲', '动态乙']}]})


def test_review_cap_balances_topics_and_retains_omitted_rows():
    posts = [
        {"id": "p1", "url": "https://example.test/1"},
        {"id": "p2", "url": "https://example.test/2"},
    ]
    rows = []
    for index in range(20):
        post = "p1" if index < 15 else "p2"
        rows.append({"sample_id": f"s{index}", "comment_id": str(index),
                     "parent_post_id": post, "like_count": index, "text": "具体意见" * 5})
    capture, omitted = apply_review_cap(
        {"rows": rows, "posts": posts, "excluded": []},
        {"https://example.test/1": "议题一", "https://example.test/2": "议题二"},
        max_total=8,
        max_per_topic=5,
    )
    assert len(capture["rows"]) == 8 and omitted == 12
    assert sum(row["parent_post_id"] == "p1" for row in capture["rows"]) == 4
    assert sum(row["parent_post_id"] == "p2" for row in capture["rows"]) == 4
    assert all(row["exclusion_reason"] == "bounded_semantic_review_sample_cap" for row in capture["excluded"])
