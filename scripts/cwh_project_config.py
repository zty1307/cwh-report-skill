"""Resolve an explicitly confirmed, project-local input convention.

Never discover configuration inside raw evidence or the installed Skill. Read
only the launcher working directory, or an explicitly supplied config path.
The returned receipt is frozen into each new job; resumes keep their contract.
"""
from pathlib import Path
import hashlib
import json


def resolve_agenda_order(explicit=None, config_path='', *, cwd=None):
    path = Path(config_path).resolve() if config_path else Path(cwd or Path.cwd()).resolve() / 'cwh_project.json'
    receipt = {'confirmed': False, 'basis': 'not_confirmed'}
    if config_path or path.is_file():
        data = path.read_bytes()
        config = json.loads(data.decode('utf-8-sig'))
        if not isinstance(config, dict) or config.get('schema_version') != 1:
            raise ValueError('Unsupported CWH project config schema')
        rule = config.get('numbered_child_agenda_order', {})
        if not isinstance(rule, dict) or type(rule.get('confirmed')) is not bool:
            raise ValueError('Project agenda-order confirmation must be a boolean')
        evidence = rule.get('confirmation_evidence', '')
        if rule['confirmed'] and (not isinstance(evidence, str) or not evidence.strip()):
            raise ValueError('Confirmed project convention requires actual user confirmation evidence')
        receipt = {'confirmed': rule['confirmed'], 'basis': 'project_config',
                   'config_path': str(path), 'config_sha256': hashlib.sha256(data).hexdigest(),
                   'confirmation_evidence': evidence}
    if explicit is not None:
        if type(explicit) is not bool:
            raise ValueError('Explicit agenda-order confirmation must be a boolean')
        receipt = {**receipt, 'confirmed': explicit, 'basis': 'explicit_cli'}
    return receipt
