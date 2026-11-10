#!/usr/bin/env python3
"""Reviewed SKTool7.1 digital-alarm definitions and companion name directory.

Validated against the user's native two-group sample. The editor stores
N definitions AND N Bxx names plus N empty four-byte companion entries
before the scene-index map. The companion entries are kept opaque; no
semantics are inferred from their observed zero representation.
This bounded schema check is not the native editor/Compile.
"""
import struct
from skm_project_header import read_project_header

SK_SERIES_DIGITAL_GROUP_LIMIT = 10


def qs(value):
    data=value.encode('utf-16-be');return struct.pack('>I',len(data))+data


class Reader:
    def __init__(self,raw,position=0):self.raw=raw;self.position=position
    def take(self,n):
        if n<0 or self.position+n>len(self.raw):raise ValueError('Truncated alarm stream at '+str(self.position))
        data=self.raw[self.position:self.position+n];self.position+=n;return data
    def u32(self):return struct.unpack('>I',self.take(4))[0]
    def string(self):
        n=self.u32()
        if n==0xffffffff:return None
        if n%2 or n>1048576:raise ValueError('Invalid alarm QString length')
        return self.take(n).decode('utf-16-be')
    def count(self,maximum=4096):
        n=self.u32()
        if n>maximum:raise ValueError('Unbounded alarm vector')
        return n


def read_definitions(raw,start=None):
    if start is None:
        anchor=qs('События станции')
        if raw.count(anchor)!=1:raise ValueError('Original alarm group anchor differs')
        start=raw.index(anchor)-11
    stream=Reader(raw,start);count=stream.count(200);groups=[]
    if count<1:raise ValueError('No original digital alarm group')
    for index in range(count):
        first=stream.position;size,offset=struct.unpack('>HH',stream.take(4))
        if not 1<=size<=4096:raise ValueError('Invalid digital alarm size')
        flags=stream.take(3);name=stream.string()
        if not name:raise ValueError('Empty digital alarm group name')
        keyboard_start=stream.position;address=stream.string();protocol=stream.take(3)
        number,prefix=stream.string(),stream.string();word_type=stream.take(1)[0]
        if not address or number is None or not prefix:raise ValueError('Invalid alarm address')
        keyboard_end=stream.position;vectors=[]
        for _ in range(2):
            length=stream.count();values=stream.take(length)
            if length!=size or any(value not in (0,1) for value in values):raise ValueError('Alarm flag vector does not match size')
            vectors.append(values)
        languages=stream.count(32);messages=[]
        if not languages:raise ValueError('No alarm message language')
        for _ in range(languages):
            length=stream.count()
            if length!=size:raise ValueError('Alarm message vector does not match size')
            messages.append([stream.string() for _ in range(length)])
        key_count=stream.count(32);keys=[stream.string() for _ in range(key_count)]
        if key_count!=languages:raise ValueError('Alarm language keys do not match messages')
        groups.append(dict(index=index,start=first,end=stream.position,size=size,offset=offset,
            flags=flags,name=name,address=address,protocol=protocol,number=number,prefix=prefix,
            wordType=word_type,keyboardStart=keyboard_start,keyboardEnd=keyboard_end,
            vectors=vectors,messages=messages,keys=keys))
    return dict(start=start,end=stream.position,count=count,groups=groups)


def directory_bytes(names):
    if not names or len(names)>200:raise ValueError('Invalid alarm directory count')
    return b''.join(qs('B%02d:%s'%(index,name)) for index,name in enumerate(names))+b'\0'*(4*len(names))


def read_directory_for_names(raw,names):
    if not names:raise ValueError('No alarm directory names')
    anchor=qs('B00:'+names[0])
    if raw.count(anchor)!=1:raise ValueError('Alarm directory anchor differs')
    first=raw.index(anchor);stream=Reader(raw,first);entries=[]
    for index,name in enumerate(names):
        expected='B%02d:%s'%(index,name);actual=stream.string()
        if actual!=expected:raise ValueError('Alarm directory entry%d missing/different: expected %r, got %r'%(index,expected,actual))
        entries.append(actual)
    companion=stream.take(4*len(names))
    if companion!=b'\0'*(4*len(names)):raise ValueError('Unreviewed alarm directory companion records')
    end=stream.position;pages=read_project_header(raw)['pageCount'];map_count=stream.count(1000)
    if map_count!=pages:raise ValueError('Alarm directory end does not align with scene map')
    pairs=[struct.unpack('>II',stream.take(8)) for _ in range(map_count)]
    if pairs!=[(i,i) for i in range(pages-1,-1,-1)]:raise ValueError('Scene-index map after alarm directory differs')
    return dict(start=first,end=end,entries=entries,companionCount=len(names),sceneMapStart=end,
                sceneMapCount=map_count,sceneMapEnd=stream.position)


def validate_alarm_catalog(raw):
    definitions=read_definitions(raw);names=[g['name'] for g in definitions['groups']]
    directory=read_directory_for_names(raw,names)
    return dict(groupCount=definitions['count'],directoryCount=len(directory['entries']),
                names=names,directory=directory,definitions=definitions)


def require_sk_group_limit(count):
    # The supplied SKTool English help (Digital alarm login) documents ten
    # digital groups for SK-series panels. Keep structural parsing separate:
    # it must still read/reject/repair the historical thirteen-group files.
    if not 1 <= count <= SK_SERIES_DIGITAL_GROUP_LIMIT:
        raise ValueError('SK-series digital alarm group limit is 10; got '+str(count))


def compact_fault_definitions(raw):
    """Merge reviewed 32+32+16 bit ranges into 80 bits per drive: 13 -> 7.

    R3056..3070 already hold three contiguous five-word masks. Addresses,
    flags, language keys and every message/bit mapping stay unchanged. The
    original station group and each unknown-code group are copied verbatim.
    """
    parsed=read_definitions(raw,0);groups=parsed['groups']
    if parsed['end']!=len(raw) or parsed['count']!=13 or groups[0]['name']!='События станции':
        raise ValueError('Expected exact thirteen-group fault definition layout')
    u32=lambda value:struct.pack('>I',value)
    rows=[raw[groups[0]['start']:groups[0]['end']]]
    for drive in (1,2,3):
        parts=groups[1+4*(drive-1):4+4*(drive-1)];unknown=groups[4*drive]
        first=parts[0];base=3056+5*(drive-1)
        for part,(start,size) in zip(parts,((1,32),(33,32),(65,16))):
            if (part['name']!='ПЧ%d коды %d..%d'%(drive,start,start+size-1)
                or part['size']!=size or part['address']!='R'+str(base+(start-1)//16)
                or part['number']!=str(base+(start-1)//16)
                or part['prefix']!='R' or part['protocol']!=bytes((1,6,1))
                or part['wordType']!=1 or part['flags']!=bytes((0,1,1))
                or part['offset']!=0 or part['keys']!=first['keys']):
                raise ValueError('Fault range/flags/language differs')
        if unknown['name']!='ПЧ%d неизвестный код'%drive or unknown['size']!=1 or unknown['address']!='R'+str(3070+drive):
            raise ValueError('Unknown-code range differs')
        messages=[[message for part in parts for message in part['messages'][language]]
                  for language in range(len(first['keys']))]
        if any(message is None for language in messages for message in language):
            raise ValueError('Unexpected null fault message')
        merged=struct.pack('>HH',80,0)+first['flags']+qs('ПЧ%d коды 1..80'%drive)
        merged+=raw[first['keyboardStart']:first['keyboardEnd']]
        for index in range(2):merged+=u32(80)+b''.join(part['vectors'][index] for part in parts)
        merged+=u32(len(messages))+b''.join(u32(80)+b''.join(map(qs,language)) for language in messages)
        merged+=u32(len(first['keys']))+b''.join(map(qs,first['keys']))
        rows.extend((merged,raw[unknown['start']:unknown['end']]))
    result=u32(7)+b''.join(rows);checked=read_definitions(result,0)
    require_sk_group_limit(checked['count'])
    if checked['end']!=len(result):raise ValueError('Compacted definition boundary differs')
    return result


def word_bit_semantics(definitions):
    """Independent address/bit/message mapping for the reviewed R-word mode."""
    result={}
    for group in read_definitions(definitions,0)['groups']:
        if group['prefix']!='R' or group['flags']!=bytes((0,1,1)) or group['wordType']!=1:
            raise ValueError('Unreviewed alarm addressing mode')
        for index in range(group['size']):
            key=(int(group['number'])+index//16,index%16)
            if key in result:raise ValueError('Overlapping alarm bits')
            result[key]=(group['offset'],group['protocol'],
                tuple(v[index] for v in group['vectors']),tuple(group['keys']),
                tuple(language[index] for language in group['messages']))
    return result
