"""One entry for the compact, portable independent sample-screening profile."""
import argparse,json,subprocess,sys
from pathlib import Path
from portable_screen import save,digest

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--workbook',type=Path);g.add_argument('--records',type=Path)
    p.add_argument('--agenda',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rules',type=Path,default=HERE/'collection_frozen_rules.json')
    p.add_argument('--compact-profile',type=Path,default=HERE/'compact_profile_manifest.json')
    p.add_argument('--model',default='gpt-6.1-sol');p.add_argument('--host',choices=['codex','workbuddy'],default='codex');p.add_argument('--host-command-json')
    p.add_argument('--budget-seconds',type=int,default=480);p.add_argument('--max-batch-chars',type=int,default=90000)
    p.add_argument('--output-contract',choices=['compact','canonical'],default='compact')
    p.add_argument('--max-body-chars',type=int,default=450000);p.add_argument('--reading-cost-power',type=float,default=.35)
    p.add_argument('--exploration-cost-power',type=float,default=0);p.add_argument('--max-batch-articles',type=int,default=0)
    p.add_argument('--max-selected-articles',type=int,default=99)
    p.add_argument('--review-all',action='store_true',help='Diagnostic all-review profile; requires its own core frozen rules')
    p.add_argument('--run',action='store_true');a=p.parse_args()
    out=a.out.resolve()
    if out.exists():raise ValueError('Fresh output directory required')
    if a.host=='workbuddy':
        if a.host_command_json:raise ValueError('Choose --host workbuddy or a custom host command')
        a.host_command_json=json.dumps([sys.executable,str(HERE/'workbuddy_screen_host.py'),'--model',a.model,'--audit-dir',str(out/'host_audit')])
    bridge=[sys.executable,str(HERE/'compact_screen_transport.py'),'--model',a.model,
            '--audit-dir',str(out/'transport_audit'),'--profile-manifest',str(a.compact_profile.resolve())]
    if a.output_contract=='canonical':
        if not a.host_command_json:raise ValueError('Readable transport requires an explicit configured host')
        bridge=[sys.executable,str(HERE/'canonical_screen_transport.py'),'--audit-dir',str(out/'transport_audit'),
                '--profile-manifest',str(a.compact_profile.resolve())]
    if a.host_command_json:bridge+=['--host-command-json',a.host_command_json]
    argv=[sys.executable,str(HERE/('run_optimized_screen.py'if a.review_all else'collect_samples.py')),'--agenda',str(a.agenda.resolve()),'--out',str(out),
          '--frozen-rules',str(a.rules.resolve()),'--budget-seconds',str(a.budget_seconds),
          '--model',a.model,'--command-json',json.dumps(bridge)]
    if not a.review_all:argv+=['--max-batch-chars',str(a.max_batch_chars),'--max-body-chars',str(a.max_body_chars),
        '--reading-cost-power',str(a.reading_cost_power),'--exploration-cost-power',str(a.exploration_cost_power),
        '--max-batch-articles',str(a.max_batch_articles),'--max-selected-articles',str(a.max_selected_articles)]
    argv+=['--workbook',str(a.workbook.resolve())]if a.workbook else['--records',str(a.records.resolve())]
    if a.run:argv.append('--run')
    save(out.with_suffix('.launch.json'),{'profile':'v8_compact_all_review'if a.review_all else'v8_compact_collection','requested_model_label':a.model,
         'custom_host_argv_hash':digest(a.host_command_json)if a.host_command_json else None,
         'compact_profile':str(a.compact_profile.resolve()),'business_rules':str(a.rules.resolve()),
         'budget_seconds':a.budget_seconds,'scope':'Independent screening; no public-web verification or full-report timing certification.'})
    raise SystemExit(subprocess.run(argv).returncode)

if __name__=='__main__':main()
