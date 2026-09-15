import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_comment_semantics import (compile_results, review_packet, label_decisions, quote_packet,
                                   merge_quote_decisions, compact_review_packet,
                                   expand_compact_comment_result, capture_has_replacement_characters,
                                   repair_corrupt_toutiao_capture)
from run_cwh_inline_review import response_object


def test_lossy_comment_capture_is_detected_before_model_review():
    assert capture_has_replacement_characters({'rows': [{'text': '城\ufffd更新'}], 'posts': []})
    assert not capture_has_replacement_characters({'rows': [{'text': '城市更新'}], 'posts': []})


def test_lossy_capture_repair_refuses_unexpected_endpoint(tmp_path):
    raw = tmp_path / 'raw.json'
    raw.write_text('{"url":"https://example.com/comments","status":200,"body":"{}"}', encoding='utf-8')
    capture = {
        'rows': [{'comment_id': '1'}],
        'posts': [{'id': 'toutiao-1', 'url': 'https://www.toutiao.com/article/1/', 'raw_file': str(raw)}],
        'raw_captures': [{'raw_file': str(raw)}],
        'monitoring_period': {'start': '2026-01-01', 'end': '2026-01-02'},
    }
    with pytest.raises(ValueError, match='unexpected endpoint'):
        repair_corrupt_toutiao_capture(capture, tmp_path / 'out')


def test_comment_output_parser_and_exact_id_coverage():
    assert response_object('{"rows":[]}') == {'rows': []}
    assert response_object('{"repairs":[]}') == {'repairs': []}
    assert response_object('{"selected":[]}') == {'selected': []}
    capture = {'rows': [{'sample_id': 'real-id'}]}
    result = {'rows': [{'id': 1, 'topic': 1, 'label': 'positive', 'formal': True, 'reason': '支持扩大公共服务覆盖', 'heading': '建议扩大覆盖'}],
              'topic_headings': {'1': '建议扩大覆盖'}}
    reviewed = compile_results(capture, ['公共服务'], result, {'session_id': 'actual-run'})
    assert reviewed[0]['sample_id'] == 'real-id' and reviewed[0]['reviewer_run_id'] == 'actual-run'
    assert reviewed[0]['topic'] == '公共服务'
    result['rows'][0]['id'] = 2
    with pytest.raises(ValueError, match='every supplied ID'):
        compile_results(capture, ['公共服务'], result, {'session_id': 'actual-run'})


@pytest.mark.parametrize('changes', [{'topic': 0}, {'formal': 'true'}, {'label': 'unreviewed'}, {'reason': ''}])
def test_invalid_results_cannot_create_handoff(changes):
    row = {'id': 1, 'topic': 1, 'label': 'neutral', 'formal': False, 'reason': '具体问题询问', 'heading': ''}
    row.update(changes)
    with pytest.raises(ValueError):
        compile_results({'rows': [{'sample_id': 'real'}]}, ['topic'], {'rows': [row]}, {'session_id': 'real-run'})


def test_label_validation_does_not_certify_misnumbered_shared_formal_heading():
    from cwh_comment_semantics import apply_quote_review
    capture = {'rows': [{'sample_id': 'a'}, {'sample_id': 'b'}]}
    result = {'topic_headings': {'1': '作者把分组序号当议题编号'}, 'rows': [
        {'id': 1, 'topic': 6, 'label': 'positive', 'formal': True,
         'reason': '具体诉求', 'heading': '建议增加服务设施'},
        {'id': 2, 'topic': 6, 'label': 'neutral', 'formal': True,
         'reason': '具体疑问', 'heading': '询问设施开放时间'}]}
    original = copy.deepcopy(result)
    topics = ['议题甲', '议题乙', '议题丙', '议题丁', '议题戊', '公共服务']
    labels = compile_results(capture, topics, result, {'session_id': 'author'}, classification_only=True)
    assert [row['label'] for row in labels] == ['positive', 'neutral']
    assert all(row['in_sentiment_denominator'] and not row['ai_formal_include'] for row in labels)
    with pytest.raises(ValueError, match='shared topic heading'):
        compile_results(capture, topics, result, {'session_id': 'author'})
    # A fixture verifies host mechanics only, not native semantic acceptance.
    reviewed = apply_quote_review(result, {'reviews': [
        {'id': 1, 'verdict': 'keep', 'reason': '具体诉求'},
        {'id': 2, 'verdict': 'reject', 'reason': '标题不忠实'}],
        'topic_headings': {'6': '建议增加服务设施'}})
    final = compile_results(capture, topics, reviewed, {'session_id': 'author'})
    assert sum(row['ai_formal_include'] for row in final) == 1
    assert [row['label'] for row in final] == [row['label'] for row in labels]
    assert result == original


@pytest.mark.parametrize('changes', [{'topic': 0}, {'formal': 'true'}, {'label': 'unreviewed'},
                                     {'reason': ''}, {'label': 'exclude', 'formal': True}])
def test_classification_precheck_keeps_original_type_and_disposition_gates(changes):
    row = {'id': 1, 'topic': 1, 'label': 'neutral', 'formal': False, 'reason': '具体疑问'}
    row.update(changes)
    with pytest.raises(ValueError):
        compile_results({'rows': [{'sample_id': 'a'}]}, ['topic'], {'rows': [row]},
                        {'session_id': 'author'}, classification_only=True)


def test_parent_title_is_not_misrepresented_as_full_body():
    capture = {'rows': [{'parent_post_id': 'p1', 'text': '具体意见'}], 'posts': [
        {'id': 'p1', 'text': '原帖标题', 'source': '媒体', 'published_at': '', 'context_kind': 'api_parent_title_only'}]}
    assert review_packet(capture, ['topic'])['posts'][0]['context_kind'] == 'api_parent_title_only'


def test_quote_candidate_limits_match_renderer_without_changing_original_comments():
    from cwh_comment_semantics import quote_constraints, QUOTE_PROMPT
    from formalize_cwh_report import comment_is_report_quote_suitable
    long_text = '希望明确政策适用条件' * 25
    assert quote_constraints(long_text)['formal_quote_allowed'] is False
    inquiry = '这项核准决定何时可以开工，是否还需办理其他手续？'
    assert quote_constraints(inquiry)['formal_quote_allowed'] == comment_is_report_quote_suitable(inquiry)
    assert '不要只因态度不明而忽略' in QUOTE_PROMPT
    assert long_text == '希望明确政策适用条件' * 25


def test_concrete_inquiry_heading_is_preserved_as_inquiry_not_added_opposition():
    from formalize_cwh_report import comment_stance_heading
    assert comment_stance_heading('询问核准后的项目能否直接开工') == '询问核准后的项目能否直接开工'
    assert comment_stance_heading('希望明确实施手续及适用范围') == '希望明确实施手续及适用范围'


def test_label_checkpoint_is_not_a_formal_quote_decision():
    capture = {'rows': [{'sample_id': 'a'}, {'sample_id': 'b'}]}
    result = {'rows': [{'id': 1, 'topic': 1, 'label': 'neutral', 'reason': 'unit opinion'},
                       {'id': 2, 'topic': 0, 'label': 'exclude', 'reason': 'unit unrelated'}]}
    labels = label_decisions(capture, ['topic'], result, {'session_id': 'label-run'})
    assert all(r['formal'] is False for r in labels['rows'])
    chosen = {'topic_headings': {'1': '具体政策诉求'}, 'selected': [{'id': 1, 'heading': '具体政策诉求', 'reason': 'unit selection'}]}
    combined = merge_quote_decisions(labels, chosen)
    assert combined['rows'][0]['label'] == 'neutral'
    assert combined['rows'][0]['reason'] == 'unit opinion'
    assert combined['rows'][0]['formal_reason'] == 'unit selection'
    assert labels['rows'][0]['formal'] is False
    assert combined['rows'][1]['formal'] is False
    chosen['selected'][0]['id'] = 2
    with pytest.raises(ValueError, match='included comment IDs'):
        merge_quote_decisions(labels, chosen)


def test_second_comment_phase_cannot_relabel_or_invent_ids():
    labels = {'rows': [{'id': 1, 'topic': 1, 'label': 'positive', 'reason': 'unit', 'formal': False}]}
    for choice in [{'id': 1, 'topic': 2, 'heading': 'title', 'reason': 'unit'},
                   {'id': 2, 'heading': 'title', 'reason': 'unit'},
                   {'id': True, 'heading': 'title', 'reason': 'unit'}]:
        with pytest.raises(ValueError):
            merge_quote_decisions(labels, {'selected': [choice]})
    packet = {'rows': [{'id': 1, 'post_id': 'p1', 'text': 'text'}, {'id': 2, 'post_id': 'p2', 'text': 'other'}],
              'posts': [{'id': 'p1'}, {'id': 'p2'}]}
    prepared = quote_packet(packet, labels)
    assert [r['id'] for r in prepared['rows']] == [1]
    assert prepared['posts'] == [{'id': 'p1'}]


def test_compact_packet_freezes_topic_from_collection_audit():
    capture = {'posts': [{'id': 'p1', 'url': 'https://post/1', 'text': '父帖标题',
                          'context_kind': 'api_parent_title_only'}],
               'rows': [{'parent_post_id': 'p1', 'text': '希望政策落实', 'like_count': 9}]}
    audit = {'coverage_by_topic': [{'topic': '公共服务', 'checks': [{
        'source_id': 'toutiao_public_comments', 'queries_or_seed_urls': ['https://post/1']}]}]}
    packet = compact_review_packet(capture, ['公共服务'], audit)
    assert packet['rows'] == [{'id': 1, 'topic': 1, 'text': '希望政策落实', 'parent_title': '父帖标题',
                               'parent_context_kind': 'api_parent_title_only', 'like_count': 9,
                               'formal_quote_allowed': True, 'formal_quote_chars': 6}]


def test_unused_cross_topic_seed_does_not_block_unambiguous_capture():
    capture = {'posts': [{'id': 'p1', 'url': 'https://post/1', 'text': '专题帖'}],
               'rows': [{'parent_post_id': 'p1', 'text': '具体意见'}]}
    audit = {'coverage_by_topic': [
        {'topic': '议题甲', 'checks': [{'source_id': 'toutiao_public_comments',
                                      'queries_or_seed_urls': ['https://post/1', 'https://shared']}]},
        {'topic': '议题乙', 'checks': [{'source_id': 'weibo_comments',
                                      'queries_or_seed_urls': ['https://shared']}]}]}
    packet = compact_review_packet(capture, ['议题甲', '议题乙'], audit)
    assert packet['rows'][0]['topic'] == 1


def test_compact_result_expands_fixed_codes_and_formal_choice():
    packet = {'topics': {'1': '公共服务'}, 'rows': [
        {'id': 1, 'topic': 1}, {'id': 2, 'topic': 1}, {'id': 3, 'topic': 1}]}
    compact = {'labels': [[1, 'support'], [2, 'oppose'], [3, 'trading']],
               'selected': [[2, '担忧配套措施不足']],
               'topic_headings': {'1': '公众关注政策配套与落实'}}
    expanded = expand_compact_comment_result(packet, compact)
    assert [row['label'] for row in expanded['rows']] == ['positive', 'negative', 'exclude']
    assert expanded['rows'][1]['formal'] is True
    assert expanded['rows'][2]['reason'] == '仅谈个股或交易而非政策'


@pytest.mark.parametrize('compact', [
    {'labels': [[1, 'support'], [1, 'neutral']], 'selected': [], 'topic_headings': {}},
    {'labels': [[1, 'unknown'], [2, 'neutral']], 'selected': [], 'topic_headings': {}},
    {'labels': [[1, 'support'], [2, 'unrelated']], 'selected': [[2, '错误选择']], 'topic_headings': {'1': '标题'}},
    {'labels': [[1, 'support'], [2, 'neutral']], 'selected': [[1, '判断']], 'topic_headings': {}},
])
def test_compact_result_rejects_invalid_protocol(compact):
    packet = {'topics': {'1': '公共服务'}, 'rows': [{'id': 1, 'topic': 1}, {'id': 2, 'topic': 1}]}
    with pytest.raises(ValueError):
        expand_compact_comment_result(packet, compact)
