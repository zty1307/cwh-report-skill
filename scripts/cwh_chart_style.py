"""Fixed report chart fallback; never masquerades as a monitoring-system image."""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def topic_chart_spec(values):
    style = json.loads((ROOT / 'config/chart_style.v1.json').read_text(encoding='utf-8'))['topic_distribution']
    pairs = values.items() if hasattr(values, 'items') else values
    items = sorted(((str(k), int(v or 0)) for k, v in pairs), key=lambda item: -item[1])
    return style, [(name, value, f'{value / 10000:.1f}万') for name, value in items]


def valid_image(path):
    from PIL import Image
    try:
        with Image.open(path) as img:
            if img.width < 2 or img.height < 2:
                return False
            img.verify()
        return True
    except (OSError, ValueError, TypeError):
        return False


def write_topic_chart(path, values):
    from PIL import Image, ImageDraw, ImageFont
    style, items = topic_chart_spec(values)
    font_path = next((p for p in [Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/simhei.ttf'),
                                 Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
                      if p.is_file()), None)
    if font_path is None:
        raise RuntimeError('A Chinese chart font is required; refusing missing-glyph fallback')
    font = ImageFont.truetype(str(font_path), style['font_size'])
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    wrapped = []
    for name, value, label in items:
        lines, line = [], ''
        for character in name:
            if line and measure.textlength(line + character, font=font) > style['label_width'] - 24:
                lines.append(line); line = ''
            line += character
        lines.append(line)
        wrapped.append((lines, value, label, max(style['row_height'], 30 * len(lines) + 16)))
    width = style['width']
    content_height = sum(row[3] for row in wrapped)
    height = max(style['minimum_height'], content_height + 60)
    image = Image.new('RGB', (width, height), style['background'])
    draw = ImageDraw.Draw(image)
    x0, chart_width = style['label_width'], width - style['label_width'] - 150
    y = (height - content_height) // 2
    draw.line((x0, y, x0, y + content_height), fill=style['axis_color'], width=2)
    maximum = max([row[1] for row in wrapped] + [1])
    for lines, value, label, row_height in wrapped:
        middle = y + row_height // 2
        for index, line in enumerate(lines):
            line_width = draw.textlength(line, font=font)
            draw.text((x0 - 20 - line_width, middle - len(lines)*15 + index*30), line,
                      font=font, fill=style['text_color'])
        length = round(chart_width * value / maximum)
        if length > 0:
            draw.rectangle((x0 + 2, middle - 22, x0 + length, middle + 22), fill=style['bar_color'])
        draw.text((x0 + length + 12, middle - 15), label, font=font, fill=style['text_color'])
        y += row_height
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); image.save(path)
    return {'style': 'chart_style.v1/topic_distribution', 'origin': 'program_fallback',
            'image_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'style_sha256': hashlib.sha256((ROOT / 'config/chart_style.v1.json').read_bytes()).hexdigest(),
            'ordered_values': [{'label': n, 'value': v, 'display_value': label} for n, v, label in items]}


def verify_topic_chart_manifest(path, manifest, values):
    """Bind a permitted generated chart to actual pixels, config and source values."""
    path = Path(path)
    if not isinstance(manifest, dict) or not valid_image(path):
        return False
    if manifest.get('style') != 'chart_style.v1/topic_distribution' or manifest.get('origin') != 'program_fallback':
        return False
    _, items = topic_chart_spec(values)
    expected = [{'label': n, 'value': v, 'display_value': label} for n, v, label in items]
    return (manifest.get('ordered_values') == expected
            and manifest.get('image_sha256') == hashlib.sha256(path.read_bytes()).hexdigest()
            and manifest.get('style_sha256') == hashlib.sha256((ROOT / 'config/chart_style.v1.json').read_bytes()).hexdigest())
