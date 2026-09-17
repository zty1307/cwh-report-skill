import copy
from pathlib import Path
import sys
import time
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_hotword_batches import partition_candidates, subset_packet, review_hotword_batches, retain_native_extensions


def packet():
    rows = [{'term': '公共服务', 'topic_index': 1, 'sample_url_refs': ['u1']},
            {'term': '普惠托育', 'topic_hits': [2], 'sample_url_refs': ['u2']},
            {'term': '基础设施', 'sample_url_refs': ['u3']}]
    return {'candidates': rows, 'candidate_source_windows': [
        {'term': row['term'], 'source_windows': [{'url_ref': f'u{i}', 'excerpt': row['term'],
         'excerpt_start_in_packet': 0, 'excerpt_end_in_packet': len(row['term'])}]} for i, row in enumerate(rows, 1)],
        'source_urls': {'u1': 'https://example.test/a', 'u2': 'https://example.test/b', 'u3': 'https://example.test/c'},
        'topics': [{'index': 1}, {'index': 2}], 'target_term_count': 3,
        'delivery_policy': 'deliver_available_with_gaps'}


def test_partition_keeps_unassigned_anchors_and_all_candidates_exactly_once():
    original = packet()
    before = copy.deepcopy(original)
    parts = partition_candidates(original)
    assert [row for part in parts for row in part] == original['candidates']
    assert original == before
    selected = subset_packet(original, parts[1])
    assert selected['topics'] == original['topics']
    assert selected['candidate_source_windows'] == [original['candidate_source_windows'][1]]
    assert selected['source_urls'] == {'u2': 'https://example.test/b'}


def test_every_partition_then_real_global_pass_preserves_native_selections(tmp_path):
    calls = []
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        calls.append(name)
        assert timeout <= 90
        return {'selected': [{'term': row['term']} for row in part['candidates']],
                'second_pass_completed': True, 'review_method': 'ai_semantic_review'}, {'session_id': name}
    result = review_hotword_batches(packet(), 'rules', [], tmp_path, time.monotonic() + 300, model)
    assert calls == ['hotword-batch-1', 'hotword-batch-2', 'hotword-batch-3', 'hotword-global-review']
    assert len(result['selected']) == 3
    assert result['batch_review_audit']['candidate_count'] == 3


def test_native_source_backed_extensions_remain_allowed_without_inventing_counts():
    original = packet()
    before = copy.deepcopy(original)
    expanded = retain_native_extensions(original, [{'term': '普惠托育服务', 'topic_hits': [2],
                                                    'evidence_aliases': ['普惠托育']}])
    assert expanded['candidates'][-1]['term'] == '普惠托育服务'
    assert 'document_count' not in expanded['candidates'][-1]
    assert expanded['candidate_source_windows'][-1]['source_windows'] == original['candidate_source_windows'][1]['source_windows']
    assert original == before


@pytest.mark.parametrize('fault', ['unknown', 'no_second_pass'])
def test_no_invented_terms_or_host_certified_second_pass(tmp_path, fault):
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        return {'selected': [{'term': '凭空制造' if fault == 'unknown' else row['term']} for row in part['candidates']],
                'second_pass_completed': False}, {'session_id': name}
    with pytest.raises(ValueError):
        review_hotword_batches(packet(), 'rules', [], tmp_path, time.monotonic() + 300, model)


def test_failed_partition_cannot_be_misreported_as_global_completion(tmp_path):
    from cwh_host_research import HostModelError
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[4])
        raise HostModelError('actual provider timeout', 124, run={'session_id': 'timeout-id'})
    with pytest.raises(HostModelError):
        review_hotword_batches(packet(), 'rules', [], tmp_path, time.monotonic() + 300, fail)
    assert calls == ['hotword-batch-1']
    assert (tmp_path / 'hotword-batch-1.packet.json').is_file()
    assert not (tmp_path / 'hotword-global-review.packet.json').exists()


def test_unwitnessed_extension_is_local_gap_not_a_whole_workbook_failure(tmp_path):
    seen = []
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        selected = [{'term': row['term']} for row in part['candidates']]
        if name == 'hotword-batch-1':
            selected.append({'term': '原文没有的新增词'})
        seen.append(name)
        return {'selected': selected, 'second_pass_completed': True}, {'session_id': name}
    result = review_hotword_batches(packet(), 'rules', [], tmp_path, time.monotonic() + 300, model)
    assert len(result['selected']) == 3
    assert seen[-1] == 'hotword-global-review'
    gaps = result['batch_review_audit']['source_witness_quarantines']
    assert gaps[0]['native_selection'] == {'term': '原文没有的新增词'}
    assert gaps[0]['native_run']['session_id'] == 'hotword-batch-1'
    assert (tmp_path / 'hotword_source_quarantine.json').exists()


def test_strict_delivery_still_rejects_unwitnessed_extension(tmp_path):
    source = packet()
    source.pop('delivery_policy')
    def model(*args, **kwargs):
        return {'selected': [{'term': '原文没有的新增词'}]}, {'session_id': 'actual'}
    with pytest.raises(ValueError, match='no literal'):
        review_hotword_batches(source, 'rules', [], tmp_path, time.monotonic() + 300, model)
