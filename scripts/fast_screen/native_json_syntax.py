"""Strict JSON intake with a narrowly bounded, lossless EOF container repair."""
import hashlib,json,re
from pathlib import Path
from portable_screen import load_response as strict_load,unique_object,save,digest

def close_completed_root(text):
    try:return json.loads(text,object_pairs_hook=unique_object),''
    except json.JSONDecodeError as original:
        if original.pos!=len(text)or not text or text[-1]not in '}]':raise
        stack=[];quoted=False;escaped=False
        for c in text:
            if quoted:
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c=='"':quoted=False
            elif c=='"':quoted=True
            elif c in '{[':stack.append(c)
            elif c in '}]':
                if not stack or(stack[-1],c)not in [('{','}'),('[',']')]:raise original
                stack.pop()
        # Only close the root object or its items array. Never complete a
        # string, article, claim, field, comma or missing semantic value.
        if quoted or stack not in [['{'],['{','[']]:raise original
        suffix=''.join('}'if c=='{'else']'for c in reversed(stack))
        value=json.loads(text+suffix,object_pairs_hook=unique_object)
        if not isinstance(value,dict)or set(value)!={'items'}or not isinstance(value['items'],list):raise original
        return value,suffix

def load_response(path):
    try:return strict_load(path)
    except json.JSONDecodeError:
        raw=Path(path).read_text(encoding='utf-8-sig').strip();notes=[]
        wrapper=re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```',raw)
        if wrapper:raw=wrapper.group(1);notes.append('single_markdown_fence_removed')
        value,suffix=close_completed_root(raw)
        if not suffix:raise ValueError('No permitted EOF root repair')
        save(Path(path).with_suffix('.syntax_repair.json'),{'raw_file_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'added_suffix':suffix,'parsed_result_hash':digest(value),'semantic_values_rewritten':False,
            'missing_articles_filled':False,'scope':'Completed items only; expected-ID coverage must still be validated'})
        return value,notes+['completed_root_container_closures:'+suffix]
