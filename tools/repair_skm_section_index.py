#!/usr/bin/env python3
"""Check/relocate the reviewed SKTool 7.1 trailing section directory.

The final24 big-endian 64-bit directory entries include EOF. The preceding
metadata stores a back-pointer to the directory immediately before section0.
This format is observed in two independent source SKM files, not inferred
from arbitrary integers. Only the exact rejected r3 may be repaired here.
"""
import hashlib
import struct

ENTRY_COUNT = 24
DIRECTORY_BYTES = 4 + ENTRY_COUNT * 8
REJECTED_R3_SHA = 'aaed37837dc96595cfcbe447057b55c1bc67bc15801d4055197937e39bd90b58'
sha = lambda data: hashlib.sha256(data).hexdigest()


def read_directory(raw, require_current=True):
    at = len(raw) - DIRECTORY_BYTES
    if at < 0 or struct.unpack_from('>I', raw, at)[0] != ENTRY_COUNT:
        raise ValueError('SKM section directory count differs')
    offsets = list(struct.unpack_from('>24Q', raw, at+4))
    if offsets != sorted(offsets) or not 8 <= offsets[0] < offsets[-2] < offsets[-1]:
        raise ValueError('SKM section directory order differs')
    delta = len(raw) - offsets[-1]
    locator = offsets[0] + delta - 8
    old_at = at - delta
    if not 0 <= locator <= at-8 or struct.unpack_from('>Q', raw, locator)[0] != old_at:
        raise ValueError('SKM directory back-pointer does not resolve')
    if offsets[-2] + delta != at-16:
        raise ValueError('SKM trailing directory boundary differs')
    if require_current and delta:
        raise ValueError('Stale SKM absolute offsets/EOF: directory EOF=%d, actual=%d' % (offsets[-1], len(raw)))
    return {'offset': at, 'locatorOffset': locator, 'entries': offsets, 'delta': delta}


def repair_rejected_r3(raw):
    if len(raw) != 1322197 or sha(raw) != REJECTED_R3_SHA:
        raise ValueError('Repair requires the exact rejected r3; other files preserved')
    directory = read_directory(raw, require_current=False)
    if directory['delta'] != 414:
        raise ValueError('Unexpected rejected-r3 relocation delta')
    result = bytearray(raw)
    writes = [(directory['locatorOffset'], directory['offset'])]
    writes += [(directory['offset']+4+8*i, value+directory['delta'])
               for i, value in enumerate(directory['entries'])]
    changes = []
    for at, value in writes:
        old = bytes(result[at:at+8])
        new = struct.pack('>Q', value)
        result[at:at+8] = new
        changes.append({'offset': at, 'old': old.hex(), 'new': new.hex()})
    final = bytes(result)
    read_directory(final)
    return final, {'relocatedEntries': ENTRY_COUNT, 'relocationDelta': directory['delta'],
                   'backPointerRelocated': True, 'changes': changes,
                   'sourceSHA256': REJECTED_R3_SHA, 'candidateSHA256': sha(final),
                   'candidateBytes': len(final), 'nativeSKToolOpenObserved': False}
