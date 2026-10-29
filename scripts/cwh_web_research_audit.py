"""Count discovery, acquired text, native readings and final uses separately."""
import argparse
import json
from pathlib import Path


def summarize(bundle):
    research = (bundle.get('research_audit') or {}).get('domestic_media_research') or {}
    selected = {
        t['topic']: {e['candidate_id'] for cluster in t.get('clusters', [])
                     for e in cluster.get('evidence', [])}
        for t in (bundle.get('viewpoints') or {}).get('by_topic', [])}
    rows = []
    for topic in research.get('candidate_pool_by_topic', []):
        candidates = topic.get('candidates', [])
        web = [c for c in candidates if c.get('discovery_origin') in {
            'fixed_registry_web', 'open_web', 'public_platform_web'}]
        raw = [c for c in candidates if c.get('discovery_origin') == 'raw_monitoring']
        used = selected.get(topic['topic'], set())
        # One article may nominate multiple speakers/claims. URL counts describe
        # reading coverage; claim counts describe final use, not unique people.
        reviewed = {c['url'] for c in web if c.get('review_scope') in {
            'full_text_semantic_review', 'full_text_review_with_unverified_formal_metadata'}}
        rows.append({
            'topic': topic['topic'],
            'completed_search_queries': sum(q.get('status') == 'completed' and q.get('route') in {
                'stable_registry','open_web','public_platform'}
                for r in topic.get('saturation', {}).get('rounds', []) for q in r.get('executions', [])),
            'adaptive_web_allocation': topic.get('adaptive_web_allocation'),
            'discovered_web_urls': len({c['url'] for c in web}),
            'web_text_acquired': (topic.get('reading_scope') or {}).get('web_full_text_count', 0),
            'web_native_read_urls': len(reviewed),
            'web_reading_deferred': len((topic.get('reading_scope') or {}).get('semantic_reading_deferred_item_ids', [])),
            'web_nominated_claims': sum(c.get('decision') == 'eligible' for c in web),
            'web_final_body_claims': sum(c['candidate_id'] in used for c in web),
            'raw_final_body_claims': sum(c['candidate_id'] in used for c in raw),
        })
    return {'topics': rows, 'totals': {
        key: sum(row[key] for row in rows) for key in (
            'web_text_acquired', 'web_native_read_urls', 'web_reading_deferred',
            'web_nominated_claims', 'web_final_body_claims', 'raw_final_body_claims')},
        'scope': 'Per-topic URL counts may overlap; claim counts are not people. '
                 'Final body use is counted from actual evidence IDs, not stale draft formal_use labels. '
                 'Zero selected web claims never proves that no useful web evidence exists.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-dir', required=True)
    parser.add_argument('--output', default='')
    args = parser.parse_args()
    job = Path(args.job_dir)
    from cwh_remaining_research import effective_bundle
    bundle_path = effective_bundle(job)
    if not bundle_path.is_file():
        parser.error('Verified bundle unavailable; cannot certify final body use')
    result = summarize(json.loads(bundle_path.read_text('utf-8-sig')))
    result['bundle_path'] = str(bundle_path.resolve())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
