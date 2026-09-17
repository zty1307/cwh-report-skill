"""Reading-only batches cannot skip final native selection or source gates."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_article_reading import reading_prompt, reading_contract, reading_input_packet


def test_reading_contract_does_not_request_provisional_topic_composition():
    prompt = reading_prompt()
    assert '不输出cluster、heading、clusters' in prompt
    assert 'quote_range' in prompt and 'published_at' in prompt
    assert 'actual_model' not in prompt
    contract = reading_contract({'items': [{'id': 'r1'}, {'id': 'w2'}]})
    assert '["r1","w2"]' in contract


def test_production_reading_prompt_matches_the_tested_semantic_scope():
    prompt = reading_prompt()
    assert '单纯说明会议首次核准' in prompt
    assert '本阶段不写标题、不分组、不选最终声音数' in prompt
    assert '完整年' in prompt or '连续完整年月日' in prompt


def test_reading_input_preserves_every_source_but_not_later_selection_instructions():
    import copy
    packet = {'topic': '公共服务', 'items': [{'id': 'r1', 'content': '完整原文',
        'segments': [{'id': 'r1/1', 'text': '完整原文'}]}],
        'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12},
        'agenda_topics': ['公共服务', '基础设施']}
    original = copy.deepcopy(packet)
    observed = reading_input_packet(packet)
    assert packet == original
    assert observed == {key: value for key, value in original.items() if key != 'formal_selection'}
    assert packet['formal_selection']['max_independent_voices'] == 12


def test_production_reading_call_does_not_receive_final_selection_rules(tmp_path, monkeypatch):
    import time
    import run_cwh_compiled_worker as worker
    observed = []
    def model(packet, *args, **kwargs):
        observed.append(packet)
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'claims': [], 'reason': '只有事实通稿'}]}, {'session_id': 'native-reading'}
    monkeypatch.setattr(worker, 'semantic_json', model)
    source = {'topic': '公共服务', 'items': [{'id': 'r1', 'origin': 'monitoring', 'content': '完整事实通稿'}],
              'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12}}
    choices, run = worker.author_topic_decisions([source], reading_prompt(), [], tmp_path,
        time.monotonic()+60, reuse_cache=False, allow_article_batches=False, reading_only=True)
    assert len(observed) == 1 and 'formal_selection' not in observed[0]
    assert ''.join(row['text'] for row in observed[0]['items'][0]['segments']) == '完整事实通稿'
    assert source['formal_selection']['max_independent_voices'] == 12
    assert choices[0]['items'][0]['decision'] == 'excluded'
