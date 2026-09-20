import copy
import sys
from pathlib import Path
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_hotword_batches import review_hotword_batches
from cwh_host_research import HostModelError
from test_hotword_batches import packet


@pytest.mark.parametrize('failure', [None, 'nomination_timeout', 'review_timeout', 'unreviewed', 'invented'])
def test_shortfall_requires_native_supplement_and_separate_review_without_erasing_prior_terms(tmp_path, failure):
    source = packet()
    source['minimum_term_count'] = 3
    source['candidate_source_windows'][0]['source_windows'][0].update(
        excerpt='公共服务需要落实配套资金。', excerpt_end_in_packet=len('公共服务需要落实配套资金。'))
    frozen = copy.deepcopy(source)
    calls = []
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        calls.append(name)
        if name == 'hotword-supplement':
            assert part['existing_reviewed_terms'] == ['公共服务', '普惠托育']
            if failure == 'nomination_timeout':
                raise HostModelError('timeout', 124, run={'session_id': name})
            term = '凭空捏造' if failure == 'invented' else '配套资金'
            return {'selected': [{'term': term, 'evidence_aliases': []}],
                    'second_pass_completed': False}, {'session_id': name}
        if name == 'hotword-supplement-review':
            if failure == 'review_timeout':
                raise HostModelError('timeout', 124, run={'session_id': name})
            return {'selected': [{'term': r['term']} for r in part['candidates']],
                    'second_pass_completed': failure != 'unreviewed'}, {'session_id': name}
        if name == 'hotword-global-review':
            return {'selected': [{'term': '公共服务'}, {'term': '普惠托育'}],
                    'second_pass_completed': True}, {'session_id': name}
        return {'selected': [{'term': r['term']} for r in part['candidates']],
                'second_pass_completed': False}, {'session_id': name}
    result = review_hotword_batches(source, 'rules', [], tmp_path, time.monotonic() + 300, model)
    assert source == frozen
    assert 'hotword-supplement' in calls
    assert result['second_pass_completed'] is True
    assert {'公共服务', '普惠托育'} <= {r['term'] for r in result['selected']}
    if failure:
        assert len(result['selected']) == 2
    else:
        assert calls[-1] == 'hotword-supplement-review'
        assert len(result['selected']) == 3
        assert result['batch_review_audit']['supplement']['status'] == 'supplement_independently_reviewed'


def test_without_remaining_budget_keep_reviewed_cloud_and_explicit_shortfall(tmp_path, monkeypatch):
    import cwh_hotword_batches as module
    source = packet()
    source['minimum_term_count'] = 3
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100.0)
    calls = []
    def model(part, prompt, command, folder, name, timeout, **kwargs):
        calls.append(name)
        return {'selected': [{'term': part['candidates'][0]['term']}],
                'second_pass_completed': name == 'hotword-global-review'}, {'session_id': name}
    result = review_hotword_batches(source, 'rules', [], tmp_path, 170.0, model)
    assert calls[-1] == 'hotword-global-review'
    assert len(result['selected']) == 1
    assert result['batch_review_audit']['supplement']['status'] == 'pending_no_budget'
