#!/usr/bin/env python3
"""Read-only review of this WinProladder Format1/FBS40003 project.

Rung comments and symbols have additive checksums. The compiled image is
decoded from its repeated blank-FF padding and checked against the FBS header
and independently named MOV anchors. Only MOV operands needed for the process
map are interpreted; this is not a full ladder simulator or native compiler.
This legacy contract expects map31 and D200/D203/D206/D209 frequency sources.
For the exact reviewed map32 source04/generated05, use review_fatek_map32.py.
"""
import argparse,hashlib,json,re,struct
from pathlib import Path

def u16(data,offset):return struct.unpack_from('<H',data,offset)[0]

def plain_records(data,start,kind):
 marker=struct.pack('<H',kind)
 for offset in range(start,len(data)-6):
  if data[offset:offset+2]!=marker:continue
  length=u16(data,offset+2);end=offset+4+length
  if end+2>len(data):continue
  body=data[offset+4:end]
  check=u16(data,end)
  if kind==0x1003:
   # Integer fields are bytes; text fields are signed CP1251 chars.
   p=0;total=0
   try:
    for _ in range(3):
     n=u16(body,p);total+=sum(body[p:p+2]);p+=2
     total+=sum(v if v<128 else v-256 for v in body[p:p+n]);p+=n
   except struct.error:continue
   if p!=len(body) or total&65535!=check:continue
  elif kind==0x1002:
   total=sum(body[:4])+sum(v if v<128 else v-256 for v in body[4:])
   if total&65535!=check:continue
  elif kind==0x1015:
   # Table end marker, not the rung-comment checksum algorithm.
   if check!=0x043c:continue
  elif sum(body)&65535!=check:continue
  yield offset,body

def register(value):
 if 0x4000<=value<0x4800 and value%2==0:return 'D'+str((value-0x4000)//2)
 if 0x0a00<=value<0x4000 and value%2==0:return 'R'+str((value-0x0a00)//2)
 return 'ADDR_'+format(value,'04X')

def review(path):
 original=Path(path).read_bytes()
 if not original.startswith(b'Fatek WinProladder, File Format 1'):raise ValueError('Unsupported PDW header')
 if u16(original,0x100)!=0x1006:raise ValueError('Project record missing')
 plen=u16(original,0x102);project=original[0x104:0x104+plen]
 if sum(project)&65535!=u16(original,0x104+plen):raise ValueError('Project metadata checksum failed')
 first=0x106+plen
 if u16(original,first)!=0x180a:raise ValueError('Compiled image record missing')
 length=u16(original,first+2);encrypted=original[first+4:first+4+length]
 period=1280
 if len(encrypted)<period*3 or length%period:raise ValueError('Unsupported compiled image length')
 if not encrypted[-period:]==encrypted[-2*period:-period]==encrypted[-3*period:-2*period]:raise ValueError('No repeated blank padding reference')
 key=bytes(v^255 for v in encrypted[-period:]);image=bytes(v^key[i%period] for i,v in enumerate(encrypted))
 if image[:8]!=b'FBS40003':raise ValueError('Decoded image header mismatch')
 second=first+4+length
 if u16(original,second)!=0x180b:raise ValueError('Second image record missing')
 text_start=second+4+u16(original,second+2)
 rungs=[]
 for offset,body in plain_records(original,text_start,0x1002):
  if len(body)<8:continue
  pc,n=struct.unpack_from('<HH',body)
  if n+4!=len(body) or not re.match(rb'[0-9]{2}\.',body[4:]):continue
  rungs.append(dict(file_offset=offset,pc=pc,label=body[4:].decode('cp1251').strip()))
 if len(rungs)<1000 or [r['pc'] for r in rungs]!=sorted(r['pc'] for r in rungs):raise ValueError('Unexpected rung sequence')
 for i,rung in enumerate(rungs):
  end=rungs[i+1]['pc'] if i+1<len(rungs) else rung['pc']+16
  if end>len(image) or end<rung['pc']:raise ValueError('Rung outside image')
  code=image[rung['pc']:end];rung['code_hex']=code.hex();rung['moves']=[]
  for p in range(0,len(code)-5,2):
   opcode,src,dst=struct.unpack_from('>HHH',code,p)
   if opcode in [0xf4ac,0xf5ac]:rung['moves'].append(dict(source=('K'+str(src)) if opcode==0xf5ac else register(src),destination=register(dst)))
 by_label={r['label']:r for r in rungs}
 anchors=[('10.01 | MODBUS_PRESSURE_INPUT','R132','R101'),
  ('10.03 | PRESSURE_SETPOINT','R2100','R110'),
  ('65.T006 | P1_FREQ_VALUE','D200','R2500'),
  ('65.T007 | P1_DISPLAY_UNKNOWN','K0','R2510'),
  ('65.T015 | P2_FREQ_VALUE','D203','R2501'),
  ('65.T016 | P2_DISPLAY_UNKNOWN','K0','R2511'),
  ('65.T024 | P3_FREQ_VALUE','D206','R2502'),
  ('65.T025 | P3_DISPLAY_UNKNOWN','K0','R2512'),
  ('65.T033 | P4_FREQ_VALUE','D209','R2503'),
  ('65.T034 | P4_DISPLAY_UNKNOWN','K0','R2513'),
  ('95.087 | HMI_PRESSURE_VALUE','R101','R2302'),
  ('95.088 | HMI_PRESSURE_VALID_ZERO','K0','R2303'),
  ('95.089 | HMI_PRESSURE_VALID_ONE','K1','R2303'),
  ('95.103 | HMI_PRESSURE_SOURCE','R130','R2308'),
  ('95.160 | HMI_HEARTBEAT_ZERO','K0','R2328'),
  ('95.161 | HMI_HEARTBEAT_ONE','K1','R2328'),
  ('95.A001 | HMI_TREND_SETPOINT','R2100','R2360'),
  ('95.A002 | HMI_TREND_PRESSURE','R2302','R2361'),
  ('95.A003 | HMI_TREND_QUALITY','R2303','R2362'),
  ('95.W032 | WORD_STATUS_VERSION','K31','R2554')]
 evidence=[]
 for label,src,dst in anchors:
  rung=by_label[label]
  if dict(source=src,destination=dst) not in rung['moves']:raise ValueError('MOV anchor mismatch: '+label)
  evidence.append(rung)
 symbols=[]
 for offset,body in plain_records(original,text_start,0x1003):
  try:
   p=0;fields=[]
   for _ in range(3):n=u16(body,p);p+=2;fields.append(body[p:p+n].decode('cp1251'));p+=n
   if p!=len(body):continue
   symbols.append(dict(address=fields[0],symbol=fields[1],comment=fields[2],file_offset=offset))
  except (struct.error,UnicodeDecodeError):continue
 pressure_symbol=next(s for s in symbols if s['address']=='R101')
 if pressure_symbol['symbol']!='P5_BAR100' or '*100' not in pressure_symbol['comment'].replace(' ',''):raise ValueError('Pressure scale symbol mismatch')
 tables=[]
 for offset,body in plain_records(original,text_start,0x1015):
  n=u16(body,0)
  if n<2 or n>128:continue
  name=body[2:2+n].rstrip(b'\0').decode('ascii','replace')
  reg=re.search(rb'R[0-9]+\x00',body[2+n:2+n+40])
  if not reg:continue
  copies=[]
  for p in range(len(body)-4):
   if body[p:p+2]!=b'\x50\xa5':continue
   rows,columns=body[p+2:p+4]
   if columns!=7 or not rows or p+4+rows*14>len(body):continue
   data=struct.unpack_from('<'+'H'*(rows*7),body,p+4)
   copies.append([list(data[i*7:(i+1)*7]) for i in range(rows)])
  if copies:
   if len(copies)!=2 or copies[0]!=copies[1]:raise ValueError('Table memory copies differ: '+name)
   tables.append(dict(name=name,register=reg[0].rstrip(b'\0').decode(),file_offset=offset,rows=copies[0],copies_equal=True))
 normal=next(t for t in tables if t['register']=='R5000')
 if len(normal['rows'])!=18:raise ValueError('Unexpected normal polling table')
 alarms=[]
 for bit in range(25):
  word_rung=by_label['95.W'+str(bit+5).zfill(3)+' | WORD_ALARM_BIT_'+str(bit).zfill(2)]
  contact=int(word_rung['code_hex'][:4],16)
  producers=[]
  for rung in rungs:
   if not rung['label'].startswith('95.'):continue
   code=bytes.fromhex(rung['code_hex'])
   if len(code)>=2 and int.from_bytes(code[-2:],'big') in [contact|0x8000,(contact&0x0fff)|0x1000]:producers.append(rung)
  if len(producers)!=1:raise ValueError('Ambiguous alarm source for bit '+str(bit)+': '+str(len(producers)))
  alarms.append(dict(register=2550 if bit<16 else 2551,bit=bit%16,mask=1<<(bit%16),source=producers[0]['label'],pc=producers[0]['pc']))
 fields=[('PressurePV_x100',2302,'bar',0.01),('PressureSourceOK',2303,'boolean',1),
  ('PressureSource',2308,'drive index,0=none',1),('PlcHeartbeatToggle',2328,'0/1',1),
  ('PressureSP_x100',2360,'bar',0.01),('AlarmLo',2550,'bitmask',1),('AlarmHi',2551,'bitmask',1)]
 tags=[dict(name=n,plc_register='R'+str(a),pdu_address=a,region='HOLDING_REGISTERS',device_type='uint16',server_type='uint32',access='ReadOnly',engineering_unit=u,display_factor=f) for n,a,u,f in fields]
 selection=[r for r in rungs if r['label'].startswith(('65.13 |','65.14 |','65.15 |','65.16 |','65.17 |','65.18 |','65.P1','65.P2','65.P3','65.P4'))]
 drives=[]
 for drive in range(1,5):
  matches=[(i,row) for i,row in enumerate(normal['rows']) if row[0]==drive and row[1]==1 and row[2]==1 and row[6]==0x1003+1]
  if len(matches)!=1:raise ValueError('Ambiguous frequency polling row')
  index,row=matches[0]
  drives.append(dict(drive=drive,frequency_register=2500+drive-1,frequency_state_register=2510+drive-1,
   frequency_state_codes={'0':'unknown_or_stale','1':'PLC_frequency_display_stopped','2':'PLC_frequency_display_running'},
   frequency_source_buffer='D'+str(row[4]),normal_poll_row=index+1,frequency_native_pdu=0x1003,
   frequency_scale_reference=0.1,frequency_scale_live_verified=False,current_native_pdu=0x1006,
   current_scale_reference=0.1,current_PLC_export=None))
 def covers(table,row,address):return row[1]==1 and row[6]-1<=address<row[6]-1+row[2]
 current_reads=[dict(table=t['register'],row=i+1) for t in tables for i,row in enumerate(t['rows']) if covers(t,row,0x1006)]
 if current_reads:raise ValueError('Current-read absence assumption changed; review data flow')
 return dict(source_name=Path(path).name,source_sha256=hashlib.sha256(original).hexdigest(),bytes=len(original),
  method='Read-only decoded compiled image plus checksum-verified comments/symbols; partial MOV interpretation; not native GUI validation',
  decoded_image_header=image[:8].decode(),rung_comments_checked=len(rungs),mov_anchors_checked=len(anchors),
  pressure_scale_evidence=pressure_symbol,mov_evidence=evidence,pressure_selection_evidence=selection,
  read_only_tags=tags,alarm_bits=alarms,master_tables=tables,drive_frequency_exports=drives,current_reads=current_reads,
  pressure_quality_limit='R2303 reports selected Modbus pressure source, not independent proof of healthy 4-20mA sensor; input is clamped at low/high limits.',
  heartbeat_limit='R2328 is a 0/1 clock copy, not an incrementing sequence. Fixed-period polling can alias it; do not base unconditional PLC-failure alarms on absence of a change.',
  native_vfd_fault_limit='Regular R5000 rows do not poll native fault0x1001. Four-word stop/run/preflight reads include fault in scratch buffers, but no fresh per-drive fault-code export is established. R2550 readiness/link alarms are not native VFD error codes.',
  live_read_verified=False,PLC_modified=False)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('--out',required=True);args=ap.parse_args()
 report=review(args.source);Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('PDW reviewed:',report['rung_comments_checked'],'checked comments,',report['mov_anchors_checked'],'MOV anchors,',len(report['master_tables']),'master tables; source unchanged.')

if __name__=='__main__':main()
