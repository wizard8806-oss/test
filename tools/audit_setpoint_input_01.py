#!/usr/bin/env python3
"""Read-only, source-locked evidence for R2100/R2360; not a full PLC decoder.

Vendor formatter runs in isolated x86 memory, with all OS imports blocked.
Its output is evidence to review, not proof that no external/indirect writer
exists. Native MODBUS worker instructions are not fully decoded by it.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import re

from check_native_drive_edit_02 import unpack
from check_setpoint_feedback_01 import check
from render_fatek_network_01 import render, VENDOR_SHA256

SOURCE_SHA = '6aba2a67d07596e4a479c462412859565186de86b410a3cd44476a81f20ffe81'


def format_span(args):
    pc, label, code, dll = args
    try:
        return dict(pc=pc, label=label, codeHex=code.hex(),
                    mnemonics=render(code, dll))
    except Exception as exc:
        return dict(pc=pc, label=label, error=str(exc))


def audit(source, dll, workers=4):
    before = source.read_bytes()
    if hashlib.sha256(before).hexdigest() != SOURCE_SHA:
        raise ValueError('Different PLC source; review it before extending this audit')
    if hashlib.sha256(dll.read_bytes()).hexdigest() != VENDOR_SHA256:
        raise ValueError('Different vendor formatter')
    comparison = check(source)
    obj = unpack(source)
    image, rungs = obj['image'], obj['rungs']
    end = int.from_bytes(image[270:272], 'little')
    if image[end-2:end] != b'\xff\xff' or len(set(pc for pc, _ in rungs)) != len(rungs):
        raise ValueError('Unsupported network layout')
    jobs = [(pc, label, image[pc:rungs[i+1][0] if i+1 < len(rungs) else end-2], dll)
            for i, (pc, label) in enumerate(rungs)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        formatted = list(pool.map(format_span, jobs, chunksize=12))
    failures = [row for row in formatted if 'error' in row]
    refs, blocks, indirect, nearby, inventory = [], [], [], [], {}
    for row in formatted:
        text = row.get('mnemonics', '')
        if re.search(r'\bR(?:2100|2360)\b', text):
            refs.append(row)
        if re.search(r'\bR(?:209\d|210\d|2110|235\d|236\d|2370)\b', text):
            nearby.append(dict(label=row['label'], pc=row['pc'], mnemonics=text))
        for line in text.splitlines():
            if re.search(r':\s*(?:P[0-9]|V\b|Z\b)|:\s*(?:R|D|WM|WS|WX|WY)\d+\s*[+\[PVZ]', line):
                indirect.append(dict(label=row['label'], text=line.strip()))
            match = re.search(r'\b(?:FUN|ORGF|ANDF|ORF|LDF)\s+(\d+)\s*([^\r\n]*)', line)
            if match:
                key = match[1] + ' ' + match[2].strip()
                inventory[key] = inventory.get(key, 0) + 1
        for part in text.split('FUN   103 _.BT_M')[1:]:
            fields = {k: re.search(pattern, part) for k, pattern in {
                'source': r'Ts:\s+([A-Z]+)(\d+)',
                'destination': r'Td:\s+([A-Z]+)(\d+)',
                'words': r'L :\s+(\d+)'
            }.items()}
            if not all(fields.values()):
                raise ValueError('Unresolved explicit block transfer')
            blocks.append(dict(label=row['label'],
                               source=fields['source'][1]+fields['source'][2],
                               destination=fields['destination'][1]+fields['destination'][2],
                               words=int(fields['words'][1])))
    raw_refs = {reg: [i for i in range(512, end, 2) if image[i:i+2] == operand]
                for reg, operand in [('R2100', bytes.fromhex('1a68')),
                                     ('R2360', bytes.fromhex('1c70'))]}
    tables = [dict(address=address, **table) for address, table in obj['tables'].items()]
    if source.read_bytes() != before:
        raise ValueError('Source changed during audit')
    return dict(source=source.name, sourceSHA256=SOURCE_SHA,
                formatterSHA256=VENDOR_SHA256, preservedBaseline=comparison,
                networkSpansFormatted=len(formatted), formatterFailures=failures,
                programEnd=end, rawEvenOperandOffsets=raw_refs,
                directReferences=refs, nearbyReferences=nearby,
                explicitBlockTransfers=blocks, indirectOperandCandidates=indirect,
                functionInventory=inventory, masterTables=tables,
                limits=['No PLC connection/native compilation/hardware action',
                        'Saved source is not a readback of the active PLC or HMI',
                        'Formatter is not a complete decoder; section metadata and native MODBUS worker instructions need separate interpretation',
                        'No proof of absence of external/HMI/indirect writers'],
                sourceUnchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plc', required=True, type=Path)
    parser.add_argument('--vendor-dll', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 5))
    args = parser.parse_args()
    # Do not allow a report to overwrite an input, even through a symlink.
    inputs = (args.plc, args.vendor_dll)
    if (args.out.resolve() in {p.resolve() for p in inputs} or
            (args.out.exists() and any(args.out.samefile(p) for p in inputs))):
        raise ValueError('Report path must differ from both inputs')
    report = audit(args.plc, args.vendor_dll, args.workers)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"Formatted {report['networkSpansFormatted']} source spans; "
          f"failures={len(report['formatterFailures'])}; no live check.")
    if report['formatterFailures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
