#!/usr/bin/env python3
"""Build a NEW HMI-r4 with the section directory correctly relocated.

Accepts exact delivered r2 or exact rejected r3. Preserves the original,
PLC, scene counts and intended r3 UI changes. Native validation is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path

from build_three_pump_hmi_r3 import prepare as assemble_historic_r3, SOURCE_SHA
from repair_skm_section_index import read_directory, repair_rejected_r3, REJECTED_R3_SHA


def prepare(source, recipe_path):
    source = Path(source)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest == SOURCE_SHA:
        read_directory(raw)
        intermediate, ui = assemble_historic_r3(source, recipe_path)
    elif digest == REJECTED_R3_SHA:
        intermediate, ui = raw, None
    else:
        raise ValueError('Use exact delivered r2 or rejected r3; preserve other native saves')
    final, directory = repair_rejected_r3(intermediate)
    if source.read_bytes() != raw:
        raise ValueError('Source changed')
    return final, {'revision': 4, 'sourceSHA256': digest, 'sourceBytes': len(raw),
                   'candidateSHA256': hashlib.sha256(final).hexdigest(), 'candidateBytes': len(final),
                   'sourcePreserved': True, 'rejectedIntermediateWrittenToDisk': False,
                   'directoryRepair': directory, 'uiChangesFromR2': ui,
                   'retainsThreeColumnsAndIndependentTimers': True,
                   'PLCChanged': False, 'nativeSKToolOpenObserved': False, 'equipmentActions': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'recipe', 'out', 'report'):
        p.add_argument('--'+name, required=True, type=Path)
    a = p.parse_args()
    if len({v.resolve() for v in (a.source, a.recipe, a.out, a.report)}) != 4 or any(v.exists() or v.is_symlink() for v in (a.out, a.report)):
        raise ValueError('New distinct output/report paths required')
    result, report = prepare(a.source, a.recipe)
    with a.out.open('xb') as f:
        f.write(result)
    with a.report.open('x', encoding='utf8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('Built NEW HMI-r4:', len(result), 'bytes;', report['candidateSHA256'])
    print('24 section addresses + directory pointer/EOF corrected; native SKTool check remains.')


if __name__ == '__main__':
    main()
