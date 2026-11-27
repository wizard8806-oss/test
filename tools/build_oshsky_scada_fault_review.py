"""Extend a private Oshsky r4a review copy with read-only native fault inputs."""
import json
import re
import struct
from zipfile import ZipFile

from patch_oshsky_scada_radio_reader import pack, parse_scripts
from review_masteropc_process_tags_01 import review
from verify_scada_variable_metadata_native import Layout

TAGS = {'FaultExportVersion':3610, 'FaultExportHeartbeat':3611}
for pump in range(1,5):
    TAGS[f'Vfd{pump}FaultConfirmed'] = 3611+pump
    TAGS[f'Vfd{pump}FaultOwnFresh'] = 3615+pump
    TAGS[f'Vfd{pump}FaultSequence'] = 3623+pump


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected source at '+str(old)[:70])
    return text.replace(old,new)


def make_profile(old, new):
    before = review(old)['codex_tags']
    original = {t['path'].split('.')[-1]:t for t in before}
    assert not (TAGS.keys() & original.keys())
    assert all(str(a) not in {t['Address'] for t in before} for a in TAGS.values())
    with ZipFile(old) as source, ZipFile(new,'x') as target:
        count = 0
        for entry in source.infolist():
            raw = source.read(entry)
            if entry.filename.lower().endswith('.mbc'):
                text = raw.decode('cp1251')
                label = text.index('"Vfd1FreqRaw"')
                a = list(re.finditer(r'"tag"\s*:\s*\{',text[:label]))[-1].end()-1
                template, size = json.JSONDecoder().raw_decode(text[a:])
                assert template['Address']=='2500' and template['NameInTree']=='Vfd1FreqRaw'
                assert template['Access']=='ReadOnly' and template['TypeInDevice']=='uint16'
                assert template['EnableProgramAfterTagRead']==template['EnableProgramBeforeTagWrite']=='False'
                add = []
                for name, address in TAGS.items():
                    item = dict(template,NameInTree=name,Address=str(address))
                    add.append('"tag":'+json.dumps(item,ensure_ascii=False))
                raw = (text[:a+size]+','+','.join(add)+text[a+size:]).encode('cp1251')
                count += 1
            target.writestr(entry,raw)
    assert count==1
    after = {t['path'].split('.')[-1]:t for t in review(new)['codex_tags']}
    assert {n:after[n] for n in original} == original
    assert all(after[n]['Address']==str(a) and after[n]['Access']=='ReadOnly' for n,a in TAGS.items())


def variables(raw):
    records=Layout(raw).run().records
    first=next(v['start'] for v in records if v['name']=='codex_Device1_MapVersion')
    end=records[-1]['end']; number=struct.unpack_from('<I',raw,first-4)[0]
    assert sum(v['start']>=first for v in records)==number and raw[end:]==bytes(4)
    v=next(v for v in records if v['name']=='Vfd1FreqRaw')
    assert len({r['name'] for r in records} & TAGS.keys())==0
    ident=struct.unpack_from('<q',raw)[0]
    ids={r['id'] for r in records}
    assert not ids.intersection(range(ident,ident+len(TAGS)))
    pointer_ids={struct.unpack_from('<I',raw,r['body'])[0] for r in records}
    first_pointer=max(pointer_ids)+4
    def encoded(s,wide=False):
        return struct.pack('<I',len(s))+s.encode('utf-16-le' if wide else 'utf-8')
    items=[]
    for i,name in enumerate(TAGS):
        item=bytearray(raw[v['start']:v['end']])
        struct.pack_into('<qI',item,v['body']-v['start']-8,ident+i,first_pointer+4*i)
        item=change(bytes(item),encoded(v['name']),encoded(name))
        item=change(item,encoded(v['address'],True),encoded('codex.Device1.'+name,True))
        items.append(item)
    result=(struct.pack('<q',ident+len(items))+raw[8:first-4]+struct.pack('<I',number+len(items))
            +raw[first:end]+b''.join(items)+raw[end:])
    saved=Layout(result).run().records
    assert [a['name'] for a in saved]==[a['name'] for a in records]+list(TAGS)
    assert all(v['external'] and v['offset']==0 and not v['scaling'] for v in saved[-len(items):])
    return result


FUNCTION = """function R4OshReadFault(Index, Pump: Integer; var Code: Int64): Boolean;
var Marker, HB, Seq, SeqAfter, Quality, QualityAfter: Int64; Name: string; Valid: Boolean;
begin
  Result:=False; Code:=-1;
  if (Index<>0) or (Pump<1) or (Pump>4) then Exit;
  HB:=0;
  Valid:=R3BaseFresh and UiWord(Index,'FaultExportVersion',Marker) and (Marker=27428)
    and UiWord(Index,'FaultExportHeartbeat',HB);
  if not R3Pulse(3,Valid,HB) then Exit;
  Name:='Vfd'+IntToStr(Pump)+'Fault';
  if not UiWord(Index,Name+'Sequence',Seq) or (Seq=0) then Exit;
  if not UiWord(Index,Name+'OwnFresh',Quality) or (Quality<>1) then Exit;
  Result:=UiWord(Index,Name+'Confirmed',Code) and (Code>=0) and (Code<=65535)
    and UiWord(Index,Name+'OwnFresh',QualityAfter) and (QualityAfter=1)
    and UiWord(Index,Name+'Sequence',SeqAfter) and (SeqAfter=Seq);
  if not Result then Code:=-1;
end;
"""


def scripts(raw):
    initial=parse_scripts(raw)
    changed={}
    for row in initial:
        name=row[1]
        if name not in ('OperatorConsole','StationDiagnostics','StationDiagnosticsTimer'):continue
        old=row[3];s='\n'.join(old)
        if name=='OperatorConsole':
            at='function R3BaseFresh: Boolean;\nprocedure R4OpenTrend'
            s=change(s,at,'function R3BaseFresh: Boolean;\n'+FUNCTION.splitlines()[0]+'\nprocedure R4OpenTrend')
            for var in ('R3Primed,R3Moving','R3LastHB','R3LastTick,R3Changed'):
                s=change(s,var+': array[0..2]',var+': array[0..3]')
            at='function R3WordText(Good: Boolean;'
            s=change(s,at,FUNCTION+'\n'+at)
            s=change(s,"UiWord(Index, 'Vfd1FaultCode', Fault)",'R4OshReadFault(Index,1,Fault)')
            s=change(s,"QGood and UiWord(0,'Vfd'+Num+'FaultCode',Code)",'R4OshReadFault(0,N,Code)')
            s=change(s,'R4FaultKnown[N]:=OwnFault;', 'if OwnFault then R4FaultKnown[N]:=True;')
            # Retain frequency requirements for operating state but show an independently confirmed fault.
            a="  Result := 'Нет данных ПЧ'; if not OwnFresh then Exit;\n"
            b="  if FaultGood and (Fault>0) and (Fault<=65535) then\n  begin Result := 'Авария ПЧ: '+IntToStr(Fault); Exit; end;\n"
            s=change(s,a+b,b+a)
            a="  if not OwnFresh then Exit;\n"
            b="  if FaultGood and (Fault > 0) and (Fault <= 65535) then\n  begin Result := 'ПЧ ' + IntToStr(Pump) + ': код неисправности ' + IntToStr(Fault); Exit; end;\n"
            s=change(s,a+b,b+a)
        elif name=='StationDiagnosticsTimer':
            # The timer already calls both global units. Pass one verified sample
            # across the unit boundary without a circular compiler dependency.
            s=change(s,'begin\n  StationProcessUpdate;', 'var Code: Int64; Known: Boolean;\nbegin\n'
                     '  Known := R4OshReadFault(0,1,Code);\n  StationProcessUpdate(Known, Code);')
        else:
            old_sig='procedure StationProcessUpdate;'
            if s.count(old_sig)!=2:
                raise ValueError('Expected the interface and implementation of StationProcessUpdate')
            s=s.replace(old_sig,'procedure StationProcessUpdate(KnownFault: Boolean; Code: Int64);')
            s=change(s,"FaultGood := ProcessWord('Vfd1FaultCode', FaultRaw);",
                     'FaultGood := RouteLive and KnownFault;\n      FaultRaw := Code;')
            a=s.index('        if FaultGood then\n        begin\n          ProcessFault.Text')
            last_status = "            StatusColor := RGB(165, 50, 50);"
            block_end = '\n        end;'
            b = s.index(block_end, s.index(last_status, a)) + len(block_end)
            chunk=s[a:b]
            assert chunk.startswith('        if FaultGood') and chunk.endswith('        end;')
            s=s[:a]+s[b:]
            marker="    if LoGood and HiGood then\n      ProcessAlarmWords.Text"
            s=change(s,marker,'\n'.join(l[4:] for l in chunk.splitlines())+'\n'+marker)
        new=s.split('\n')
        raw=change(raw,pack(old),pack(new))
        changed[name]=new
    final=parse_scripts(raw)
    assert len(initial)==len(final) and all(a[:3]==b[:3] for a,b in zip(initial,final))
    assert {b[1] for a,b in zip(initial,final) if a[3]!=b[3]}==set(changed)
    return raw


def verify_saved(source, saved, source_profile, review_profile):
    """Check the native Save As, independent of Editor's in-memory model."""
    def bodies(data):
        return {r[1]: r[3] for r in parse_scripts(data)}

    source_scripts = (source / 'Scripts/Scripts.ssc').read_bytes()
    saved_scripts = (saved / 'Scripts/Scripts.ssc').read_bytes()
    expected_scripts = bodies(scripts(source_scripts))
    if bodies(saved_scripts) != expected_scripts:
        raise ValueError('Saved Pascal bodies do not match the four-pump fault changes')
    if variables((source / 'Variables.svr').read_bytes()) != (saved / 'Variables.svr').read_bytes():
        raise ValueError('Unexpected native variable table')
    compiled = (saved / 'Scripts/Compiled/program.exs').read_bytes()
    old_compiled = (source / 'Scripts/Compiled/program.exs').read_bytes()
    symbol = 'R4OshReadFault'.encode('utf-16-le')
    if compiled == old_compiled or symbol not in compiled or symbol in old_compiled:
        raise ValueError('Saved runtime does not contain the new fault reader')

    def tags(path):
        return {v['path']: v for v in review(path)['codex_tags']}

    old_tags = tags(source_profile)
    saved_tags = tags(review_profile)
    prefix = 'Server.codex.Device1.'
    if prefix + 'Vfd1FreqRaw' not in old_tags:
        raise ValueError('Source profile has no matching four-pump branch')
    expected_names = {prefix + name for name in TAGS}
    if saved_tags.keys() - old_tags.keys() != expected_names:
        raise ValueError('Unexpected OPC additions')
    if any(saved_tags.get(name) != item for name, item in old_tags.items()):
        raise ValueError('Existing OPC items changed')
    for name, address in TAGS.items():
        item = saved_tags[prefix + name]
        if item['Access'] != 'ReadOnly' or item['Address'] != str(address):
            raise ValueError('Invalid read-only fault item ' + name)
    return {
        'pascalBodies': len(expected_scripts),
        'variables': len(Layout((saved / 'Variables.svr').read_bytes()).run().records),
        'opcItems': len(saved_tags),
        'compiledBytes': len(compiled),
    }


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Verify a native r4b Save As against r4a and both review OPC profiles.')
    for name in ('source', 'saved', 'source_profile', 'review_profile'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_saved(**vars(args)), ensure_ascii=False))
