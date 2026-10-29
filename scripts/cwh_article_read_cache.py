"""Reuse completed article readings across changed batches, with source/run proofs."""
import copy
import hashlib
import json
from pathlib import Path
from cwh_pipeline_runtime import atomic_write_json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def key(packet, item, prompt, command):
    # Scoped item IDs and batch membership are transport details. Context, model,
    # source metadata, segmentation and rules can change the semantic task.
    source = {k: item.get(k) for k in ('origin', 'url', 'title', 'source', 'account',
        'published_at', 'content', 'segment_scope', 'segment_scheme')}
    return digest({'source': source, 'topic': packet['topic'], 'period': packet['period'],
                   'agenda_topics': packet.get('agenda_topics'),
                   'meeting_context': packet.get('meeting_context'),
                   'prompt': prompt, 'command': command})


def proofs(run):
    found = {}
    def visit(value):
        if isinstance(value, dict):
            for name, child in value.items():
                if name in {'log', 'receipt'} and isinstance(child, str) and Path(child).is_file():
                    found[str(Path(child).resolve())] = hashlib.sha256(Path(child).read_bytes()).hexdigest()
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(run)
    return found


def store(root, cache_key, choice, run):
    if choice.get('classification_origin') in {'deterministic_publication_period_gate','deterministic_body_availability_gate'}:
        return False  # Mechanical metadata decisions are not completed native readings.
    if choice.get('decision') not in {'eligible', 'excluded', 'duplicate'}:
        raise ValueError('Only completed native article decisions may be cached')
    evidence = proofs(run)
    if not evidence:
        return False  # No native receipt means no reusable semantic certificate.
    payload = {'choice': choice, 'run': run, 'proofs': evidence}
    path = Path(root) / (cache_key + '.json')
    if path.exists():
        # Never replace a completed reading with a later selection/timeout.
        load(root, cache_key, choice['id'])
        return True
    atomic_write_json(path, {'key': cache_key, 'payload': payload, 'payload_sha256': digest(payload),
                            'scope': 'Completed extraction only; no final selection or independent approval.'})
    return True


def load(root, cache_key, item_id):
    path = Path(root) / (cache_key + '.json')
    if not path.is_file():
        return None
    record = json.loads(path.read_text('utf-8'))
    payload = record.get('payload')
    if record.get('key') != cache_key or record.get('payload_sha256') != digest(payload):
        raise ValueError('Article reading cache checksum mismatch')
    if not payload.get('proofs') or any(not Path(p).is_file() or
            hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in payload['proofs'].items()):
        raise ValueError('Article reading native provenance changed')
    choice, run = copy.deepcopy(payload['choice']), copy.deepcopy(payload['run'])
    choice['id'] = item_id
    run.update(cache_reused=True, seconds=0, reuse_scope='Same article, context, model and reading rules; batch changed')
    return choice, run
