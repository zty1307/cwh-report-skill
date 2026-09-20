"""Publish byte-identical, model/time-labelled delivery copies; keep run files."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil


def publish(report_dir, output_dir, model):
    report_dir, output_dir = Path(report_dir).resolve(), Path(output_dir).resolve()
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', model).strip(' .')
    if not label:
        raise ValueError('A real model label is required')
    data = json.loads((report_dir / 'report_data.json').read_text('utf-8-sig'))
    raw_time = data.get('generated_at')
    if not isinstance(raw_time, str) or not raw_time:
        raise ValueError('Missing actual generation timestamp; do not substitute copy time')
    generated = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
    if generated.tzinfo:
        from datetime import timezone, timedelta
        generated = generated.astimezone(timezone(timedelta(hours=8)))
    prefix = f'{label}_{generated:%H%M}'
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [('cwh_formal_report.docx', '报告.docx'),
             ('cwh_dashboard.html', '工作台.html'), ('cwh_data_workbook.xlsx', '数据.xlsx')]
    planned = [(report_dir / source, output_dir / f'{prefix}_{suffix}') for source, suffix in files]
    if any(not source.is_file() for source, _ in planned):
        raise ValueError('All three source artifacts are required')
    if any(target.exists() for _, target in planned):
        raise FileExistsError('Labelled delivery already exists; never overwrite a prior version')
    rows = []
    for source, target in planned:
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        shutil.copy2(source, target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == before
        rows.append({'source': str(source), 'output': str(target), 'sha256': before})
    receipt = {'model': model, 'generated_at': raw_time, 'display_timezone': 'Asia/Shanghai',
               'timestamp_basis': 'report_data.generated_at, not copy time',
               'source_unchanged': True, 'files': rows}
    (output_dir / f'{prefix}_命名记录.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report-dir', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--model', required=True)
    a = p.parse_args()
    print(json.dumps(publish(a.report_dir, a.output_dir, a.model), ensure_ascii=False))
