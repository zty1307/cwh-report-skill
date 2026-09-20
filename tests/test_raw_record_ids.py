import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_raw_record_ids import alias_record_ids, restore_record_ids


def test_repair_context_reuses_current_aliases_without_repairing_unknown_ids():
    from cwh_raw_record_ids import alias_previous_review
    source = {'items': [{'record_id': 'long:source:hash', 'decision': 'exclude', 'transport_record_id': 'r8'},
                        {'record_id': 'unknown:typo', 'decision': 'include'}]}
    frozen = copy.deepcopy(source)
    result = alias_previous_review(source, {'r1': 'long:source:hash'})
    assert result['items'][0] == {'record_id': 'r1', 'decision': 'exclude'}
    assert result['items'][1] == source['items'][1]
    assert source == frozen


def test_long_identifiers_round_trip_without_changing_evidence_or_native_decisions():
    source = {'items': [{'record_id': 'system_raw:31:81088e6463fd', 'content': '原始报道全文', 'source_row': 31}]}
    original = copy.deepcopy(source)
    packet, mapping = alias_record_ids(source)
    assert packet['items'][0] == {**source['items'][0], 'record_id': 'r1'}
    answer = {'items': [{'record_id': 'r1', 'decision': 'exclude', 'review_reason': '原文不支持'}]}
    before = copy.deepcopy(answer)
    result = restore_record_ids(answer, mapping)
    assert result['items'][0] == {**answer['items'][0], 'record_id': original['items'][0]['record_id'], 'transport_record_id': 'r1'}
    assert source == original and answer == before


@pytest.mark.parametrize('bad', ['r2', 'R1', 'r01', 'system_raw:31:81088e463fd'])
def test_unknown_or_misspelled_ids_are_never_guessed(bad):
    with pytest.raises(ValueError, match='Unknown raw transport'):
        restore_record_ids({'items': [{'record_id': bad}]}, {'r1': 'system_raw:31:81088e6463fd'})


def test_alias_roundtrip_never_fills_missing_rows_or_merges_duplicates():
    result = restore_record_ids({'items': [{'record_id': 'r1'}, {'record_id': 'r1'}]}, {'r1': 'source1', 'r2': 'source2'})
    assert [row['record_id'] for row in result['items']] == ['source1', 'source1']
    from run_cwh_inline_review import validate_transport_result
    with pytest.raises(ValueError, match='exactly every'):
        validate_transport_result('overseas', {'items': [{'record_id': 'source1'}, {'record_id': 'source2'}]},
                                  {**result, 'review_method': 'ai_semantic_review'})
