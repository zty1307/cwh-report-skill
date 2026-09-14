import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_source_spans import source_segments, selected_quote
from normalize_cwh_analysis import evidence_sentence
from normalize_cwh_analysis import judgment_heading


def test_segments_preserve_every_character_and_distinguish_repeated_text():
    text = '甲表示：“需要协同。”\n第一句。第一句。末尾'
    rows = source_segments(text)
    assert ''.join(row['text'] for row in rows) == text
    for row in rows:
        quote, start, end = selected_quote(text, [row['id'], row['id']])
        assert quote == text[start:end] == row['text']
    assert selected_quote(text, [4, 4])[1] > selected_quote(text, [3, 3])[1]


@pytest.mark.parametrize('span', [[0, 1], [2, 1], [1, 99], [True, 1], [1], '1,2'])
def test_invalid_span_never_guesses_offsets(span):
    with pytest.raises(ValueError):
        selected_quote('原文。', span)


def test_source_scoped_ids_reject_cross_document_range():
    assert selected_quote('甲原文。', ['p甲/1', 'p甲/1'], 'p甲')[0] == '甲原文。'
    with pytest.raises(ValueError, match='belong to this original source'):
        selected_quote('甲原文。', ['p乙/1', 'p乙/1'], 'p甲')
    with pytest.raises(ValueError):
        selected_quote('甲原文。', [1, 1], 'p甲')


def test_sentence_scheme_preserves_formatting_without_mid_sentence_boundaries():
    text = '前文。\n增量有限，但\n存量\n潜力巨大。\n末尾说明'
    segments = source_segments(text, 'source', 'sentence_v2')
    assert ''.join(s['text'] for s in segments) == text
    assert len(segments) == 3
    assert selected_quote(text, ['source/2', 'source/2'], 'source', 'sentence_v2')[0].endswith('潜力巨大。')
    assert len(source_segments(text)) > len(segments)  # Legacy offsets remain reproducible.


def test_judgment_frame_is_neutral_idempotent_and_preserves_explicit_stance():
    assert judgment_heading('政策需要适应地区差异。') == '认为政策需要适应地区差异'
    assert judgment_heading('质疑部分做法缺乏依据') == '质疑部分做法缺乏依据'
    assert judgment_heading('监测期内尚未形成评论性观点') == '监测期内尚未形成评论性观点'
    heading = judgment_heading('政策需要适应地区差异')
    assert judgment_heading(heading) == heading


def test_exact_name_prefix_is_expanded_without_double_attribution():
    row = {'speaker_name': '李明', 'attribution': '甲大学教授李明', 'formal_claim': '李明表示，需要统筹供需。'}
    assert evidence_sentence(row) == '甲大学教授李明表示，需要统筹供需'
    assert row['formal_claim'] == '李明表示，需要统筹供需。'
    row['formal_claim'] = '李明所在城市需要统筹供需。'
    assert evidence_sentence(row) == '甲大学教授李明认为，李明所在城市需要统筹供需'
