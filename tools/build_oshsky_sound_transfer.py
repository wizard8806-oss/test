"""Build Oshsky r3h from the saved r3g using one native, triggered R2553 transfer."""
import argparse
import hashlib
import re
from pathlib import Path

from build_native_merge_r16 import macro_mirrors
from prepare_telemetry_hmi_r19 import replace_records
from skm_alarm_catalog import qs

BASE_SHA = '0ec7b21fd84e21781965a35e89a7bb1f78a05aa639e6971238329fc0000543bc'
SERVICE = Path(__file__).resolve().parents[1] / 'assets/hmi/oshsky-cascade-r3/oshsky_service_word.c'


def address(kind, number):
    descriptor, word = {
        'R': (bytes((1, 6, 1)), 1),
        'LW': (bytes((0, 1, 100)), 1),
        'LB': (bytes((0, 0, 100)), 0),
    }[kind]
    return qs(f'{kind}{number}') + descriptor + qs(str(number)) + qs(kind) + bytes((word,))


def transfer_record():
    # From a native Data Transfer Save in SKTOOL 7.1.0.80. One triggered WORD,
    # automatic trigger reset, one WORD of payload, notification disabled.
    native_options = bytes.fromhex('01 01 01 02 01 01')
    native_notification = bytes.fromhex(
        '00 00 00 02 00 00 00 16 00 30 00 01 00 01 00 30 00 01 00 01 '
        '00 30 00 01 00 01 00 30 00 01 00 00 00 02 00 30')
    return (native_options + address('LW', 54210) + address('R', 2553)
            + address('LB', 54210) + native_notification)


def build(source):
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('Expected saved Oshsky r3g')
    primary, mirror = macro_mirrors(raw)
    assert primary == mirror
    c = primary[4:].decode('utf-16-be').replace('\r', '')
    if any(qs(a) in raw for a in ('LB54210', 'LW54210', 'LW54211')) or re.search(r'\b5421[01]\b', c):
        raise ValueError('Existing HMI address overlaps the native transfer')
    helper = SERVICE.read_text(encoding='utf-8').rstrip()
    site = 'static void OshSoundEvidence('
    assert c.count(site) == 1
    c = c.replace(site, helper + '\n\n' + site)
    pending = '    if (cl50_pending_generation != 0u && LocalBit[60107]'
    assert c.count(pending) == 1
    c = c.replace(pending, '    if (!LocalBit[60107] || MapVersion != 32u) {\n'
                  '        cl50_pending_generation = 0u;\n    }\n' + pending)
    call = '    OshSoundEvidence(p, old_mask'
    assert c.count(call) == 1
    c = c.replace(call, '    OshServiceTransport(p, cl50_generation, alarm_muted);\n' + call)
    c = c.replace('W, FATEK R2553.', 'W, local LW54211. Native triggered transfer sends the existing service to R2553.')
    c = c.replace('Configure_BootAck_as_16_Bit_Unsigned_Int_W_R2553',
                  'Configure_BootAck_as_16_Bit_Unsigned_Int_W_LW54211')
    changes = [(m.start(), primary, qs(c.replace('\n', '\r\n')))
               for m in re.finditer(re.escape(primary), raw)]
    assert len(changes) == 2
    definition = qs('BootAck') + qs('16-Bit Unsigned Int') + qs('') + qs('W')
    assert raw.count(definition) == 1
    start = raw.index(definition) + len(definition)
    assert raw.startswith(address('R', 2553), start)
    changes.append((start, address('R', 2553), address('LW', 54211)))
    # The empty transfer list is located in the pinned r3g section.
    at = 4063894
    assert raw[at-19:at+14] == bytes.fromhex(
        '64 00 00 00 02 00 30 00 00 00 04 00 4c 00 42 00 00 00 00 '
        '00 00 00 00 01 00 19 00 00 00 01 01 00 00')
    changes.append((at, b'\x00', transfer_record()))
    for old, new in [('R3g DIAG 27.11.2026', 'R3h DIAG 27.11.2026'),
                     ('R3g · живые данные', 'R3h · живые данные'), ('R3g', 'R3h')]:
        for found in re.finditer(re.escape(qs(old)), raw):
            changes.append((found.start(), qs(old), qs(new)))
    result = replace_records(raw, changes)
    assert result.count(transfer_record()) == 1
    assert result.count(definition + address('LW', 54211)) == 1
    assert result.count(address('R', 2553)) == 1
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = build(args.source)
    with args.output.open('xb') as output:
        output.write(data)
