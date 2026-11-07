#!/usr/bin/env python3
"""Isolated vendor network-to-node and node-to-code structural checks.

Uses the same hash-checked Prolad18.dll as the mnemonic formatter. All OS
imports are blocked. This detects unrepresentable rungs missed by mnemonic
formatting, including the rejected HP-r1 patterns. It is not full native F8
or PLC execution; existing unedited program networks are outside this API.
Requires the optional cloud-only pefile/unicorn packages.
"""
import hashlib
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX

from render_fatek_network_01 import VENDOR_SHA256


class GraphChecker:
    def __init__(self, dll):
        binary = Path(dll).read_bytes()
        if hashlib.sha256(binary).hexdigest() != VENDOR_SHA256:
            raise ValueError('Unreviewed vendor DLL')
        pe = pefile.PE(data=binary)
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        base = pe.OPTIONAL_HEADER.ImageBase
        self.uc.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage+4095) & ~4095)
        self.uc.mem_write(base, pe.get_memory_mapped_image())
        for address, size in ((0,0x10000),(0x1000000,0x200000),(0x2000000,0x200000),
                              (0x3000000,0x1000),(0x3100000,0x10000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(0x3000000,b'\xf4')
        imports = {}
        for dependency in pe.DIRECTORY_ENTRY_IMPORT:
            for symbol in dependency.imports:
                address = 0x3100000 + 16*len(imports)
                imports[address] = (dependency.dll, symbol.name or symbol.ordinal)
                self.uc.mem_write(symbol.address, struct.pack('<I', address))
                self.uc.mem_write(address,b'\xcc')

        def block_import(uc,address,size,data):
            raise RuntimeError('Unexpected OS import: '+repr(imports.get(address,address)))

        self.uc.hook_add(UC_HOOK_CODE,block_import,begin=0x3100000,end=0x310ffff)
        self.exports = {entry.name:base+entry.address for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}

    def call(self, name, args):
        stack = 0x11ff000
        self.uc.mem_write(stack,struct.pack('<'+'I'*(len(args)+1),0x3000000,*args))
        self.uc.reg_write(UC_X86_REG_ESP,stack)
        self.uc.emu_start(self.exports[name],0x3000000,count=3000000)
        if self.uc.reg_read(UC_X86_REG_EIP) != 0x3000000:
            raise RuntimeError('Vendor network conversion did not return')
        return self.uc.reg_read(UC_X86_REG_EAX)

    def inspect(self, code):
        if not code or len(code)%2 or len(code)>0xff00:
            raise ValueError('Expected one even-length network')
        input_ptr, nodes_ptr, count_ptr = 0x2000000,0x2020000,0x201f000
        self.uc.mem_write(input_ptr,code+b'\xff'*512)
        self.uc.mem_write(nodes_ptr,b'\x00'*0x10000)
        self.uc.mem_write(count_ptr,b'\x00'*16)
        error = self.call(b'_CodeTranNode',[input_ptr,len(code)//2,nodes_ptr,count_ptr])
        rows = struct.unpack('<I',self.uc.mem_read(count_ptr,4))[0]
        flags = bytes(self.uc.mem_read(0x45c330,1))[0]
        result = dict(nodeError=error,rows=rows,errorFlag=bool(flags&1),roundTrip=False)
        if error or flags&1 or not 1<=rows<=64:
            return result
        code_ptr, words_ptr = 0x2040000, count_ptr+4
        inverse = self.call(b'_NodeTranCode',[nodes_ptr,rows,code_ptr,words_ptr])
        length = struct.unpack('<I',self.uc.mem_read(words_ptr,4))[0]
        if inverse or not 1<=length<=0x7f80:
            result['inverseError'] = inverse
            return result
        canonical = bytes(self.uc.mem_read(code_ptr,length*2))
        self.uc.mem_write(input_ptr,canonical+b'\xff'*512)
        again = self.call(b'_CodeTranNode',[input_ptr,length,nodes_ptr,count_ptr])
        again_flags = bytes(self.uc.mem_read(0x45c330,1))[0]
        result.update(roundTrip=not again and not again_flags&1,
                      canonicalBytes=len(canonical),canonicalHex=canonical.hex(),
                      roundTripNodeError=again)
        return result

    def require(self, code):
        result = self.inspect(code)
        if result['nodeError'] or result['errorFlag'] or not result['roundTrip']:
            raise ValueError('Unrepresentable native network: '+repr(result))
        return result
