"""Validate the narrow Variables.svr layout against the official x86 loader.

Optional cloud verification, not a Windows application launch. GUI, strings,
registration and version access use adapters; native scalar read order and the
zero-offset multiplier setter execute in Unicorn. No project files are written.
"""
import hashlib
import os
import struct
from pathlib import Path

from _runtime import ROOT, SCADA_SEED

EDITOR_SHA = 'c90b3e893d9918c3e0dd95aedb7d0b6744453dc96003244d51dd8d2282078b57'


class Layout:
    """Independent portable reader, recording every body read for comparison."""
    def __init__(self, raw):
        self.raw, self.pos, self.records, self.groups = raw, 0, [], 0
        self.trace = []

    def scalar(self, fmt):
        start = self.pos
        size = struct.calcsize('<' + fmt)
        if size > len(self.raw) - start:
            raise ValueError('truncated scalar')
        self.pos += size
        self.trace.append((start, self.pos, fmt))
        return struct.unpack_from('<' + fmt, self.raw, start)[0]

    def text(self, wide=False):
        start = self.pos
        count = self.scalar('I')
        size = count * (2 if wide else 1)
        if count > 65536 or size > len(self.raw) - self.pos:
            raise ValueError('truncated/overlong string')
        value = self.raw[self.pos:self.pos+size].decode('utf-16le' if wide else 'utf8')
        self.pos += size
        self.trace[-1] = (start, self.pos, 'w' if wide else 's')
        return value

    def variable(self):
        start = self.pos
        name, id_ = self.text(), self.scalar('q')
        body = self.pos
        self.trace = []
        self.scalar('I')
        address_position = self.pos
        address, bit, type_, outer = self.text(True), self.scalar('b'), self.scalar('I'), self.scalar('B')
        for fmt in ('I', 'B', 'f', 'I', 'I'):
            self.scalar(fmt)
        description_position = self.pos
        self.text(True)
        for fmt in ('B', 'I', 'B', 'f'):
            self.scalar(fmt)
        self.text(True)
        for fmt in ('B', 'B', 'd', 'd'):
            self.scalar(fmt)
        ua_position = self.pos
        assert self.scalar('B') == 0, 'only the validated internal/OPC DA layout'
        opc = self.scalar('B')
        assert opc in (0, 1)
        self.scalar('q')
        for _ in range(4 if opc else 1):
            self.text(True)
        self.scalar('I')
        for _ in range(4):
            self.scalar('d')
        for _ in range(4):
            self.scalar('q')
        self.text(True)
        offset_position = self.pos
        offset, scaling = self.scalar('b'), self.scalar('B')
        self.scalar('d'); self.scalar('d')
        self.records.append(dict(start=start, body=body, end=self.pos, name=name, id=id_, address=address,
                                 address_position=address_position, description_position=description_position,
                                 ua_position=ua_position, bit=bit, type=type_, external=outer,
                                 offset=offset, offset_position=offset_position, scaling=scaling,
                                 trace=list(self.trace)))

    def group(self, depth=0):
        assert depth <= 32
        self.groups += 1
        self.text(); self.scalar('B'); self.scalar('I')
        count = self.scalar('I'); assert count <= 10000
        for _ in range(count):
            self.variable()
        count = self.scalar('I'); assert count <= 1000
        for _ in range(count):
            self.group(depth+1)

    def run(self):
        self.scalar('q')
        count = self.scalar('I'); assert count <= 1000
        for _ in range(count):
            self.group()
        assert self.pos == len(self.raw)
        return self


class NativeBody:
    def __init__(self, image):
        import pefile
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn import x86_const as reg
        assert hashlib.sha256(image.read_bytes()).hexdigest() == EDITOR_SHA
        pe = pefile.PE(str(image))
        data, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        self.reg = reg
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(base, (len(data)+4095)//4096*4096)
        self.u.mem_write(base, data)
        for address, length in [(0, 4096), (0x20000000, 0x20000), (0x30000000, 0x20000)]:
            self.u.mem_map(address, length)
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def ret(self, pop=0):
        r, u = self.reg, self.u
        sp = u.reg_read(r.UC_X86_REG_ESP)
        target = struct.unpack('<I', u.mem_read(sp, 4))[0]
        u.reg_write(r.UC_X86_REG_ESP, sp+4+pop)
        u.reg_write(r.UC_X86_REG_EIP, target)

    def hook(self, u, ip, size, user):
        r = self.reg
        if ip == 0xfbabc2:  # All serialized body fields read; skip value registration/cleanup.
            u.emu_stop(); return
        reads = {0x8b0e60: 'I', 0x8b0924: 'q', 0x8b1e30: 'B', 0x8b21b0: 'B',
                 0x8b0078: 'f', 0x8b0ae0: 'b', 0x8b0234: 'd'}
        if ip in reads or ip == 0x8b13a0:
            start = self.pos
            dst = u.reg_read(r.UC_X86_REG_EDX)
            if ip in reads:
                fmt = reads[ip]
                length = struct.calcsize('<'+fmt)
                data = self.raw[start:start+length]
                assert len(data) == length
                self.pos += length
                u.mem_write(dst, data)
            else:
                count = struct.unpack_from('<I', self.raw, start)[0]
                self.pos += 4+count*2
                assert self.pos <= len(self.raw)
                u.mem_write(dst, struct.pack('<I', 0)); fmt = 'w'
            self.trace.append((start, self.pos, fmt)); self.ret(); return
        if ip == 0x11bef6c:
            u.reg_write(r.UC_X86_REG_EAX, 2615000); self.ret(); return
        if ip == 0x40dc50:  # Special-name comparison before RegisterID is overwritten.
            u.reg_write(r.UC_X86_REG_EFLAGS, u.reg_read(r.UC_X86_REG_EFLAGS) & ~64)
            self.ret(); return
        if ip in (0xfb9bdc, 0x40c690, 0x40c6b4, 0x30011000, 0x30011008):
            self.ret(); return
        if ip == 0x4a5a20:  # Finite-limit adapter, no stream reads.
            u.reg_write(r.UC_X86_REG_EAX, 0); self.ret(8); return
        if not (0xfba178 <= ip < 0xfbac06 or 0xfbac9c <= ip < 0xfbacdf):
            raise ValueError('Unexpected native call 0x%x' % ip)

    def run(self, raw, record):
        u, r = self.u, self.reg
        self.raw, self.pos, self.trace = raw, record['body'], []
        put = lambda address, value: u.mem_write(address, struct.pack('<I', value))
        u.mem_write(0, bytes(4096)); u.mem_write(0x30000000, bytes(4096))
        put(0x30000000, 0x30010000)
        put(0x30010000, 0x30011000)
        put(0x30010074, 0xfbac9c)  # Actual DecimalOffset setter, zero path executes fld1.
        put(0x30010078, 0x30011008)
        put(0x134e7bc, 0x30001000); put(0x30001000, 1); put(0x30002000, 0x30003000)
        put(0x2001ff00, 0x20000001)
        u.reg_write(r.UC_X86_REG_ESP, 0x2001ff00)
        u.reg_write(r.UC_X86_REG_EAX, 0x30000000)
        u.reg_write(r.UC_X86_REG_EDX, 0x30002000)
        u.emu_start(0xfba178, 0x20000002, count=20000)
        assert u.reg_read(r.UC_X86_REG_EIP) == 0xfbabc2
        assert self.pos == record['end'] and self.trace == record['trace']
        assert struct.unpack('<b', u.mem_read(0x30000056, 1))[0] == record['offset'] == 0
        assert struct.unpack('<d', u.mem_read(0x30000058, 8))[0] == 1.0
        assert u.mem_read(0x3000003e, 1)[0] == record['scaling']


def main():
    image = Path(os.environ.get('CODEX_SCADA_EDITOR', ROOT/'.local-tools/scada-2.6.15/Editor.exe'))
    demo = Path(os.environ['CODEX_SCADA_DEMO_VARIABLES'])
    native = NativeBody(image)
    for label, path in [('seed', SCADA_SEED/'Variables.svr'), ('official-demo', demo)]:
        raw = path.read_bytes(); before = hashlib.sha256(raw).hexdigest()
        layout = Layout(raw).run()
        for record in layout.records:
            native.run(raw, record)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        print('PASS native body trace/zero multiplier:', label, len(raw), 'bytes,',
              layout.groups, 'groups,', len(layout.records), 'variables; SHA256', before)
    print('Scope: x86 emulation with adapters; Windows GUI/F8/F9/live candidate not checked.')


if __name__ == '__main__':
    main()
