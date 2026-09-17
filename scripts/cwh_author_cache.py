"""Hash-bound completed author checkpoints, never independent certification."""
import copy
import hashlib
import json
from pathlib import Path
from cwh_pipeline_runtime import atomic_write_json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def cache_key(packet, prompt, command, contract):
    root = Path(__file__).resolve().parent
    implementations = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
        'cwh_author_cache.py', 'cwh_author_batches.py', 'cwh_article_reading.py', 'cwh_claim_synthesis.py',
        'cwh_ranked_selection.py', 'cwh_semantic_compiler.py', 'cwh_semantic_repairs.py', 'run_cwh_compiled_worker.py')}
    return digest({'packet': packet, 'prompt': prompt, 'command': command,
                   'contract': contract, 'implementations': implementations})


def read_completed(path, key):
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text('utf-8'))
        payload = record['payload']
        if record['key'] != key or record['payload_sha256'] != digest(payload):
            return None
        result, run = copy.deepcopy(payload['result']), copy.deepcopy(payload['run'])
        if not isinstance(result.get('items'), list) or not isinstance(run, dict) or not run.get('session_id'):
            return None
        run.update(cache_reused=True, original_execution_seconds=run.get('seconds', 0), seconds=0,
            reuse_scope='Same immutable author input and rules; no new source reading or independent acceptance')
        return result, run
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def save_completed(path, key, result, run):
    payload = {'result': result, 'run': run}
    atomic_write_json(path, {'key': key, 'payload': payload, 'payload_sha256': digest(payload),
        'scope': 'Completed author transport and local repairs only; all draft and independent gates still mandatory'})
