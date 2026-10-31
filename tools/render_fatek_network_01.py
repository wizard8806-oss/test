#!/usr/bin/env python3
"""Run the original Prolad18.dll network formatter in isolated x86 memory.

Requires pefile and unicorn. This executes the vendor mnemonic formatter,
not the native editor/compiler or a PLC. No imported OS function may run.
The caller supplies the separately downloaded, hash-checked vendor DLL.
"""
import hashlib
import struct
from pathlib import Path

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX

VENDOR_SHA256 = 'daef5641e3f9fb8405e6d614f393f35f279a47bbec4bacac2ce844dbb463b3e9'


def render(code: bytes, dll: Path) -> str:
    if len(code) % 2 or not code or len(code) > 0x10000:
        raise ValueError('Expected one even-length compiled network')
    binary = dll.read_bytes()
    if hashlib.sha256(binary).hexdigest() != VENDOR_SHA256:
        raise ValueError('Unreviewed vendor formatter')
    pe = pefile.PE(data=binary)
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    base = pe.OPTIONAL_HEADER.ImageBase
    size = (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095
    uc.mem_map(base, size)
    uc.mem_write(base, pe.get_memory_mapped_image())
    uc.mem_map(0, 0x10000)
    uc.mem_map(0x1000000, 0x200000)
    uc.mem_map(0x2000000, 0x200000)
    stop = 0x3000000
    uc.mem_map(stop, 4096)
    uc.mem_write(stop, b'\xf4')
    imports = {}
    uc.mem_map(0x3100000, 0x10000)
    for imp in pe.DIRECTORY_ENTRY_IMPORT:
        for sym in imp.imports:
            address = 0x3100000 + len(imports) * 16
            imports[address] = (imp.dll, sym.name or sym.ordinal)
            uc.mem_write(sym.address, struct.pack('<I', address))
            uc.mem_write(address, b'\xcc')

    def block_imports(uc, address, size, data):
        if address in imports:
            raise RuntimeError('Unexpected native import: ' + repr(imports[address]))

    uc.hook_add(UC_HOOK_CODE, block_imports)
    input_ptr, output_ptr = 0x2000000, 0x2010000
    uc.mem_write(input_ptr, code + b'\xff\xff')
    esp = 0x11ff000
    uc.mem_write(esp, struct.pack('<5I', stop, input_ptr, len(code) // 2, 0, output_ptr))
    uc.reg_write(UC_X86_REG_ESP, esp)
    export = next(e for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name == b'_GetNetNMne')
    uc.emu_start(base + export.address, stop, count=3000000)
    if uc.reg_read(UC_X86_REG_EIP) != stop:
        raise RuntimeError('Vendor formatter did not return')
    length = uc.reg_read(UC_X86_REG_EAX)
    if length > 0x10000:
        raise RuntimeError('Unexpected output size')
    return bytes(uc.mem_read(output_ptr, length)).decode('cp1251')
