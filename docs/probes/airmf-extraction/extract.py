"""AI RMF extraction, proven 2026-09-20. Run: python extract.py

SOURCE is AIRC (airc.nist.gov), NOT CPRT. CPRT does not carry the AI RMF
core; that was resolved by checking, and a resumed session should not
re-litigate it.

The row pattern keys on the IDENTIFIER SHAPE, not on a CSS class. Class
names are the site's presentation and change without notice; `Govern 1.1`
is the document's own grammar. A parser keyed on the class would fail
silently into zero rows on a restyle -- the failure mode this project has
catalogued repeatedly.
"""
import json, pathlib, re, sys

ROW = re.compile(
    r'<span class="[^"]*">\s*'
    r'(?P<id>(?:Govern|Map|Measure|Manage) \d+(?:\.\d+)?)\s*'
    r'</span>\s*:\s*(?P<text>.*?)</th>', re.S)

TAGS = re.compile(r'<[^>]+>')

def clean(raw: str) -> str:
    text = TAGS.sub(' ', raw)
    text = (text.replace('&amp;', '&').replace('&nbsp;', ' ')
                .replace('&lt;', '<').replace('&gt;', '>')
                .replace('&#39;', "'").replace('&quot;', '"'))
    return re.sub(r'\s+', ' ', text).strip()

def main() -> int:
    html = pathlib.Path(__file__).with_name('source-airc.html').read_text(
        encoding='utf-8', errors='replace')
    rows = [{'id': m.group('id'), 'text': clean(m.group('text'))}
            for m in ROW.finditer(html)]
    cats = [r for r in rows if '.' not in r['id']]
    subs = [r for r in rows if '.' in r['id']]

    # Every assertion the extraction was accepted on, restated as a check
    # rather than a remembered number.
    empty = [r['id'] for r in rows if not r['text']]
    assert not empty, f'empty text: {empty}'
    cat_ids = {c['id'] for c in cats}
    orphans = sorted({s['id'].split('.')[0] for s in subs} - cat_ids)
    assert not orphans, f'subcategory with no parent category: {orphans}'
    for fn in ('Govern', 'Map', 'Measure', 'Manage'):
        nums = sorted(int(c['id'].split()[1]) for c in cats
                      if c['id'].startswith(fn))
        assert nums == list(range(1, len(nums) + 1)), f'{fn} not contiguous: {nums}'

    pathlib.Path(__file__).with_name('rows.json').write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'{len(cats)} categories / {len(subs)} subcategories, all checks passed')
    print('  per function:', {fn: sum(1 for c in cats if c["id"].startswith(fn))
                              for fn in ('Govern', 'Map', 'Measure', 'Manage')})
    return 0

if __name__ == '__main__':
    sys.exit(main())
