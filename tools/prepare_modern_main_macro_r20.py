#!/usr/bin/env python3
"""Export a reviewable C source for native SKTool; never rewrite the SKM.

Requires the explicitly pinned r19 native with telemetry27134. Native variable
rows, native Compile and UI placement remain the local editor's work.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from build_native_merge_r16 import macro_mirrors
from skm_alarm_catalog import validate_alarm_identities
from skm_project_header import read_project_header

ROOT = Path(__file__).resolve().parents[1]
sha = lambda data: hashlib.sha256(data).hexdigest()


def prepare(raw, expected_sha, fixture=False):
    if not re.fullmatch('[0-9a-f]{64}', expected_sha) or sha(raw) != expected_sha:
        raise ValueError('The explicitly pinned source differs')
    h = read_project_header(raw)
    if (h['model'] != 'SK-070HE' or h['resolution'] != (800.0,480.0)
            or h['pageCount'] != (16 if fixture else 17)
            or validate_alarm_identities(raw) != list(range(7))):
        raise ValueError('Use the current native3-pump r19; do not roll back newer pages')
    block = macro_mirrors(raw)[0]
    c = block[4:].decode('utf-16-be')
    required = ('LocalWord[930] = 27134u;',
                'LocalWord[960 + i] = PumpAnimTelemetry[4 + i];',
                'PumpAnimTelemetry[9] == 27133u')
    if any(s not in c for s in required):
        raise ValueError('Finish the r19 telemetry macro before adding the new Main')
    if any(s in c for s in ('MainOverview', 'MainModeData', 'MainRotationData')):
        raise ValueError('Main service already present; preserve and inspect current edits')
    for number in range(970,980):
        if (('LW'+str(number)).encode('utf-16-be') in raw
                or re.search(r'LocalWord\[\s*'+str(number)+r'\b', c)):
            raise ValueError('Reserved display word already referenced: LW'+str(number))
    newline = '\r\n' if '\r\n' in c else '\n'
    entry = re.search(r'(?m)^[ \t]*(?:static[ \t]+)?void[ \t]+Macro_main\(IN \*p\)',c)
    if not entry:
        raise ValueError('Native macro entry not found')
    definition = entry.group(0)
    hook = '    PumpAnimation(p);'
    if c.count(definition) != 1 or c.count(hook) != 1:
        raise ValueError('Reviewed macro entry/animation hook differs')
    component = (ROOT/'assets/hmi/modern-main-r20/main_overview.c').read_text()
    insertion = component.replace('\r\n','\n').replace('\n',newline) + newline
    hooked = hook + newline + '    MainOverview(p);'
    updated = c.replace(definition,insertion+definition).replace(hook,hooked)
    inverse = updated.replace(insertion,'',1).replace(hooked,hook,1)
    if inverse.encode('utf-16-be') != block[4:]:
        raise ValueError('Existing code preservation failed')
    data = updated.encode('utf-8')
    return data, dict(sourceSHA256=sha(raw), sourceMacroQStringSHA256=sha(block),
        outputUTF8SHA256=sha(data), fixtureOnly=fixture, outputKind='C for native Script Editor',
        newInputRows=[dict(name='MainModeData',type='Batch16 unsigned',address='R2300',bytes=2,readOnly=True),
                      dict(name='MainRotationData',type='Batch16 unsigned',address='R2140',bytes=40,readOnly=True)],
        nativeInputPlacement='Before existing final BootAckW; regenerate aliases natively',
        words='LW970..979; local preflight must also check indirect ranges',
        noSKMOrVariableTableWritten=True, existingUTF16SourceRecoveredByInverse=True,
        nativeCompileObserved=False, hardwareActions=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out','report'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--source-sha256',required=True)
    p.add_argument('--fixture-source',action='store_true',
                   help='Tests only:16-page ancestor, never a production base')
    a=p.parse_args()
    paths=(a.source,a.out,a.report)
    if len({x.resolve() for x in paths})!=3 or any(x.is_symlink() for x in paths) or a.out.exists() or a.report.exists():
        p.error('Distinct source and NEW regular output/report required')
    raw=a.source.read_bytes()
    data,report=prepare(raw,a.source_sha256.lower(),a.fixture_source)
    if a.source.read_bytes()!=raw:raise ValueError('Source changed')
    with a.out.open('xb') as f:f.write(data)
    with a.report.open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Exported C for native SKTool; add2 input rows and Compile:',len(data),sha(data))


if __name__=='__main__':
    main()
