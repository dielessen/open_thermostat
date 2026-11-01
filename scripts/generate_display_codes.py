"""Boiler display codes in words, from the boiler profiles; presentation only, never control evidence.

Source of truth: docs/modern-thermostat/boiler-profiles/
  ems-display-codes.json   the generic EMS table (display code + cause number), the shared
                           severity/advice texts and the registry of the manufacturer documents;
  <model>.json             a boiler profile with a "display_codes" block: that family's own table,
                           the boiler-model selections (public/boilers/catalog-v1.json) it covers.
                           A model row without "code" is a cause-number-only row: the manual lists
                           that number without a display code (an operating message shown as "-",
                           or a family that shows the number only); it matches any display code.
Lookup: (code, cause), then (any code, cause) in a model table, then (code, no cause).
Generated (never edit by hand; --check fails on drift):
  ha/config/custom_components/open_thermostat/display_code_table.py   English, Dutch and Polish
  data/html/display-codes.js (between the GENERATED markers)          English and Dutch (the E32 UI)
"""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / 'docs/modern-thermostat/boiler-profiles'
GENERIC = PROFILES / 'ems-display-codes.json'
CATALOG = ROOT / 'public/boilers/catalog-v1.json'
HA_TABLE = ROOT / 'ha/config/custom_components/open_thermostat/display_code_table.py'
JS = ROOT / 'data/html/display-codes.js'
START = '    // BEGIN GENERATED DISPLAY CODES\n'
END = '    // END GENERATED DISPLAY CODES\n'
LANGUAGES = ('en', 'nl', 'pl')
WEB_LANGUAGES = ('en', 'nl')  # the E32 pages are English and Dutch
SEVERITIES = ('normal', 'waiting', 'service', 'blocking', 'locking', 'fault', 'unknown')
CODE = re.compile(r'[-=0-9A-Za-z]{1,2}')
TEXT_MAX = 140
CAUSE_MIN, CAUSE_MAX = 100, 9999  # three-digit cause numbers; four-digit fault codes (EMS+)
ADVICE_MAX = 200


def require(condition, message):
    if not condition:
        raise ValueError(message)


def texts(value, where, limit=TEXT_MAX):
    require(type(value) is dict and set(value) == set(LANGUAGES), f'{where}: needs exactly {LANGUAGES}')
    for language, text in value.items():
        require(type(text) is str and 0 < len(text) <= limit and text == text.strip() and '\n' not in text,
                f'{where}.{language}: one plain line of 1-{limit} characters')
    return tuple(value[language] for language in LANGUAGES)


def rows(codes, where, advice, sources, generic):
    """{(code, cause or None): (severity, advice id or None, texts)} of one table, validated."""
    require(type(codes) is list and codes, f'{where}: no codes')
    table = {}
    for i, row in enumerate(codes):
        at = f'{where}[{i}]'
        allowed = {'code', 'cause', 'severity', 'advice', 'text', 'sources' if generic else 'pages'}
        require(type(row) is dict and set(row) <= allowed and {'severity', 'text'} <= set(row), f'{at}: keys')
        # A model table may list a cause number without a display code (any code with that number).
        require('code' in row or (not generic and 'cause' in row), f'{at}: keys')
        code, cause = row.get('code'), row.get('cause')
        require(code is None or (type(code) is str and CODE.fullmatch(code)), f'{at}: display code {code!r}')
        require(cause is None or (type(cause) is int and CAUSE_MIN <= cause <= CAUSE_MAX), f'{at}: cause number {cause!r}')
        require(code is not None or cause is not None, f'{at}: a row without a display code needs a cause number')
        require(row['severity'] in SEVERITIES[:-1], f'{at}: severity {row["severity"]!r}')
        require(row.get('advice') is None or row['advice'] in advice, f'{at}: advice {row.get("advice")!r}')
        key = (code, cause)
        require(key not in table, f'{at}: duplicate {code} {cause}')
        if generic:
            cited = row.get('sources')
            if cause is None:
                require(cited == 'all_reviewed', f'{at}: a code-only row must hold for all reviewed documents')
            else:
                require(type(cited) is list and cited, f'{at}: no source')
                for ref in cited:
                    require(type(ref) is dict and set(ref) == {'source', 'pages'} and ref['source'] in sources
                            and type(ref['pages']) is list and ref['pages']
                            and all(type(p) is int and p > 0 for p in ref['pages']), f'{at}: source {ref!r}')
        else:
            require(type(row.get('pages')) is str and row['pages'], f'{at}: pages in the source document')
        table[key] = (row['severity'], row.get('advice'), texts(row['text'], at + '.text'))
    return table


def load():
    generic = json.loads(GENERIC.read_text(encoding='utf-8'))
    require(generic.get('schema') == 1 and generic.get('id') == 'ems-generic', 'generic table schema/id')
    sources = generic['sources']
    require(type(sources) is dict and sources, 'source registry')
    for name, source in sources.items():
        require(re.fullmatch(r'[a-z0-9.-]{3,63}', name), f'source id {name!r}')
        for key in ('publisher', 'title', 'document', 'edition', 'language', 'models', 'sections', 'url', 'host', 'sha256'):
            require(source.get(key), f'source {name}: {key}')
        require(source['url'].startswith('https://'), f'source {name}: https URL')
        require(re.fullmatch('[0-9a-f]{64}', source['sha256']), f'source {name}: sha256 of the reviewed PDF')
    severities = {key: texts(value, f'severity {key}') for key, value in generic['severities'].items()}
    require(tuple(severities) == SEVERITIES, f'severities must be exactly {SEVERITIES}')
    advice = {key: texts(value, f'advice {key}', ADVICE_MAX) for key, value in generic['advice'].items()}
    require(advice and all(re.fullmatch('[a-z_]{2,20}', key) for key in advice), 'advice ids')
    unknown = texts(generic['unknown'], 'unknown', ADVICE_MAX)
    tables = {'ems-generic': rows(generic['codes'], 'ems-generic', advice, sources, True)}
    fallback = {'ems-generic': None}
    models = {}
    catalog_models = json.loads(CATALOG.read_text())['models']
    catalog = {m['id'] for m in catalog_models}
    family_source = {}
    for path in sorted(PROFILES.glob('*.json')):
        if path == GENERIC:
            continue
        profile = json.loads(path.read_text(encoding='utf-8'))
        block = profile.get('display_codes')
        if block is None:
            continue
        name = profile['id']
        require(path.stem == name and name not in tables, f'{path.name}: profile id')
        require(block.get('schema') == 1, f'{name}: display_codes schema')
        require(block.get('source') in sources, f'{name}: source {block.get("source")!r}')
        require(block.get('fallback') in (None, 'ems-generic'), f'{name}: fallback')
        require(type(block.get('cause_numbers')) is bool and block.get('scope') and block.get('verified'), f'{name}: scope')
        tables[name] = rows(block['codes'], name, advice, sources, False)
        if not block['cause_numbers']:
            require(all(cause is None for _, cause in tables[name]), f'{name}: no cause numbers in this family')
        fallback[name] = block['fallback']
        ids = block.get('catalog_ids')
        require(type(ids) is list and ids, f'{name}: catalog_ids')
        for model in ids:
            require(model in catalog, f'{name}: {model} is not a boiler-model selection')
            require(model not in models, f'{model}: in two display-code profiles')
            models[model] = name
            family_source[model] = block['source']
    # A selection added to the catalogue for a family manual is covered by that manual's table.
    for model in catalog_models:
        if model.get('source') == 'manufacturer-document':
            require(family_source.get(model['id']) == model.get('source_document'),
                    f'{model["id"]}: catalogued for {model.get("source_document")!r} but not covered by its table')
    used ={row[1] for table in tables.values() for row in table.values()} - {None}
    require(used == set(advice), f'unused advice texts: {sorted(set(advice) - used)}')
    return dict(severities=severities, advice=advice, unknown=unknown, tables=tables, fallback=fallback,
                models=models, sources=sources)


def python_module(data):
    def table(rows_):
        lines = []
        for (code, cause), (severity, advice, text) in rows_.items():
            lines.append(f'        ({code!r}, {cause!r}): ({severity!r}, {advice!r}, {text!r}),')
        return '\n'.join(lines)
    out = ['"""Boiler display codes in words (English, Dutch, Polish).',
           '',
           'Generated by scripts/generate_display_codes.py from docs/modern-thermostat/boiler-profiles;',
           'edit the profiles, never this file. Presentation only: never control evidence.',
           '"""',
           '',
           f'LANGUAGES = {LANGUAGES!r}',
           '# severity: (texts per language)',
           'SEVERITIES = {']
    out += [f'    {key!r}: {value!r},' for key, value in data['severities'].items()]
    out += ['}', '# advice id: (texts per language)', 'ADVICE = {']
    out += [f'    {key!r}: {value!r},' for key, value in data['advice'].items()]
    out += ['}', f'UNKNOWN = {data["unknown"]!r}', 'GENERIC = "ems-generic"',
            '# table: {(display code or None for any, cause number or None for any): (severity, advice id or None, texts)}',
            'TABLES = {']
    for name, rows_ in data['tables'].items():
        out += [f'    {name!r}: {{', table(rows_), '    },']
    out += ['}', '# table: the table to use for a code it does not list (None: unknown, never guessed)',
            f'FALLBACK = {data["fallback"]!r}',
            '# boiler-model selection (E32 /config/boiler-display, public/boilers/catalog-v1.json): table',
            f'MODELS = {data["models"]!r}', '']
    return '\n'.join(out)


def javascript(data):
    pick = [LANGUAGES.index(language) for language in WEB_LANGUAGES]
    def words(value):
        return [value[i] for i in pick]
    # One pool of meanings ("x"): the families share most texts, so each row holds an index.
    pool, index = [], {}
    def text_id(text):
        key = tuple(words(text))
        if key not in index:
            index[key] = len(pool)
            pool.append(list(key))
        return index[key]
    compact = {
        's': {key: words(value) for key, value in data['severities'].items()},
        'a': {key: words(value) for key, value in data['advice'].items()},
        'u': words(data['unknown']),
        't': {name: {'f': data['fallback'][name],
                     'c': {(code or '*') + ('' if cause is None else ' ' + str(cause)): [severity, advice, text_id(text)]
                           for (code, cause), (severity, advice, text) in rows_.items()}}
              for name, rows_ in data['tables'].items()},
        'm': data['models'],
    }
    compact['x'] = pool
    return '    const data = ' + json.dumps(compact, ensure_ascii=False, separators=(',', ':')) + ';\n'


def generate(check=False):
    data = load()
    outputs = {HA_TABLE: python_module(data)}
    source = JS.read_text(encoding='utf-8')
    require(source.count(START) == source.count(END) == 1, 'display-codes.js markers')
    before, tail = source.split(START)
    _, after = tail.split(END)
    outputs[JS] = before + START + javascript(data) + END + after
    for path, text in outputs.items():
        if check:
            require(path.read_text(encoding='utf-8') == text, f'Regenerate display codes: {path.relative_to(ROOT)}')
        else:
            path.write_bytes(text.encode('utf-8'))
    counts = {name: len(rows_) for name, rows_ in data['tables'].items()}
    print(f'PASS display codes: {counts}, {len(data["models"])} model selections, {len(data["sources"])} documents')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
