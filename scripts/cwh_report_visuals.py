"""Baseline-locked report charts/table; model input supplies facts, never styling."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/report_visual_style.v1.json'
TABLE = ROOT / 'templates/topic_table.xml'


def style():
    return json.loads(CONFIG.read_text('utf-8'))


def ten_thousands(value):
    number = (Decimal(str(value)) / 10000).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return format(number, 'f').rstrip('0').rstrip('.') if number else '0'


def payload(data):
    stats = data.get('statistics') or {}
    raw_date = str((data.get('meeting') or {}).get('date') or '')
    match = re.search(r'(?:\d{4}[-/.年])?(\d{1,2})[-/.月](\d{1,2})', raw_date)
    date = f'{int(match[1])}月{int(match[2])}日' if match else raw_date
    topics = [{'label': str(r.get('topic') or r.get('display') or ''),
               'value': int(r.get('spread_count', 0) or r.get('total_samples', 0) or 0)}
              for r in data.get('topic_stats') or []]
    trend = [{'date': str(k), 'value': int(v or 0)} for k, v in sorted((stats.get('by_date') or {}).items())
             if re.search(r'\d', str(k))]
    return {'date': date, 'total': int(stats.get('total_spread', 0) or 0),
            'trend': trend, 'topics': sorted(topics, key=lambda r: -r['value'])}


def _fonts(scale):
    from PIL import ImageFont
    supplied = os.environ.get('CWH_CHART_FONT', '')
    regular = next((p for p in (Path(supplied) if supplied else Path('__unset__'),
        Path('C:/Windows/Fonts/msyh.ttc')) if p.is_file()), None)
    if regular is None:
        raise RuntimeError('Baseline chart font Microsoft YaHei is required; set CWH_CHART_FONT to the installed real font. No silent font substitution.')
    bold = Path(os.environ.get('CWH_CHART_BOLD_FONT', str(regular.with_name('msyhbd.ttc'))))
    if not bold.is_file():
        raise RuntimeError('Baseline bold chart font is required; set CWH_CHART_BOLD_FONT.')
    for path in (regular,bold):
        if ImageFont.truetype(str(path),22).getname()[0] not in ('Microsoft YaHei','微软雅黑'):
            raise RuntimeError('Chart font must be the real Microsoft YaHei family, not a substitute')
    return (lambda size, is_bold=False: ImageFont.truetype(str(bold if is_bold else regular), round(size*scale)),
            {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in (regular, bold)})


def _wrap(draw, text, font, width):
    lines, current = [], ''
    for char in text:
        if current and (char == '\n' or draw.textlength(current+char, font=font) > width):
            lines.append(current)
            current = ''
        if char != '\n':
            current += char
    return lines + ([current] if current else [])


def _axis_max(value):
    if value <= 0:
        return 5
    raw = value / 5
    unit = 10 ** math.floor(math.log10(raw))
    step = next((m*unit for m in (1, 2, 3, 5, 10) if m*unit >= raw), 10*unit)
    return step * 5


def write_report_charts(data, out_dir):
    from PIL import Image, ImageDraw
    spec, facts = style(), payload(data)
    scale = spec['render_scale']
    font, font_hashes = _fonts(scale)
    normal, title, subtitle = font(spec['text_size']), font(spec['title_size'], True), font(spec['subtitle_size'], True)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests, paths = {}, {}
    for kind in ('trend', 'topics'):
        width, height = spec['width'], spec['height']
        probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        title_text = spec['trend_title' if kind == 'trend' else 'topic_title'].format(date=facts['date'])
        # Extra title/label lines grow the canvas, never crop or shrink text.
        title_lines = _wrap(probe, title_text, title, (width-30)*scale)
        title_extra = (len(title_lines)-1) * 46
        height += title_extra
        rows = []
        if kind == 'topics':
            cfg = spec['topics']
            for row in facts['topics']:
                lines = _wrap(probe, row['label'], normal, (cfg['axis_x']-cfg['label_gap']-8)*scale)
                row_height = max(cfg['minimum_row_height'], len(lines)*cfg['line_height']+12)
                rows.append((row, lines, row_height))
            base_height = cfg['bottom']-cfg['top']
            content_height = max(base_height, sum(r[2] for r in rows))
            height += content_height-base_height
        im = Image.new('RGB', (width*scale, height*scale), 'white')
        draw = ImageDraw.Draw(im)
        def text(x, y, value, f=normal, anchor='mm'):
            draw.text((round(x*scale), round(y*scale)), str(value), font=f, fill=spec['text_color'], anchor=anchor)
        def line(coords, color, size=1):
            draw.line(tuple(round(n*scale) for n in coords), fill=color, width=max(1, round(size*scale)))
        def dot(x, y, r, fill):
            draw.ellipse(tuple(round(n*scale) for n in (x-r,y-r,x+r,y+r)), fill=fill)
        for i, value in enumerate(title_lines):
            text(width/2, 46+i*46, value, title)
        if kind == 'trend':
            cfg = spec['trend']
            text(width/2, 106+title_extra, spec['total_title'].format(total=ten_thousands(facts['total'])), subtitle)
            top, bottom = cfg['top']+title_extra, cfg['bottom']+title_extra
            maximum = _axis_max(max([r['value'] for r in facts['trend']] + [0]))
            for i in range(6):
                y = bottom-(bottom-top)*i/5
                line((cfg['left'], y, cfg['right'], y), spec['grid_color'])
                for x in (cfg['left'], cfg['right']): dot(x,y,6,spec['grid_color'])
                text(cfg['left']-20,y,f'{maximum*i/5:g}',anchor='rm')
            n = len(facts['trend'])
            pts = [(cfg['left']+(i+.5)*(cfg['right']-cfg['left'])/max(n,1), bottom-(bottom-top)*r['value']/maximum)
                   for i,r in enumerate(facts['trend'])]
            for a,b in zip(pts,pts[1:]): line((*a,*b),spec['color'],cfg['line_width'])
            stride = max(1, math.ceil(n/8))
            for i, ((x,y),row) in enumerate(zip(pts,facts['trend'])):
                dot(x,y,6,spec['color']); dot(x,y,2,'white')
                if i%stride == 0 or i == n-1:
                    stamp=re.search(r'(?:\d{4}[-/.年])?(\d{1,2})[-/.月](\d{1,2})',row['date'])
                    label = f'{int(stamp[1])}/{int(stamp[2])}' if stamp else row['date']
                    text(x,bottom+29,label)
            if pts:
                peak = max(range(n),key=lambda i:facts['trend'][i]['value'])
                text(pts[peak][0],pts[peak][1]-19,facts['trend'][peak]['value'])
            label_width = draw.textlength(spec['legend'],font=normal)/scale
            lx = (width-label_width-44)/2
            line((lx,height-20,lx+40,height-20),spec['color'],2)
            dot(lx+20,height-20,6,spec['color']); dot(lx+20,height-20,2,'white')
            text(lx+46,height-20,spec['legend'],anchor='lm')
        else:
            cfg = spec['topics']; axis=cfg['axis_x']; y=cfg['top']+title_extra
            extra = (content_height-sum(r[2] for r in rows))/max(len(rows),1)
            line((axis,y,axis,y+content_height),spec['grid_color'])
            dot(axis,y,6,spec['grid_color']); dot(axis,y+content_height,6,spec['grid_color'])
            maximum=max([r['value'] for r,_,_ in rows]+[1])
            widest_value=max([draw.textlength(ten_thousands(r['value'])+'万',font=normal)/scale for r,_,_ in rows]+[0])
            available=min(cfg['right']-axis,width-axis-widest_value-20)
            for row,labels,rh in rows:
                rh += extra; middle=y+rh/2
                for index,label in enumerate(labels):
                    text((axis-cfg['label_gap'])/2,middle+(index-(len(labels)-1)/2)*cfg['line_height'],label)
                # Leave room for arbitrarily large value labels.
                display=ten_thousands(row['value'])+'万'
                length=max(0,available*row['value']/maximum)
                if length:
                    draw.rectangle(tuple(round(v*scale) for v in (axis+1,middle-cfg['bar_height']/2,axis+length,middle+cfg['bar_height']/2)),fill=spec['color'])
                text(axis+length+12,middle,display,anchor='lm')
                y+=rh
                if y<cfg['top']+title_extra+content_height-1: line((axis-6,y,axis,y),spec['grid_color'])
        key='trend_distribution' if kind=='trend' else 'topic_distribution'
        path=out/f'{key}_template.png'
        im.save(path)
        paths[key]=str(path)
        manifests[key]={'origin':'baseline_template','version':spec['version'],
            'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            'font_sha256':font_hashes,'input':facts,'title':title_text}
    return paths, manifests


def verify_report_charts(data, paths, manifests):
    from cwh_chart_style import valid_image
    facts=payload(data)
    for key in ('trend_distribution','topic_distribution'):
        path=Path(paths.get(key) or '')
        m=manifests.get(key) or {}
        if (not valid_image(path) or m.get('input') != facts or m.get('origin')!='baseline_template'
            or m.get('version')!=style()['version'] or m.get('config_sha256')!=hashlib.sha256(CONFIG.read_bytes()).hexdigest()
            or m.get('image_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest()):
            return False
    return True


def add_fixed_topic_table(document, rows, domestic_label):
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.shared import Pt
    table_xml=parse_xml(TABLE.read_bytes())
    prototype=table_xml.findall(qn('w:tr'))[-1]
    table_xml.remove(prototype)
    headers=table_xml.findall(qn('w:tr'))
    # This slot is the current input channel scope, not a style decision.
    headers[0].findall(qn('w:tc'))[2].xpath('.//w:t')[0].text=domestic_label
    for values in rows:
        if len(values) not in (6,9): raise ValueError('Topic row must contain six facts and optional three reviewed ratios')
        row=deepcopy(prototype)
        for i,cell in enumerate(row.findall(qn('w:tc'))):
            from docx.text.paragraph import Paragraph
            p=Paragraph(cell.find(qn('w:p')),None)
            value=values[i] if i<len(values) else ''
            # Missing review is blank, never a fabricated percentage.
            if value in ('待分析',None): value=''
            r=p.add_run(str(value)); r.font.name='微软雅黑';r.font.size=Pt(11)
            fonts=r._element.get_or_add_rPr().get_or_add_rFonts()
            for attr in ('ascii','hAnsi','eastAsia'): fonts.set(qn('w:'+attr),'微软雅黑')
        table_xml.append(row)
    document._body._body.insert_element_before(table_xml,'w:sectPr')
    return Table(table_xml,document._body)


def verify_topic_table(document_xml):
    """Check visual structure independently of row count and evidence availability."""
    from lxml import etree
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        table=etree.fromstring(document_xml).xpath('//w:body/w:tbl[1]',namespaces=ns)[0]
        grid=[int(x) for x in table.xpath('./w:tblGrid/w:gridCol/@w:w',namespaces=ns)]
        rows=table.xpath('./w:tr',namespaces=ns)
        if grid!=style()['table_grid_twips'] or len(rows)<2:return False
        if len(rows[0].xpath('./w:tc/w:tcPr/w:vMerge[@w:val="restart"]',namespaces=ns))!=6:return False
        if rows[0].xpath('./w:tc[7]/w:tcPr/w:gridSpan/@w:val',namespaces=ns)!=['3']:return False
        for p in table.xpath('.//w:p',namespaces=ns):
            if p.xpath('./w:pPr/w:ind/@w:firstLine',namespaces=ns)!=['0']:return False
            if p.xpath('./w:pPr/w:spacing/@w:line',namespaces=ns)!=['624']:return False
        for run in table.xpath('.//w:r',namespaces=ns):
            if run.xpath('./w:rPr/w:rFonts/@w:eastAsia',namespaces=ns)!=['微软雅黑']:return False
            if run.xpath('./w:rPr/w:sz/@w:val',namespaces=ns)!=['22']:return False
        return True
    except (ValueError,IndexError,etree.XMLSyntaxError):
        return False
