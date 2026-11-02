"""Local per-interview rule files. No cloud storage or shared replacement dictionary."""
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'private_sessions'


def list_sessions():
    ROOT.mkdir(parents=True, exist_ok=True)
    output = []
    for file in ROOT.glob('*/rules.json'):
        try:
            data = json.loads(file.read_text(encoding='utf-8'))
            if data.get('id') == file.parent.name:
                output.append({'id':data['id'], 'title':data.get('title','Untitled')})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(output, key=lambda x: x['title'].casefold())


def new_session(title):
    if not title.strip():
        raise ValueError('Enter an interview name')
    sid = 'INT-' + uuid.uuid4().hex[:12].upper()
    save_session(sid, title.strip(), [])
    return sid


def save_session(sid, title, rules):
    if not re.fullmatch(r'INT-[A-F0-9]{12}', sid):
        raise ValueError('Invalid interview ID')
    folder = ROOT / sid
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'rules.json'
    temporary = folder / 'rules.json.tmp'
    temporary.write_text(json.dumps({'id':sid,'title':title,'rules':rules},indent=2,ensure_ascii=False), encoding='utf-8')
    temporary.replace(target)


def load_session(sid):
    if not re.fullmatch(r'INT-[A-F0-9]{12}', sid):
        raise ValueError('Invalid interview ID')
    data = json.loads((ROOT / sid / 'rules.json').read_text(encoding='utf-8'))
    if data.get('id') != sid:
        raise ValueError('Session ID mismatch')
    return data


def validate_rules(rows):
    valid = []
    seen = set()
    for row in rows:
        original = str(row.get('Original') or '').strip()
        if not original:
            continue
        folded = original.casefold()
        if folded in seen:
            raise ValueError(f'Duplicate original term: {original}')
        seen.add(folded)
        action = str(row.get('Action') or 'Review').strip()
        if action not in {'Review','Keep','Replace'}:
            raise ValueError(f'Invalid action for {original}')
        replacement = str(row.get('Replacement') or '').strip()
        if action == 'Replace' and not replacement:
            raise ValueError(f'Missing replacement for {original}')
        if action == 'Replace' and replacement.casefold() == original.casefold():
            raise ValueError(f'Replacement must differ for {original}')
        valid.append({'Original':original,'Category':str(row.get('Category') or 'Custom').strip(), 'Replacement':replacement, 'Action':action})
    # Reversal requires unique placeholders, including no overlap with other originals.
    repl = [r for r in valid if r['Action']=='Replace']
    placeholders = [r['Replacement'].casefold() for r in repl]
    if len(placeholders) != len(set(placeholders)):
        raise ValueError('Each replacement must be unique for safe restoration. Use Agency_A_FULL and Agency_A_ACRONYM instead.')
    originals = {r['Original'].casefold() for r in valid}
    if set(placeholders) & originals:
        raise ValueError('A placeholder conflicts with an original term in the dictionary.')
    return valid
