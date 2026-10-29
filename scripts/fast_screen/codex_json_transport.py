"""One optional host adapter; portable business rules contain no model names.

stdin: portable task JSON. stdout: result JSON only. No shell/tools in prompt.
Use a separate adapter for domestic API/CLI hosts with the same IO contract.
"""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
from portable_screen import response_schema

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--schema-file',type=Path);a=p.parse_args()
    packet=json.load(sys.stdin)
    with tempfile.TemporaryDirectory(prefix='cwh-screen-')as folder:
        root=Path(folder);schema=root/'schema.json';output=root/'response.json'
        specification=json.loads(a.schema_file.read_text(encoding='utf-8'))if a.schema_file else packet.get('output_schema')or response_schema(packet['agenda'])
        schema.write_text(json.dumps(specification,ensure_ascii=False),encoding='utf-8')
        response=subprocess.run(['codex','exec','--ephemeral','--skip-git-repo-check','-s','read-only','-m',a.model,
            '-c','model_reasoning_effort="low"','--output-schema',str(schema),'-o',str(output),'-'],
            input=json.dumps(packet,ensure_ascii=False),text=True,encoding='utf-8',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=root)
        if response.returncode:raise SystemExit(response.returncode)
        decoded=json.loads(output.read_text(encoding='utf-8'))
        print(json.dumps(decoded,ensure_ascii=False))
if __name__=='__main__':main()
