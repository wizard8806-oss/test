"""Run 2.6.15 Editor x86 object-load code in Unicorn with read/UI adapters.

Only stream reading/control-property loading is exercised. GUI, managed string
allocation, event bindings, the native Pascal compiler and Windows are not run.
Requires pefile/unicorn plus the official 2.6.15 Editor.exe, not redistributed.
"""
from _runtime import ROOT, SCADA_SEED
import os
import sys,struct,json,hashlib,re
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
U32=lambda n:struct.pack('<I',n)
IMAGE=Path(os.environ.get('CODEX_SCADA_EDITOR', str(ROOT / '.local-tools/scada-2.6.15/Editor.exe')))
PE=pefile.PE(str(IMAGE)); DATA=PE.get_memory_mapped_image(); BASE=PE.OPTIONAL_HEADER.ImageBase
READS={0x8b0e60:4,0x8b0924:8,0x8b1e30:1,0x8b21b0:1,0x8b18d4:4,0x8b0078:4,0x8b1ff0:2,0x8b1aac:16}
STUBS={0x40c6f0:0,0x40c690:0,0x40c6b4:0,0x40ca70:0,0x412ff4:0,0x40cab8:0,0x12a3540:0,
0x12416a4:8,0x12415e4:8,0x1244d74:0,0x1246368:0,0x12458a8:0,0x124640c:0,0x93d9a4:0,
0x93d430:0,0x40a940:0}
RANGES=[(0x1244b70,0x1244ca6),(0x12410ac,0x1241313),(0x12a2940,0x12a2b19),(0x12a0d20,0x12a0d2e),
(0x9329a4,0x9329f5),(0x93d5d0,0x93d640),(0x1245a5c,0x1245cb5)]
class NativeReader:
 def __init__(self,raw,pos,kind):
  self.raw=raw;self.pos=pos;self.trace=[];self.last=None;self.kind=kind
  u=self.u=Uc(UC_ARCH_X86,UC_MODE_32)
  u.mem_map(BASE,(len(DATA)+4095)//4096*4096);u.mem_write(BASE,DATA)
  u.mem_map(0,4096);u.mem_map(0x20000000,0x20000);u.mem_map(0x30000000,0x20000)
  u.mem_write(0x30000000,U32(0x1222d24 if kind==4 else 0x122364c))
  u.mem_write(0x30000124,U32(0x30001000))
  self.stack=0x2001ff00;u.mem_write(self.stack,U32(0x20000001));u.reg_write(UC_X86_REG_ESP,self.stack)
  u.reg_write(UC_X86_REG_EAX,0x30000000);u.reg_write(UC_X86_REG_EDX,0x30002000);u.reg_write(UC_X86_REG_ECX,2615000)
  u.hook_add(UC_HOOK_CODE,self.hook)
 def ret(self,pop=0):
  u=self.u;sp=u.reg_read(UC_X86_REG_ESP);ip=struct.unpack('<I',u.mem_read(sp,4))[0]
  u.reg_write(UC_X86_REG_ESP,sp+4+pop);u.reg_write(UC_X86_REG_EIP,ip)
 def take(self,n):
  if n<0 or self.pos+n>len(self.raw):raise ValueError('Stream read error at %d requesting %d (call %x)'%(self.pos,n,self.last))
  d=self.raw[self.pos:self.pos+n];self.pos+=n;return d
 def hook(self,u,ip,size,user):
  if ip==0x20000001:u.emu_stop();return
  if ip in READS or ip in [0x8b1020,0x8b13a0]:
   sp=u.reg_read(UC_X86_REG_ESP);self.last=struct.unpack('<I',u.mem_read(sp,4))[0]-5
   dst=u.reg_read(UC_X86_REG_EDX);start=self.pos
   if ip in READS:d=self.take(READS[ip]);u.mem_write(dst,d)
   else:
    n=struct.unpack('<I',self.take(4))[0];d=self.take(n*(2 if ip==0x8b13a0 else 1));u.mem_write(dst,U32(0))
   self.trace.append((start,self.pos,hex(self.last),d.hex()[:80]));self.ret();return
  if ip in STUBS:
   if ip==0x40a940:u.reg_write(UC_X86_REG_EAX,1 if self.kind==5 else 0)
   elif ip==0x93d430:u.reg_write(UC_X86_REG_EAX,0x30003000)
   elif ip in [0x12415e4,0x12416a4]:
    obj=u.reg_read(UC_X86_REG_EAX);sp=u.reg_read(UC_X86_REG_ESP)
    u.mem_write(obj+(0x138 if ip==0x12415e4 else 0x148),bytes(u.mem_read(sp+4,8)))
   self.ret(STUBS[ip]);return
  if not any(lo<=ip<hi for lo,hi in RANGES):raise ValueError('Unmocked call %x after %r'%(ip,self.trace[-3:]))
 def run(self):
  self.u.emu_start(0x1244b70 if self.kind==4 else 0x1245a5c,0x20000002,count=100000)
  assert self.u.reg_read(UC_X86_REG_EIP)==0x20000001
  return self.pos
def read_pages(path):
 """Page/subpage sequence comes from 129733c/129a5cc/129bcbc, not the writer."""
 raw=Path(path).read_bytes();pos=0;objects=[];page_ids=[];uid_set=set();next_page=None
 def read(fmt):
  nonlocal pos
  n=struct.calcsize('<'+fmt)
  if pos+n>len(raw):raise ValueError('Header truncated')
  value=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=n;return value
 def string(wide=False):
  nonlocal pos
  n=read('I')*(2 if wide else 1)
  if pos+n>len(raw):raise ValueError('Header string truncated')
  data=raw[pos:pos+n];pos+=n;return data.decode('utf-16le' if wide else 'utf8')
 def uid():
  v=read('I');assert v not in uid_set,('Duplicate UID',v);uid_set.add(v);return v
 next_page=read('q');count=read('I')
 for page in range(count):
  name=string();caption=string(True);id_offset=pos;page_id=read('q')
  assert page_id not in page_ids,('Duplicate page ID',page_id)
  page_ids.append(page_id);uid();read('q');read('q');next_subpage=read('q')
  read('I');read('I');read('B');read('I');nsub=read('I');sub_ids=[]
  for _ in range(nsub):
   subname=string();subcaption=string(True);subid=read('q');assert subid not in sub_ids;sub_ids.append(subid)
   read('I');read('I');string();uid();read('q');read('q');read('I');read('I');read('B');read('I')
   nobj=read('I')
   for _ in range(nobj):
    kind=read('H');object_name=string();start=pos
    assert kind in [4,5],('This fixture verifier only supports Text and Field',kind)
    reader=NativeReader(raw,start,kind);pos=reader.run()
    object_uid=struct.unpack_from('<I',raw,start+107)[0]
    assert object_uid not in uid_set;uid_set.add(object_uid)
    objects.append(dict(page=page,page_id_offset=id_offset,name=object_name,kind=kind,
                        body=start,end=pos,reads=len(reader.trace)))
   assert next_subpage>max(sub_ids)
 assert next_page>max(page_ids) and pos==len(raw),(pos,len(raw))
 assert len({o['name'] for o in objects})==len(objects)
 return dict(bytes=pos,page_ids=page_ids,objects=objects)

def main():
 root=Path(__file__).resolve().parents[1];out=root/'artifacts/simple-scada-diagnostics-01'
 original=read_pages(SCADA_SEED / 'Pages.spg');candidate=read_pages(out/'Pages.spg')
 assert len(original['objects'])==2 and len(candidate['objects'])==20
 for obj in candidate['objects']:
  if obj['kind']==4:
   b=(out/'Pages.spg').read_bytes();s=obj['body']
   assert struct.unpack_from('<q',b,s+111)[0]==-1
   assert b[s+49:s+54]==bytes(5)
 # Regression: actual x86 loader must reject the old Z-order offset.
 raw=bytearray((out/'Pages.spg').read_bytes());start=candidate['objects'][2]['body']
 struct.pack_into('<I',raw,start+51,2)
 try:NativeReader(bytes(raw),start,4).run()
 except ValueError as e:
  assert 'requesting 131072' in str(e);regression=str(e)
 else:raise AssertionError('Rejected hint-length corruption was accepted')
 # Independent native Text record from the manufacturer's matching demo.
 demo=Path(os.environ['CODEX_SCADA_DEMO_PAGES']).read_bytes()
 assert demo[4369:4380]==b'\x04\x00\x05\x00\x00\x00txtA1'
 reference=NativeReader(demo,4380,4);assert reference.run()==4538
 assert demo[4538:4559]==b'\x05\x00\x0f\x00\x00\x00fldATemperature'
 report=dict(editor_sha256=hashlib.sha256(IMAGE.read_bytes()).hexdigest(),version='2.6.15.0',
  original=original,candidate=candidate,corrupt_layer_regression=regression,
  official_demo_text_reader=dict(name='txtA1',start=4380,end=4538,passed=True),
  scope='Native x86 stream reader in emulation; UI/strings/event bindings are adapters.',
  native_GUI_or_F9_passed=False)
 (out/'native-loader-validation-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('PASS: original 2 Fields, repaired 20 objects, official Text; rejected old corruption.')
 return candidate

if __name__=='__main__':main()
