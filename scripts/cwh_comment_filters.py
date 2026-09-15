"""Exact operation-only noise rules; ambiguous policy comments stay for review."""
import re
from cwh_writing_rules import writing_rules


def is_procedural_only(text):
    value = re.sub(r'[\s。！!…]+$', '', str(text or '').strip())
    return value in writing_rules()['comments'].get('procedural_only_texts', [])
