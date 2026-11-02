"""Pure transcript processing and replacement functions, suitable for unit tests."""
import io
import re
from docx import Document


def read_transcript(filename, data):
    if filename.lower().endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            parts.extend(" | ".join(c.text for c in row.cells) for row in table.rows)
        return "\n".join(parts)
    if filename.lower().endswith((".txt", ".vtt")):
        return data.decode("utf-8-sig")
    raise ValueError("Only .docx, .txt and .vtt are supported")


def find_suggestions(text, nlp, allowlist):
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > 10000 and current:
            chunks.append(current)
            current = ""
        while len(line) > 10000:
            chunks.append(line[:10000]); line = line[10000:]
        current += line
    if current: chunks.append(current)
    protected = {v.casefold() for v in allowlist}
    found = {}
    for doc in nlp.pipe(chunks, batch_size=8):
        for ent in doc.ents:
            original = ent.text.strip()
            if ent.label_ not in ("PERSON", "ORG", "GPE") or len(original) < 3 or "\n" in original:
                continue
            if original.casefold() in protected: continue
            found.setdefault(original.casefold(), {"Original": original, "Category": ent.label_, "Replacement": "", "Action": "Review"})
    return sorted(found.values(), key=lambda r: (r["Category"], r["Original"].casefold()))


def apply_rules(text, rows):
    mapping = {}
    for row in rows:
        if row["Action"] != "Replace": continue
        src, dst = row["Original"].strip(), row["Replacement"].strip()
        if src.casefold() == dst.casefold(): continue
        mapping[src.casefold()] = dst
    if not mapping: return text, 0
    # Prevent substitutions that would collide with literal content already in input.
    for dst in mapping.values():
        if re.search(r"(?<!\w)" + re.escape(dst) + r"(?!\w)", text, re.IGNORECASE):
            raise ValueError(f"Placeholder already appears in source: {dst}. Use another replacement label.")
    keys = sorted(mapping, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(key) for key in keys) + r")(?!\w)", re.IGNORECASE)
    return pattern.subn(lambda m: mapping[m.group().casefold()], text)


def restore_text(text, rows):
    """Restore literal placeholders using one interview's validated rule set."""
    from session_store import validate_rules
    pairs = {r['Replacement']: r['Original'] for r in validate_rules(rows) if r['Action'] == 'Replace'}
    if not pairs:
        return text, 0
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(x) for x in sorted(pairs, key=len, reverse=True)) + r')(?!\w)')
    return pattern.subn(lambda m: pairs[m.group()], text)
