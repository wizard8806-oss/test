#!/usr/bin/env python3
"""Build a self-contained, offline operator UI preview; no SCADA/PLC access."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ui/operator-console'
DEFAULT = ROOT / 'artifacts/operator-ui-preview-01/operator-preview.html'


def build(output=DEFAULT):
    output = Path(output).resolve()
    if output.suffix.lower() != '.html' or output.is_relative_to(SOURCE.resolve()):
        raise ValueError('Use an HTML output outside the source directory')
    text = (SOURCE / 'index.template.html').read_text(encoding='utf-8')
    raw_catalog = (SOURCE / 'catalog.json').read_text(encoding='utf-8')
    json.loads(raw_catalog)
    catalog = raw_catalog.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    values = {'/*__STYLES__*/': (SOURCE/'styles.css').read_text(encoding='utf-8'),
              '__CATALOG_JSON__': catalog,
              '/*__MODEL__*/': (SOURCE/'model.js').read_text(encoding='utf-8'),
              '/*__APP__*/': (SOURCE/'app.js').read_text(encoding='utf-8')}
    for key, value in values.items():
        if text.count(key) != 1:
            raise ValueError('Missing/duplicate template slot')
        text = text.replace(key, value.replace('\r\n', '\n'), 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding='utf-8', newline='\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(build(args.out))
