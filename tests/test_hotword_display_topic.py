import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_hotword_pipeline import primary_reviewed_topic


def test_unique_literal_topic_is_preferred_over_smallest_shared_article_index():
    titles = ['区域基础设施建设', '修改有关行政法规', '部署智慧交通建设']
    assert primary_reviewed_topic('智慧交通', [1, 3], titles) == (
        3, 'unique_literal_term_in_reviewed_topic_title')
    assert primary_reviewed_topic('智慧交通', [2, 3], titles)[0] == 3


def test_does_not_expand_model_approved_topics_or_guess_ambiguous_ownership():
    titles = ['区域基础设施建设', '完善公共服务', '部署智慧交通建设']
    assert primary_reviewed_topic('智慧交通', [1, 2], titles)[0] == 1
    assert primary_reviewed_topic('建设', [1, 3], titles)[0] == 1
    assert primary_reviewed_topic('服务保障', [2, 3], titles)[0] == 2


def test_mapping_is_dynamic_and_keeps_reviewed_list_unchanged():
    hits = [1, 2]
    assert primary_reviewed_topic('职业教育', hits, ['重点工作部署', '加快职业教育发展'])[0] == 2
    assert hits == [1, 2]
