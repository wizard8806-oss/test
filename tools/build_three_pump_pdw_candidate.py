#!/usr/bin/env python3
"""Create a separate fixed-three-pump offline candidate from accepted HP-r2.

Source locked; no PLC connection, overwrite, or HMI change. The original
ROM master-table templates stay intact. A constant RAM table addressed by
the normal FUN150 worker contains exactly the fourteen requests to 1..3.
The existing single-job workers already use RAM table copies in this way.
Native F8 and actual worker/pressure behavior require separate acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from build_setpoint_feedback_pdw_01 import build, layout, word_sum
from check_native_drive_edit_02 import unpack

SOURCE_SHA = '7d436bec9fab5a50bd60ae22e269be90a5adfb9a579426b397a7520c82a82db4'
ANCHOR = '10.01 | MODBUS_PRESSURE_INPUT'
RAM_TABLE = 2900
COUNT = 3


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def words(*values):
    return struct.pack('>'+'H'*len(values), *values)


def r(number):
    if not 0 <= number < 3840:
        raise ValueError('Ordinary R address required')
    return 0xa00+2*number


def d(number):
    if not 0 <= number < 1024:
        raise ValueError('Reviewed D address range required')
    return 0x4000+2*number


def prepare(source):
    raw = Path(source).read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError('Use exact accepted HP-r2, preserve other native saves')
    obj = unpack(Path(source))
    part = layout(raw)
    image = bytearray(part['image'])
    end = int.from_bytes(image[270:272], 'little')
    if len(obj['tables']) != 9 or len(obj['rungs']) != 1878:
        raise ValueError('Unexpected source inventory')
    for number in list(range(2860,2868))+list(range(RAM_TABLE,RAM_TABLE+101)):
        if any(image[pc:pc+2] == words(r(number)) for pc in range(512,end,2)):
            raise ValueError('Possible original reference in candidate R range')
    for name,table in obj['tables'].items():
        ranges = [(int(name[1:]),4+8*len(table['rows']))]
        ranges += [(row[4],row[2]) for row in table['rows'] if row[3]==12]
        if any(max(start,RAM_TABLE)<min(start+length,RAM_TABLE+101) for start,length in ranges):
            raise ValueError('RAM poll table overlaps existing table/buffer')

    indexed = []
    for i,(pc,label) in enumerate(obj['rungs']):
        stop = obj['rungs'][i+1][0] if i+1<len(obj['rungs']) else end-2
        indexed.append((pc,label,stop))
    edits = []

    def edit(prefix, old, new, count=1):
        if len(old)!=len(new):
            raise ValueError('Only reviewed same-size operand/contact edits')
        found=[]
        for pc,label,stop in indexed:
            if not label.startswith(prefix):
                continue
            for offset in range(pc,stop-len(old)+1,2):
                if image[offset:offset+len(old)]==old:
                    found.append((offset,label))
        if len(found)!=count:
            raise ValueError('Anchor/pattern mismatch '+prefix+': '+str(len(found)))
        for offset,label in found:
            image[offset:offset+len(old)]=new
            edits.append(dict(label=label,pc=offset,oldHex=old.hex(),newHex=new.hex()))

    # Clamp physical absence independently of selector, cached role and demand.
    edit('70.01',words(0x4004,0xc8db),words(0x5feb,0xc8db))
    edit('90.05',words(0xc104),words(0x0104)) # replace the sole fourth RUN coil by reset
    edit('65.11',words(0x4a6a),words(0x5feb)) # never set link for absent drive
    edit('65.17',words(0x4a75),words(0x5feb))
    edit('65.M069',words(0x4004),words(0x5feb))
    edit('65.M073',words(0x8004),words(0x9fe7))
    edit('65.S17',words(0xf5ac,4,d(845)),words(0xf5ac,0,d(845)))
    edit('65.61',words(0x4ad4),words(0x5feb))
    edit('65.56',words(0x4ac8),words(0x5feb))
    edit('95.A013',words(0x5f94),words(0x5feb))
    edit('95.A017',words(0x5f94),words(0x5feb))
    edit('95.S053',words(0xf4ac,r(2173),r(723)),words(0xf5ac,0,r(723)))
    edit('95.S035D',words(0xf67f,0x23,r(2173),2),words(0xf67f,0x23,r(2173),1))
    # The manual cursor and two AUTO queue completion sentinels are 1..3 /4.
    edit('65.M097',words(0xf67f,0x16,r(2400),4),words(0xf67f,0x16,r(2400),3))
    for prefix,register in [('60.138',d(278)),('65.G31',d(403)),
                            ('65.K08',d(666)),('65.F04',d(288)),
                            ('65.P01',d(250)),('65.36B',d(251)),
                            ('60.70',r(484))]:
        edit(prefix,words(0xf67f,0x23,register,5),words(0xf67f,0x23,register,4))
    for prefix,register in [('60.140',d(278)),('65.G33',d(403))]:
        edit(prefix,words(0xf67f,0x21,register,5),words(0xf67f,0x21,register,4))
    # Packet numbering changes when the interleaved four-address table is filtered.
    edit('65.T019',words(0xf67f,0x21,d(300),16),words(0xf67f,0x21,d(300),13))
    edit('65.T028',words(0x8a6a),words(0x9fe7))
    # A source-locked FUN150 parameter edit, not a replacement of its topology.
    edit('65.00',words(0xf31b,0x2800,d(300)),words(0xf31b,r(RAM_TABLE),d(300)))

    rows = [list(row) for row in obj['tables']['R5000']['rows'] if row[0]<=COUNT]
    if len(rows)!=14 or {row[0] for row in rows}!={1,2,3}:
        raise ValueError('Unexpected interleaved poll distribution')
    template = next(x['body'] for x in part['records'] if x['kind']==0x1015 and b'R5000\0' in x['body'])
    offset=template.index(b'\x50\xa5')
    trailer=int.from_bytes(template[offset+4+18*14:offset+6+18*14],'little')
    # The template's trailing word is retained as in the existing mutable
    # single-job buffers. FUN150 uses the packed packet count and seven fields.
    table_words=[0xa550,7*256+len(rows)]+[v for row in rows for v in row]+[trailer]
    assert len(table_words)==101
    plan=[]

    def mov(label,address,value):
        plan.append(dict(label='10.N3%03d | '%(len(plan)+1)+label,
                         expectedCodeHex=words(0x4fe8,0xf5ac,value&65535,address).hex()))

    for number,value,name in [(2860,3,'FIXED_COUNT'),(2861,27114,'BUILD_MARKER'),
                              (2862,3,'COUNT_DISPLAY'),(2863,0,'FIXED_BUILD_STATUS'),
                              (2864,7,'INSTALLED_MASK'),(2865,1,'CONFIG_VALID'),
                              (2866,1,'CONFIG_REVISION'),(2867,1,'PICTURE_INDEX')]:
        mov(name,r(number),value)
    mov('ABSENT_P4_MEMBERSHIP',r(723),0)
    mov('ABSENT_P4_STOP_HISTORY',d(853),0)
    plan.append(dict(label='10.N3%03d | ABSENT_P4_LINK_RESET'%(len(plan)+1),
                     expectedCodeHex=words(0x4fe8,0x0a75).hex()))
    plan.append(dict(label='10.N3%03d | ABSENT_P4_Y4_RESET'%(len(plan)+1),
                     expectedCodeHex=words(0x4fe8,0x0104).hex()))
    for index,value in enumerate(table_words):
        mov('POLL_RAM_R'+str(RAM_TABLE+index),r(RAM_TABLE+index),value)

    struct.pack_into('<H',image,202,word_sum(image[512:end]))
    encoded=bytes(v^part['key'][i%1280] for i,v in enumerate(image))
    changed=bytearray(raw);changed[part['first']+4:part['second']]=encoded
    struct.pack_into('<H',changed,part['checksum'],(sum(encoded)+sum(part['payload']))&65535)
    result,_,evidence=build(bytes(changed),plan,ANCHOR)
    # Parsed project-name field, same size; CPU/model and all other metadata
    # are preserved. The editor should identify this copy as PUMP_STATION_3.
    target=bytearray(result);size=int.from_bytes(target[0x102:0x104],'little')
    version,name_size,model_size,description_size=struct.unpack_from('<4H',target,0x104)
    if version!=1 or name_size!=14 or target[0x10c:0x10c+name_size]!=b'PUMP_STATION_4':
        raise ValueError('Unexpected source project-name field')
    target[0x10c:0x10c+name_size]=b'PUMP_STATION_3'
    struct.pack_into('<H',target,0x104+size,sum(target[0x104:0x104+size])&65535)
    result=bytes(target)
    final=layout(result)
    if final['payload']!=part['payload'] or Path(source).read_bytes()!=raw:
        raise ValueError('Data frame/source changed')
    report=dict(candidateRevision=1,installedPumps=3,configuration='fixed-three-pump-build',projectName='PUMP_STATION_3',
                sourceSHA256=SOURCE_SHA,sourceBytes=len(raw),candidateSHA256=sha(result),candidateBytes=len(result),
                insertedNetworks=len(plan),insertedProgramBytes=sum(len(bytes.fromhex(x['expectedCodeHex'])) for x in plan),
                insertionPC=next(pc for pc,label in obj['rungs'] if label==ANCHOR),
                edits=edits,networks=plan,pollRAMStart='R2900',pollRAMEnd='R3000',pollRows=rows,
                normalPollRows=14,staticROMTemplatesPreserved=9,HPRevision2Preserved=True,
                countRegisters='R2860..R2867 read-only in this fixed build',
                HPRegisters='R2868..R2883 unchanged',HMIFileModified=False,
                nativeF8Observed=False,equipmentActions=0,formatEvidence=evidence)
    return result,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if len({x.resolve() for x in (a.source,a.out,a.report)})!=3 or any(x.exists() or x.is_symlink() for x in (a.out,a.report)):
        raise ValueError('New distinct output/report files required')
    result,report=prepare(a.source)
    with a.out.open('xb') as f:f.write(result)
    with a.report.open('x',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Built fixed 3-pump offline candidate:',len(result),'bytes; SHA256',sha(result))
    print('Normal poll14 rows, HP-r2 preserved; native F8 and HMI/bench checks remain.')


if __name__=='__main__':main()
