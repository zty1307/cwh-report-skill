import json
from pathlib import Path
from unittest.mock import patch
import sys
from PIL import Image
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import formalize_cwh_report as formal


def test_late_review_draws_real_cloud_instead_of_renaming_svg(tmp_path):
    audit = tmp_path / 'review.json'
    payload = {'status': 'ai_review_complete', 'review_method': 'ai_semantic_review',
               'second_pass_completed': True, 'settings': {}, 'selected': [{'term': '安全生产'}]}
    audit.write_text(json.dumps(payload), encoding='utf-8')
    original = audit.read_bytes()
    charts = tmp_path / 'charts'
    charts.mkdir()
    svg = charts / 'hotword_distribution.svg'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding='utf-8')
    false_png = charts / 'hotword_distribution_pipeline.png'
    false_png.write_bytes(svg.read_bytes())
    data = {'statistics': {'by_platform': {}, 'by_date': {}}, 'topic_stats': [],
            'hotwords': [{'word': '安全生产', 'count': 10, 'authority': 'reviewed_wordcloud_audit',
                          'selection_method': 'ai_semantic_review'}],
            'artifacts': {'hotword_audit': str(audit), 'wordcloud_image': str(false_png),
                          'charts': {'hotword_distribution': str(svg)}}}
    def render(review, target):
        assert review['selected'] == payload['selected']
        Image.new('RGB', (25, 15), 'navy').save(target)
        review['image_path'] = str(target)
    with patch('cwh_hotword_pipeline.render_wordcloud_png', side_effect=render) as draw:
        result = formal.ensure_docx_chart_images(data, tmp_path)
    assert draw.call_count == 1
    with Image.open(result['hotword_distribution']) as im:
        assert im.format == 'PNG' and im.size == (25, 15)
    assert audit.read_bytes() == original
    assert svg.read_text('utf-8').startswith('<svg')
