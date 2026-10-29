"""Freeze completed collection inputs across semantic retries, not approvals."""
import hashlib
import json
import copy
from cwh_pipeline_runtime import atomic_write_json


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def collection_key(plan,index,policy,semantic_command,search_command):
    # Deliberately exclude remaining seconds, errors and validation feedback.
    return digest({'plan':plan,'source_sha256':index['source_sha256'],
        'candidate_count':index['candidate_count'],'topics':[r['topic'] for r in index['topics']],
        'policy':policy,'semantic_command_sha256':digest(semantic_command),
        'search_command_sha256':digest(search_command)})


def load(path,key):
    if not path.is_file():
        return None
    record=json.loads(path.read_text('utf-8'))
    payload=record.get('payload')
    if record.get('input_sha256')!=key or record.get('payload_sha256')!=digest(payload):
        raise ValueError('Prepared research changed; refuse to replace completed sources with a smaller pool')
    if not isinstance(payload,dict) or set(payload)!={'packets','topic_plans','observed'}:
        raise ValueError('Malformed prepared collection checkpoint')
    return payload


def save(path,key,packets,topic_plans,observed):
    if path.exists():
        raise ValueError('Prepared research is immutable once completed')
    payload={'packets':packets,'topic_plans':topic_plans,'observed':observed}
    atomic_write_json(path,{'input_sha256':key,'payload':payload,
        'payload_sha256':digest(payload),
        'scope':'Immutable completed collection and raw nominations only; no final claim or semantic approval cached here.'})


def carry_repair_runs(previous,repair):
    """Preserve original read coverage and separately identify each local edit."""
    if not previous.get('topic_runs'):
        return repair
    return {**repair,'transport':'sequential_single_topic_semantic',
        'topic_runs':copy.deepcopy(previous['topic_runs']),
        'selected_repair_runs':[*copy.deepcopy(previous.get('selected_repair_runs') or []),copy.deepcopy(repair)],
        'seconds':previous.get('seconds',0)+repair.get('seconds',0)}
