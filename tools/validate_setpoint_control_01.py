#!/usr/bin/env python3
"""Exercise operator-only writes against a mock variable, plus real copy guards."""
import json
import os
import re
import subprocess
import struct
import tempfile
from pathlib import Path

from _runtime import fpc, fpc_units, PWSH
from build_setpoint_control_01 import ROOT, BASE, OUT, EVENTS, NATIVE_PAGES, page_packet
from validate_setpoint_display_01 import fixture06
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts, hashes

STUB = r'''unit ProcessStubs;
{$mode objfpc}{$H+}{$codepage utf8}
interface
uses SysUtils,Variants;
type TControl=class public Text:string;Color:Cardinal;Enabled:Boolean;end;
 TM_MessageKind=(mkMessage,mkWarning,mkAlarm);
 TM_Variable=class
 public Good,Outer,FailRead:Boolean;Raw,Reads:Int64;Address,OPCServerName,ComputerName:string;
 DecimalOffset:ShortInt;DecimalMultiplier:Double;
 function GetOriginal:Integer;function GetValue:Variant;procedure SetValue(const AValue:Variant);
 property OriginalAsInt:Integer read GetOriginal;property IsGoodQuality:Boolean read Good;
 property Value:Variant read GetValue write SetValue;
 end;
var __CONTROLS__:TControl;
 V:array[0..20]of TM_Variable;Present:array[0..20]of Boolean;
 LookupFailure:Boolean;TestSeconds:Double;
 ActorClient,ActorName,LastNotice:string;ActorID:Int64;
 WriteCount,LogCount,NoticeCount:Integer;LastWrite:Int64;
 FailBeforeWrite,FailAfterWrite,FailJournal:Boolean;
function GetVariableByAddress(const Address:string):TM_Variable;
function RGB(R,G,B:Byte):Cardinal;
function GetClientName:string;function GetUserName:string;function GetUserID:Int64;
procedure ShowMessageClient(const Client,Title,Content:string);
procedure AddMessage(T:TDateTime;Kind:TM_MessageKind;const Content:string;Unconfirmed,Sound:Boolean);
implementation
function TM_Variable.GetOriginal:Integer;
begin Inc(Reads);if not Good or FailRead then raise Exception.Create('Bad variable read');Result:=Raw;end;
function TM_Variable.GetValue:Variant;begin Result:=Raw;end;
procedure TM_Variable.SetValue(const AValue:Variant);
begin
 if Self<>V[20] then raise Exception.Create('Write to telemetry attempted');
 if FailBeforeWrite then raise Exception.Create('Write error before send');
 Inc(WriteCount);LastWrite:=AValue;
 if FailAfterWrite then raise Exception.Create('Write error after send');
end;
function GetVariableByAddress(const Address:string):TM_Variable;
var I:Integer;
begin
 if LookupFailure then raise Exception.Create('Lookup failure');Result:=nil;
 for I:=0 to 20 do if Present[I] and (V[I].Address=Address) then begin Result:=V[I];Exit;end;
end;
function RGB(R,G,B:Byte):Cardinal;begin Result:=(Cardinal(R)shl 16)or(Cardinal(G)shl 8)or B;end;
function GetClientName:string;begin Result:=ActorClient;end;
function GetUserName:string;begin Result:=ActorName;end;
function GetUserID:Int64;begin Result:=ActorID;end;
procedure ShowMessageClient(const Client,Title,Content:string);begin Inc(NoticeCount);LastNotice:=Content;end;
procedure AddMessage(T:TDateTime;Kind:TM_MessageKind;const Content:string;Unconfirmed,Sound:Boolean);
begin if FailJournal then raise Exception.Create('Journal unavailable');Inc(LogCount);end;
end.
'''

HARNESS = r'''program CheckControl;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,ProcessStubs,ProcessCard;
const Items:array[0..20]of string=('MapVersion','PressurePV_x100','PressureSourceOK',
 'PressureSP_x100','Vfd1FreqRaw','Vfd1FreqState','AlarmLo','AlarmHi','Vfd1NativeState',
 'Vfd1CurrentRaw','Vfd1FaultCode','PlcAliveCounter','StationMode','SpFeedbackVersion',
 'SpConfirmedDrive','SpConfirmed_x100','SpApplyPhase','SpApplyError','SpApplyDetail',
 'SpApplyFlags','PressureSP_Command');
 Values:array[0..20]of Int64=(32,345,1,350,0,1,7624,1792,3,0,0,0,0,1,1,350,0,0,0,0,350);
var I,J,N:Integer;
procedure Check(B:Boolean;const Why:string);begin Inc(N);if not B then raise Exception.Create(IntToStr(N)+' '+Why);end;
procedure Fresh;
var K:Integer;
begin
 TestControlReset;TestSeconds:=0;LookupFailure:=False;ActorClient:='ClientA';ActorName:='OperatorA';ActorID:=1;
 WriteCount:=0;LastWrite:=0;LogCount:=0;NoticeCount:=0;FailBeforeWrite:=False;FailAfterWrite:=False;FailJournal:=False;
 for K:=0 to 20 do begin
  Present[K]:=True;V[K].Good:=True;V[K].Outer:=True;V[K].FailRead:=False;V[K].Raw:=Values[K];V[K].Reads:=0;
  V[K].Address:='codex.Device1.'+Items[K];V[K].OPCServerName:='InSAT.ModbusOPCServer.DA';V[K].ComputerName:='localhost';
  V[K].DecimalOffset:=0;V[K].DecimalMultiplier:=1.0;
 end;
end;
procedure Tick(T:Double;C:Int64);begin TestSeconds:=T;V[11].Raw:=C;StationProcessUpdate;end;
procedure Prime;begin Fresh;Tick(0,0);Tick(1,1);Tick(2,2);end;
procedure WritePlus;begin StationSpAdjust(10);StationSpApply;end;
begin
 DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';N:=0;
 for I:=0 to 20 do V[I]:=TM_Variable.Create;
 __CREATE_CONTROLS__
 Prime;
 for I:=3 to 100 do Tick(I,I);
 Check((WriteCount=0)and(LogCount=0),'startup and timer never write or flood journal');
 Prime;StationSpAdjust(10);Tick(2.1,2);
 Check(ProcessSpDraft.Text='3.6','draft plus step');Check(WriteCount=0,'editing is not writing');
 StationSpCancel;Tick(2.2,2);Check(ProcessSpDraft.Text='3.5','cancel restores displayed PLC input');
 Check(WriteCount=0,'cancel performs no rollback write');
 Prime;StationSpApply;Check(WriteCount=0,'apply without draft writes nothing');
 Prime;StationSpAdjust(10);StationSpAdjust(-10);StationSpApply;
 Check((WriteCount=0)and(LogCount=0),'unchanged target sends no new command');
 Prime;ActorID:=-1;WritePlus;Check(WriteCount=0,'server/unauthorized callback blocked');
 Prime;ActorClient:='';WritePlus;Check(WriteCount=0,'no caller client blocked');
 Prime;StationSpAdjust(10);ActorClient:='ClientB';ActorID:=2;ActorName:='OperatorB';
 StationSpAdjust(-10);StationSpApply;StationSpCancel;
 Check(WriteCount=0,'another client cannot apply or cancel draft');
 ActorClient:='ClientA';ActorID:=1;ActorName:='OperatorA';StationSpApply;
 Check((WriteCount=1)and(LastWrite=360),'owner submits exactly one raw write');
 StationSpApply;StationSpCancel;StationSpAdjust(10);Check(WriteCount=1,'pending requests cannot duplicate or undo write');
 V[3].Raw:=360;Tick(3,3);Tick(4,4);
 Check(Pos('ПЛК принял',ProcessMainScope.Text)=0,'mirror alone without R2100 readback is not accepted');
 V[20].Raw:=360;Tick(5,5);
 Check(Pos('ПЛК принял',ProcessMainScope.Text)=0,'single echo is not accepted');
 Tick(6,6);Check(Pos('ПЛК принял',ProcessMainScope.Text)>0,'two post-submit echoes accept PLC input');
 Check(ProcessMainScope.Color<>RGB(40,140,90),'PLC echo alone is not drive success');
 V[15].Raw:=360;V[19].Raw:=2;Tick(7,7);Tick(8,8);
 Check(Pos('подтверждена ПЛК и ведущим ПЧ',ProcessMainScope.Text)>0,'separate drive feedback completes value result');
 Check(ProcessMainScope.Color=RGB(40,140,90),'verified result green');
 Check((WriteCount=1)and(LogCount=3),'request, PLC acceptance and final result logged once');
 for I:=9 to 15 do Tick(I,I);
 Check((WriteCount=1)and(LogCount=3),'no timer replay or journal flood after completion');
 for I:=16 to 30 do Tick(I,15);
 Check(ProcessMainScope.Color<>RGB(40,140,90),'stale connection cannot present historical result as current green');
 Check(WriteCount=1,'freeze never triggers resend');
 Prime;WritePlus;
 for I:=3 to 23 do Tick(I,I);
 Check(Pos('20 с не подтверждён',ProcessMainScope.Text)>0,'missing echo times out');
 V[3].Raw:=360;V[20].Raw:=360;V[15].Raw:=360;V[19].Raw:=2;
 for I:=24 to 30 do Tick(I,I);
 Check(WriteCount=1,'late recovery never retries');
 Check(Pos('подтверждена ПЛК и ведущим ПЧ',ProcessMainScope.Text)=0,'late data do not rewrite unconfirmed request history');
 Prime;WritePlus;V[3].Raw:=360;V[20].Raw:=360;Tick(3,3);Tick(4,4);
 for I:=5 to 50 do Tick(I,I);
 Check(Pos('ПЛК принял 3.60 бар; подтверждение ПЧ пока не получено',ProcessMainScope.Text)>0,'STOP can accept stored setpoint without drive confirmation');
 Check((WriteCount=1)and(ProcessMainScope.Color<>RGB(40,140,90)),'no success green or replay when drive unconfirmed');
 Prime;StationSpAdjust(10);V[3].Raw:=370;V[20].Raw:=370;StationSpApply;
 Check(WriteCount=0,'external input change during editing cancels stale draft');
 Prime;WritePlus;V[3].Raw:=360;V[20].Raw:=360;Tick(3,3);Tick(4,4);
 V[3].Raw:=370;V[20].Raw:=370;Tick(5,5);
 Check(Pos('снова изменилась',ProcessMainScope.Text)>0,'external change after acceptance is not overwritten');
 Check(WriteCount=1,'no implicit reapply after external change');
 Prime;WritePlus;V[11].Good:=False;Tick(3,3);
 Check(Pos('потеряны подтверждённые данные',ProcessMainScope.Text)>0,'lost route leaves result unconfirmed');
 V[11].Good:=True;Tick(4,4);Tick(5,5);Check(WriteCount=1,'quality recovery does not replay');
 Prime;FailBeforeWrite:=True;WritePlus;Check(WriteCount=0,'pre-send error does not write');
 Check(Pos('Результат ПЛК не подтверждён',ProcessMainScope.Text)=0,'UI refresh is separate from caller');Tick(3,3);
 Check(Pos('Результат ПЛК не подтверждён',ProcessMainScope.Text)>0,'write error explicitly unconfirmed');
 Prime;FailAfterWrite:=True;WritePlus;Check(WriteCount=1,'ambiguous after-send failure counted once');
 FailAfterWrite:=False;for I:=3 to 10 do Tick(I,I);Check(WriteCount=1,'ambiguous send failure no retry');
 Prime;FailJournal:=True;WritePlus;Check(WriteCount=0,'cannot journal requested action: no command');
 Prime;WritePlus;FailJournal:=True;V[3].Raw:=360;V[20].Raw:=360;Tick(3,3);Tick(4,4);
 Check(WriteCount=1,'post-write journal failure does not resend');Check(Pos('Журнал результата недоступен',ProcessMainScope.Text)>0,'journal failure visible');
 Prime;StationSpAdjust(10);for I:=3 to 63 do Tick(I,I);StationSpApply;Check(WriteCount=0,'expired draft never applied');
 Prime;StationSpAdjust(10);Tick(-1,3);StationSpApply;Check(WriteCount=0,'backward clock invalidates draft');
 Prime;StationSpAdjust(10);ActorID:=2;StationSpApply;Check(WriteCount=0,'different login on same client cannot reuse draft');
 for I:=0 to 20 do begin
  if (I=0)or(I=3)or(I=11)or(I>=12) then begin
   Prime;V[I].Good:=False;WritePlus;Check(WriteCount=0,'bad required binding blocks command');
  end;
 end;
 for I:=0 to 5 do begin
  Prime;
  case I of
   0:V[20].Outer:=False;
   1:V[20].ComputerName:='OtherHost';
   2:V[20].OPCServerName:='OtherServer';
   3:V[20].DecimalOffset:=2;
   4:V[20].DecimalMultiplier:=0.01;
   5:V[20].FailRead:=True;
  end;
  WritePlus;Check(WriteCount=0,'foreign/scaled/unreadable command binding rejected');
 end;
 Prime;Present[20]:=False;WritePlus;Check(WriteCount=0,'missing command tag stays read only');
 Prime;V[0].Raw:=31;WritePlus;Check(WriteCount=0,'old map blocks writes');
 Prime;V[13].Raw:=0;WritePlus;Check(WriteCount=0,'missing feedback contract blocks writes');
 Prime;V[12].Raw:=90;WritePlus;Check(WriteCount=0,'invalid selector blocks write');
 Prime;V[19].Raw:=3;WritePlus;Check(WriteCount=0,'contradictory feedback blocks write');
 Prime;V[20].Raw:=340;WritePlus;Check(WriteCount=0,'disagreeing R2100 and mirror block write');
 Prime;V[3].Raw:=10;V[20].Raw:=10;StationSpAdjust(-10);StationSpApply;Check(WriteCount=0,'cannot go below profile');
 Prime;V[3].Raw:=1190;V[20].Raw:=1190;StationSpAdjust(10);StationSpApply;Check(WriteCount=0,'cannot exceed profile');
 Prime;StationSpAdjust(1);StationSpApply;Check(WriteCount=0,'arbitrary step rejected');
 Prime;V[2].Raw:=0;WritePlus;Check((WriteCount=1)and(LastWrite=360),'stored setpoint separate from pressure validity; PLC interlocks retained');
 Prime;WritePlus;V[3].Raw:=360;V[20].Raw:=360;Tick(3,3);Tick(4,4);
 V[19].Raw:=1;V[17].Raw:=27;V[18].Raw:=9;Tick(5,5);Tick(6,6);
 Check(Pos('ошибка применения',ProcessMainScope.Text)>0,'coordinator apply error is shown');
 Check(ProcessFault.Text='Код 0','coordinator error not a native VFD fault');Check(WriteCount=1,'apply error never retried');
 WriteLn('PASS operator control assertions=',N);
end.
'''


def run_logic(harness=HARNESS):
    text=(OUT/'scripts/StationDiagnostics.txt').read_text()
    assert text.count('Command.Value := Integer(SpControlTarget);')==1
    assert text.count('Now * 86400.0')==1
    controls=sorted(set(re.findall(r'\b(Process\w+)\.(?:Text|Color|Enabled)\s*:=',text)))
    stub=STUB.replace('__CONTROLS__',','.join(controls))
    text=text.replace('Now * 86400.0','TestSeconds')
    text=text.replace('interface\n','interface\nuses SysUtils,ProcessStubs;\nprocedure TestControlReset;\n',1)
    reset='''procedure TestControlReset;
begin
 RouteFreshReset;SpFeedbackReset;SpControlClearDraft;
 SpControlStage:=0;SpControlText:='';SpControlSerial:=0;SpControlLogLost:=False;
 SpEchoSeen:=False;SpDraftTick:=0;SpControlTick:=0;
end;
'''
    at=text.rfind('\nend.');text=text[:at]+'\n'+reset+text[at:]
    creation='\n'.join(x+':=TControl.Create;' for x in controls)
    harness=harness.replace('__CREATE_CONTROLS__',creation).replace('__CONTROLS__',creation)
    with tempfile.TemporaryDirectory(prefix='sp-control-logic-') as name:
        p=Path(name);(p/'ProcessStubs.pas').write_text(stub);(p/'ProcessCard.pas').write_text('unit ProcessCard;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+text);(p/'check.pas').write_text(harness)
        compiler=fpc();cmd=[str(compiler),'-gl','-Cr','-Co','-Fu'+str(p),'-FU'+str(p),'-FE'+str(p)]+['-Fu'+str(x) for x in fpc_units(compiler)]
        r=subprocess.run(cmd+[str(p/'check.pas')],capture_output=True,text=True,timeout=30);assert r.returncode==0,r.stdout+r.stderr
        r=subprocess.run([str(p/'check')],capture_output=True,text=True,timeout=20);assert r.returncode==0,r.stdout+r.stderr
        return r.stdout.strip()


def legacy_checks():
    from validate_process_display_01 import HARNESS as OLD
    from validate_station_freshness_03 import FRESH_HARNESS
    from validate_station_mode_display_01 import MODE_CASES
    from validate_setpoint_display_01 import FEEDBACK_CASES, EXTRA_ITEMS
    legacy=OLD.replace('Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;','Fresh;V[0].Raw:=33;StationProcessUpdate;UnknownPressure;')
    # Old harnesses intentionally have no command-tag fixture; this must remain read only.
    reports=[run_logic(legacy)]
    text=FRESH_HARNESS.replace('array[0..11]','array[0..19]').replace('for K:=0 to 11','for K:=0 to 19').replace('for I:=0 to 11','for I:=0 to 19')
    text=text.replace("'PlcAliveCounter');","'PlcAliveCounter',"+EXTRA_ITEMS+');')
    text=text.replace('7624,1792,3,0,0,0);','7624,1792,3,0,0,0,10,1,1,350,0,0,0,0);').replace('var I,N,S,A:Integer;','var I,J,N,S,A:Integer;')
    text=text.replace(" WriteLn('PASS freshness assertions=',N);",MODE_CASES+FEEDBACK_CASES+"\n Check(WriteCount=0,'all prior read-only behavior sends no command');\n WriteLn('PASS prior display assertions=',N);")
    reports.append(run_logic(text));return reports


def fixture07(folder):
    records=fixture06(folder);records[0]=(*records[0][:3],BASE.read_text().splitlines())
    (folder/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records));return records


def page_preservation():
    # Independent file-slice checks: preserve all old records, apart from the
    # intentionally moved footer and the first page's object count.
    for source in [None, NATIVE_PAGES.read_bytes()]:
        before, after, _ = page_packet(source)
        first = before.index(b'\x04\x00\x0c\x00\x00\x00ProcessTitle')
        assert struct.unpack_from('<I', before, first-4)[0] == 20
        assert struct.unpack_from('<I', after, first-4)[0] == 26
        assert before[:first-4] == after[:first-4]
        name = b'ProcessMainScope'
        marker = struct.pack('<HI',4,len(name))+name
        footer = before.index(marker) + len(marker)
        caption_size = struct.unpack_from('<I', before, footer+141)[0]
        page_end = footer+141+4+caption_size*2+9
        expected = bytearray(before[first:page_end])
        struct.pack_into('<4f', expected, footer-first+8, 32,850,1376,34)
        struct.pack_into('<f', expected, footer-first+32, .66)
        assert bytes(expected) == after[first:page_end]
        # Whole Diagnostics page remains byte-identical, including native UIDs.
        second = b'\x0f\x00\x00\x00PageDiagnostics'
        second_offset = after.index(second, page_end)
        assert before[page_end:] == after[second_offset:]
    print('PASS page preservation: both variants, all prior objects and diagnostic page')


def copies():
    results=[];installer=(OUT/'Install-Setpoint-Control-01.ps1').read_text()
    for case in ['normal','native_saved','unit_header','changed_radio','changed_core','changed_pages','changed_native_layout','changed_native_uid','wrong_timer','destination_exists','wrong_version','corrupt_bundle']:
        with tempfile.TemporaryDirectory(prefix='sp-control-copy-') as name:
            p=Path(name);src=p/'Current source';dst=p/'Desktop/codex_diag_08';dst.parent.mkdir();rows=fixture07(src)
            native = case in ['native_saved','changed_native_layout','changed_native_uid']
            if native:(src/'Pages.spg').write_bytes(NATIVE_PAGES.read_bytes())
            if case=='unit_header':rows=[(uid,n,meta[:9]+bytes.fromhex('070000000c000000'),['unit '+n+';']+lines if n!='StationDiagnosticsTimer' else lines) for uid,n,meta,lines in rows]
            if case=='changed_radio':r=rows[1];rows[1]=(*r[:3],[s.replace('RadioPublishedUnix','RadioPublishedSeconds') for s in r[3]])
            if case=='changed_core':r=rows[0];rows[0]=(*r[:3],r[3]+['// keep user modification'])
            if case=='wrong_timer':r=rows[2];rows[2]=(*r[:3],['begin','end.'])
            (src/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(rows))
            if case=='changed_pages':(src/'Pages.spg').write_bytes((src/'Pages.spg').read_bytes()+b'changed')
            if case in ['changed_native_layout','changed_native_uid']:
                b=bytearray((src/'Pages.spg').read_bytes());b[217 if case=='changed_native_layout' else 316]^=1
                (src/'Pages.spg').write_bytes(b)
            if case=='wrong_version':b=bytearray((src/'Project.spr').read_bytes());b[10]=7;(src/'Project.spr').write_bytes(b)
            if case=='destination_exists':dst.mkdir();(dst/'keep.txt').write_text('preserve existing project')
            before=hashes(src);old_dest=hashes(dst) if dst.exists() else None
            code=re.sub(r'^\$processTarget=.*$',lambda _:"$processTarget='"+str(dst)+"'",installer,count=1,flags=re.M)
            code=re.sub(r'\$candidates=@\(.*?\n    \)',lambda _:"$candidates=@('"+str(src)+"')",code,count=1,flags=re.S)
            if case=='corrupt_bundle':code=code.replace("$controlBundle='","$controlBundle='AAAA",1)
            runner=p/'run.ps1';runner.write_text(code);env=dict(os.environ,XDG_CACHE_HOME=str(p/'cache'),XDG_CONFIG_HOME=str(p/'config'),XDG_DATA_HOME=str(p/'data'))
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=25);assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            assert hashes(src)==before
            if case in ['normal','native_saved','unit_header','changed_radio']:
                assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                new=parse_scripts((dst/'Scripts/Scripts.ssc').read_bytes());assert len(new)==7
                assert new[0][3]==(OUT/'scripts/StationDiagnostics.txt').read_text().splitlines();assert new[1:3]==rows[1:]
                for index,(obj,_) in enumerate(EVENTS):
                    row=new[3+index];assert row[0]==3+index and row[1]==obj+'_OnClick' and row[2][:2]==bytes([1,0]);assert row[3]==(OUT/'scripts'/(obj+'_OnClick.txt')).read_text().splitlines()
                expected_pages=OUT/('Pages-native07.spg' if native else 'Pages.spg')
                assert (dst/'Pages.spg').read_bytes()==expected_pages.read_bytes()
                for rel,digest in before.items():
                    if rel in ['Pages.spg','Scripts/Scripts.ssc'] or rel.startswith('Scripts/Compiled/'):continue
                    assert hashes(dst)[rel]==digest,(case,rel)
                assert not list((dst/'Scripts/Compiled').iterdir())
            else:
                assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout,(case,r.stdout)
                assert hashes(dst)==old_dest if old_dest is not None else not dst.exists()
            assert not list(dst.parent.glob('*.stage-*'))
            results.append(dict(case=case,passed=True));print('PASS control copy',case,flush=True)
    return results


def main():
    page_preservation()
    logic=run_logic();print(logic,flush=True);legacy=legacy_checks()
    for result in legacy:print(result,flush=True)
    cases=copies()
    report=dict(date='2026-10-31',logic=logic,legacyReports=legacy,copyCases=cases,realFieldWrites=False,nativeNewF9Observed=False,scope='Actual Pascal with mock command variable, native documented API seams and real PowerShell/Linux copy/preservation; no PLC connection')
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
