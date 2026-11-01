#!/usr/bin/env python3
"""Check one OPC file flag against the original loader in isolated x86 memory.

String cleanup/read and scalar stream reads are adapters. Native version
branches and destination addresses execute; no GUI/compiler/OPC/OS import does.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from _runtime import SCADA_SEED
from verify_scada_variable_metadata_native import EDITOR_SHA, NativeBody

PROFILE_SHA = 'efd91d5df93359c3320c72e185941247688b9ffad8fe3a5af196a9ed675a15fc'
WRITE_PROFILE_SHA = 'c0662185786f2204479c9ad90d2dcc2ed0dbb79d9d532942f1841f650ef498b6'


class NativeServer(NativeBody):
    def hook(self, u, ip, size, user):
        r = self.reg
        if ip == 0x11e049c:
            u.emu_stop()
            return
        if ip == 0x40c690:  # String cleanup; empty mock fields.
            self.ret()
            return
        reads = {0x8b0e60: ('I', 4), 0x8b21b0: ('B', 1), 0x8b1e30: ('B', 1)}
        if ip in reads or ip == 0x8b13a0:
            start = self.pos
            dst = u.reg_read(r.UC_X86_REG_EDX)
            if ip == 0x8b13a0:
                count = struct.unpack_from('<I', self.raw, start)[0]
                self.pos += 4 + 2 * count
                if count > 1024 or self.pos > len(self.raw):
                    raise ValueError('Bad profile string')
                self.raw[start+4:self.pos].decode('utf-16le')
                u.mem_write(dst, bytes(4))
                kind, value = 'wideString', None  # Do not publish private strings.
            else:
                kind, size = reads[ip]
                self.pos += size
                value = struct.unpack_from('<' + kind, self.raw, start)[0]
                u.mem_write(dst, self.raw[start:self.pos])
            self.trace.append(dict(fileOffset=start, end=self.pos,
                                   objectOffset=dst-0x30000000, kind=kind, value=value))
            self.ret()
            return
        if not 0x11e0214 <= ip < 0x11e049c:
            raise ValueError('Unreviewed native call 0x%x' % ip)

    def confirm(self, raw):
        u, r = self.u, self.reg
        self.raw, self.pos, self.trace = raw, 20, []
        u.mem_write(0, bytes(4096))
        u.mem_write(0x30000000, bytes(0x10000))
        u.mem_write(0x30002000, struct.pack('<I', 0x30003000))
        u.mem_write(0x2001ff00, struct.pack('<I', 0x20000001))
        for reg, value in [(r.UC_X86_REG_EAX, 0x30000000),
                           (r.UC_X86_REG_EDX, 0x30002000),
                           (r.UC_X86_REG_ECX, 2615000),
                           (r.UC_X86_REG_ESP, 0x2001ff00)]:
            u.reg_write(reg, value)
        u.emu_start(0x11e0214, 0x20000002, count=10000)
        assert u.reg_read(r.UC_X86_REG_EIP) == 0x11e049c and self.pos == 237
        flag = u.mem_read(0x30000026, 1)[0]
        assert self.trace[-1] == dict(fileOffset=236, end=237, objectOffset=38, kind='B', value=flag)
        assert struct.unpack_from('<I', raw, 237)[0] == 0  # No UA records in this exact profile.
        return dict(connectionReadOnly=bool(flag), trace=self.trace)


def check(editor):
    binary = editor.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == EDITOR_SHA
    # Delphi extended field RTTI: flags/type/offset/short-string name.
    # Boolean type0x401000, field offset0x26, name ReadOnly. The following
    # integer field is Tag at0x28; it must not be confused with ReadOnly.
    marker = bytes.fromhex('020002001040002600000008') + b'ReadOnly'
    assert binary.count(marker) == 1
    source = SCADA_SEED / 'Servers.ssr'
    raw = source.read_bytes()
    assert len(raw) == 241 and hashlib.sha256(raw).hexdigest() == PROFILE_SHA
    assert struct.unpack_from('<Iq', raw, 8) == (1, 0)
    native = NativeServer(editor)
    original = native.confirm(raw)
    assert original['connectionReadOnly'] is True
    candidate = bytearray(raw)
    candidate[236] = 0
    assert hashlib.sha256(candidate).hexdigest() == WRITE_PROFILE_SHA
    changed = native.confirm(bytes(candidate))
    assert changed['connectionReadOnly'] is False
    assert source.read_bytes() == raw
    return dict(editorSHA256=EDITOR_SHA, sourceSHA256=PROFILE_SHA,
                hypotheticalWriteEnabledSHA256=WRITE_PROFILE_SHA,
                loaderVA='0x11e0214', loaderStopVA='0x11e049c', versionArgument=2615000,
                readOnlyObjectOffset=38, readOnlyFileOffset=236,
                readOnlyFieldRTTIVerified=True, original=original, candidate=changed,
                method='Original loader in Unicorn; string/stream adapters, no OS import',
                workingFileModified=False, nativeGUIRun=False, hardwareWriteTested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != '.json' or args.out.exists():
        raise ValueError('Use a new JSON result path')
    result = check(args.editor)
    with args.out.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('PASS original profile ReadOnly=true; one-byte mock change ReadOnly=false; no live action')


if __name__ == '__main__':
    main()
