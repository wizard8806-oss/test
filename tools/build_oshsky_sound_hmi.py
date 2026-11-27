"""Update only the four-pump buzzer output and add local first-rearm evidence.

The body is read from the exact r3e. Native variable definitions, guards, mask,
generation, service token and every motor output stay under their original owners.
"""
import hashlib
import re
import struct
from pathlib import Path

from build_native_merge_r16 import macro_mirrors
from prepare_telemetry_hmi_r19 import replace_records

SOURCE_SHA = '4ad1a6f36348fdc66a2d2e25af085cb0e4184cb8fb098e83c96d32bb6f4d8563'


def replace_once(body, old, new):
    if body.count(old) != 1:
        raise ValueError('Unrecognized native sound source')
    return body.replace(old, new)


def patch_macro(body):
    helper = (Path(__file__).resolve().parents[1] / 'assets/hmi/oshsky-cascade-r3/oshsky_sound_evidence.c').read_text('utf8')
    body = replace_once(body, 'static unsigned int alarm_phase = 0u;', '')
    body = replace_once(body, 'void Macro_main(IN *p)', helper + '\nvoid Macro_main(IN *p)')
    body = replace_once(body, '    int cl50_new_generation;', '''    int cl50_new_generation;
    unsigned short old_generation = cl50_previous_generation;
    unsigned int old_mask = alarm_previous;
    int was_muted = alarm_muted;''')
    body = replace_once(body, '    /* Use the controlled buzzer, not the general alarm-sound toggle. */\n    LocalBit[60117] = 0;','')
    begin = body.index('    /* Global period250ms: 500ms ON, 500ms OFF. */')
    end = body.index('    LocalBit[803] = 1;', begin)
    if body[begin:end].count('LocalBit[60185]') != 1:
        raise ValueError('Unrecognized legacy output')
    body=body[:begin]+'''    /* SKTool7.1 local register LB60117: alarm sound enable. */
    LocalBit[60117] = LocalBit[802];
    OshSoundEvidence(p, old_mask, current, rising, old_generation, cl50_generation,
        cl50_new_generation, request, was_muted, alarm_muted);
'''+body[end:]
    return body


def patch(source):
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:
        raise ValueError('Expected saved four-pump r3e')
    mirrors=macro_mirrors(data)
    assert len(mirrors)==2 and mirrors[0]==mirrors[1] and data.count(mirrors[0])==2
    old=mirrors[0][4:].decode('utf-16-be')
    source_c=old.replace('\r','')
    for address in range(54160,54211):
        if ('LW'+str(address)).encode('utf-16-be') in data or re.search(r'\b'+str(address)+r'\b',source_c):
            raise ValueError('Occupied diagnostic word '+str(address))
    result=patch_macro(source_c)
    native=result.replace('\n','\r\n').encode('utf-16-be')
    new=struct.pack('>I',len(native))+native
    updated=replace_records(data,[(m.start(),mirrors[0],new)
        for m in re.finditer(re.escape(mirrors[0]),data)])
    return updated,result
