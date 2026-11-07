#!/usr/bin/env python3
"""Build one source-locked OFFLINE pressure-protection candidate.

Known Format1 framing only. The source is the supplied, saved file, which
still contains the 32MC model. The new copy explicitly changes the two
parsed model-name fields to24MC and adds native networks. Native opening,
F8, hardware behavior, HMI editing and pump-count implementation remain
separate checks. Never connects to PLC/VFD/HMI and never overwrites input.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

from build_setpoint_feedback_pdw_01 import build, layout, word_sum
from check_native_drive_edit_02 import unpack

SOURCE_SHA = '96686b9948079d700d96e37483063b21de0cbef8f24a3e63785eed5be101abf5'
ANCHOR = '20.03 | PRESSURE_BELOW_LIMIT'
ORIGINAL = bytes.fromhex('f67f00170aca04b0c8ed')
MARKER = 27113
REGISTERS = {
    'marginConfirmed_x100': 'R2868', 'marginDraft_x100': 'R2869',
    'tripThreshold_x100': 'R2870', 'tripActive': 'R2871',
    'pressureAtTrip_x100': 'R2872', 'setpointAtTrip_x100': 'R2873',
    'configurationMarker': 'R2874', 'applyStatus': 'R2875',
    'acceptedEditsCounter': 'R2876', 'applyRequest': 'R2877',
    'runPermit': 'R2878', 'extensionVersion': 'R2879',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def words(*items):
    return struct.pack('>' + 'H' * len(items), *items)


def register(number):
    if not 0 <= number < 3840:
        raise ValueError('Unsupported R-register')
    return 0x0a00 + 2 * number


def contact(kind, number):
    if kind == 'X' and 0 <= number <= 13:
        return number
    if kind == 'Y' and 0 <= number <= 9:
        return 0x100 + number
    if kind == 'M' and 0 <= number <= 2001:
        return 0x810 + number
    raise ValueError('Unsupported contact')


def bit(operation, kind, number):
    return words({'ORG': 0x4000, 'ORGN': 0x5000, 'LD': 0x6000,
                  'AND': 0x8000, 'ANDN': 0x9000, 'OR': 0xa000}[operation]
                 + contact(kind, number))


def compare(operation, relation, left, right, immediate=True):
    base = {'ORG': 0x15, 'AND': 0x21}[operation]
    function = base + {'=': 0, '>': 1, '<': 2, '<>': 3}[relation]
    return words(0xf67f if immediate else 0xf47f, function,
                 register(left), right & 0xffff if immediate else register(right))


def move(destination, value, immediate=True):
    return words(0xf5ac if immediate else 0xf4ac,
                 value & 0xffff if immediate else register(value), register(destination))


def add(destination, left, right):
    # Existing native arithmetic uses a separate OPEN carry input.
    return words(0x7fe8, 0xf462, register(left), register(right), register(destination))


def networks():
    result = []

    def emit(name, code):
        result.append({'label': f'20.HP{len(result)+1:03d} | {name}',
                       'expectedCodeHex': code.hex()})

    unconfigured = compare('ORG', '<>', 2874, MARKER)
    for destination, value in ((2868, 200), (2871, 0), (2872, 0), (2873, 0), (2875, 0), (2876, 0)):
        emit(f'FIRST_USE_R{destination}', unconfigured + move(destination, value))
    emit('FIRST_USE_MARKER_LAST', unconfigured + move(2874, MARKER))
    boot = bit('ORG', 'M', 1924)
    emit('BOOT_DRAFT', boot + move(2869, 2868, False))
    emit('BOOT_DROP_APPLY', boot + move(2877, 0))
    emit('EXTENSION_VERSION', words(0x4fe8) + move(2879, 1))

    request = compare('ORG', '=', 2877, 1)
    stopped = (bit('ANDN', 'X', 8) + bit('ANDN', 'X', 9)
               + b''.join(bit('ANDN', 'Y', i) for i in range(1, 5))
               + bit('ANDN', 'M', 1924))
    draft_valid = compare('AND', '>', 2869, 9) + compare('AND', '<', 2869, 501)
    accept = request + stopped + draft_valid
    not_stopped = (bit('LD', 'X', 8) + bit('OR', 'X', 9)
                   + b''.join(bit('OR', 'Y', i) for i in range(1, 5))
                   + bit('OR', 'M', 1924) + words(0xe200))
    emit('EDIT_REJECT_NOT_STOP', request + not_stopped + move(2875, 3))
    emit('EDIT_REJECT_LOW', request + compare('AND', '<', 2869, 10) + move(2875, 4))
    emit('EDIT_REJECT_HIGH', request + compare('AND', '>', 2869, 500) + move(2875, 4))
    emit('EDIT_ACCEPT_MARGIN', accept + move(2868, 2869, False))
    emit('EDIT_ACCEPT_COUNTER', accept + compare('AND', '<', 2876, 32767)
         + add(2876, 2876, 2879))
    emit('EDIT_ACCEPT_STATUS', accept + move(2875, 2))
    emit('EDIT_REJECT_COMMAND', compare('ORG', '<>', 2877, 0)
         + compare('AND', '<>', 2877, 1) + move(2875, 5))
    emit('EDIT_CONSUME_REQUEST', compare('ORG', '<>', 2877, 0) + move(2877, 0))
    emit('THRESHOLD_SP_PLUS_MARGIN', words(0x4fe8) + add(2870, 110, 2868))

    valid = (bit('ORG', 'M', 102) + bit('ANDN', 'M', 1924)
             + compare('AND', '>', 110, 9) + compare('AND', '<', 110, 1200)
             + compare('AND', '=', 2874, MARKER)
             + compare('AND', '>', 2868, 9) + compare('AND', '<', 2868, 501))
    emit('AUTO_RESET_BELOW_SP', valid + compare('AND', '<', 101, 110, False) + move(2871, 0))
    emit('AUTO_RESET_AT_SP', valid + compare('AND', '=', 101, 110, False) + move(2871, 0))
    # The original fixed12bar ceiling remains an additional protective limit.
    for name, condition in (
            ('RELATIVE', compare('AND', '>', 101, 2870, False)),
            ('ABSOLUTE_12BAR', compare('AND', '>', 101, 1199))):
        trigger = valid + condition + compare('AND', '=', 2871, 0)
        emit(name + '_CAPTURE_PV', trigger + move(2872, 101, False))
        emit(name + '_CAPTURE_SP', trigger + move(2873, 110, False))
        emit(name + '_TRIP', trigger + move(2871, 1))
    emit('PERMIT_DEFAULT_OFF', words(0x4fe8) + move(2878, 0))
    emit('PERMIT_WHEN_CLEAR', valid + compare('AND', '=', 2871, 0)
         + compare('AND', '<', 101, 1200) + move(2878, 1))
    return result


def model_fields(raw):
    size = int.from_bytes(raw[0x102:0x104], 'little')
    body = raw[0x104:0x104+size]
    version, project_size, model_size, description_size = struct.unpack_from('<4H', body)
    if version != 1 or len(body) != 8 + project_size + model_size + description_size:
        raise ValueError('Unsupported project metadata')
    start = 0x104 + 8 + project_size
    model = raw[start:start+model_size]
    if raw[0xa0:0xa0+model_size] != model or raw[0xa0+model_size] != 0:
        raise ValueError('Model header/project fields disagree')
    return model.decode('ascii'), start, model_size, size


def build_candidate(source):
    raw = Path(source).read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError('Different input: use the reviewed saved upload; source preserved')
    original = layout(raw)
    obj = unpack(Path(source))
    if model_fields(raw)[0] != 'FBs-32MC':
        raise ValueError('Unexpected saved source model')
    pc = next(pc for pc, label in obj['rungs'] if label == ANCHOR)
    if original['image'][pc:pc+len(ORIGINAL)] != ORIGINAL:
        raise ValueError('Original fixed12bar safety network differs')
    used_end = int.from_bytes(original['image'][270:272], 'little')
    for number in range(2868, 2880):
        encoded = words(register(number))
        if any(original['image'][i:i+2] == encoded for i in range(512, used_end, 2)):
            raise ValueError('Candidate register has possible original code references')
    plan = networks()
    generated, _, evidence = build(raw, plan, ANCHOR)
    part = layout(generated)
    image = bytearray(part['image'])
    insert_bytes = sum(len(bytes.fromhex(r['expectedCodeHex'])) for r in plan)
    target_pc = pc + insert_bytes
    if image[target_pc:target_pc+10] != ORIGINAL:
        raise ValueError('Shifted safety anchor differs')
    # Same-size replacement: M221 reads the new, fully calculated permit.
    replacement = compare('ORG', '=', 2878, 1) + words(0xc8ed)
    if len(replacement) != len(ORIGINAL):
        raise ValueError('Safety replacement length differs')
    image[target_pc:target_pc+10] = replacement
    struct.pack_into('<H', image, 202, word_sum(image[512:int.from_bytes(image[270:272], 'little')]))
    encoded = bytes(v ^ part['key'][i % 1280] for i, v in enumerate(image))
    target = bytearray(generated)
    target[part['first']+4:part['second']] = encoded
    struct.pack_into('<H', target, part['checksum'], (sum(encoded)+sum(part['payload'])) & 65535)
    name, start, count, size = model_fields(target)
    if name != 'FBs-32MC' or count != 8:
        raise ValueError('Unexpected model field before explicit24MC candidate conversion')
    for pos in (0xa0, start):
        target[pos:pos+count] = b'FBs-24MC'
    struct.pack_into('<H', target, 0x104+size, sum(target[0x104:0x104+size]) & 65535)
    result = bytes(target)
    checked = layout(result)
    if checked['image'] != bytes(image) or model_fields(result)[0] != 'FBs-24MC':
        raise ValueError('Output image/model round-trip differs')
    # Existing program/data and all source records outside insertion/anchor
    # are independently compared by the separate validator.
    report = dict(schemaVersion=1, sourceSHA256=SOURCE_SHA, sourceBytes=len(raw),
                  sourceSavedModel='FBs-32MC', candidateModel='FBs-24MC',
                  candidateSHA256=sha(result), candidateBytes=len(result),
                  insertedNetworks=len(plan), insertedProgramBytes=insert_bytes,
                  insertionPC=pc, existingSafetyAnchor=ANCHOR,
                  replacementCodeHex=replacement.hex(), registers=REGISTERS,
                  threshold='PV > SP + margin; additional original absolute ceiling PV >=12bar',
                  reset='automatic when valid PV <= SP; hold state in deadband or on invalid measurement',
                  marginDefault=200, marginScale=0.01, marginDraftRange=[10,500],
                  marginChange='explicit applyRequest=1 in selector STOP with all RUN outputs off; command consumed',
                  HMIFileModified=False, pumpCountImplemented=False,
                  nativeOpenObserved=False, nativeF8Observed=False,
                  nativeTargetCPUConversionObserved=False, equipmentActions=0,
                  formatEvidence=evidence)
    if Path(source).read_bytes() != raw:
        raise ValueError('Source changed while building')
    return result, report, plan


def write_new(path, content):
    path = Path(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    if (args.out.exists() or args.report.exists() or
            len({p.resolve() for p in (args.source,args.out,args.report)}) != 3):
        raise ValueError('Outputs must be new, distinct files')
    result, report, plan = build_candidate(args.source)
    report['networks'] = plan
    write_new(args.out, result)
    write_new(args.report, (json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode())
    print('Built separate offline pressure candidate:', len(plan), 'native networks;', sha(result))
    print('Native F8 / HMI editing / N2/3/4 implementation remain separate, no equipment action.')


if __name__ == '__main__':
    main()
