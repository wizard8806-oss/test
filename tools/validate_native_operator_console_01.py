#!/usr/bin/env python3
"""Native UI generator, read-only runtime and source-preserving copy checks.

FPC/PowerShell execute only against synthetic local fixtures. Optional original
Editor stream-reader verification is isolated x86 emulation, not Windows GUI.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from _runtime import PWSH, SCADA_SEED, fpc, fpc_units
from build_native_operator_console_01 import ROOT, UI, build, catalog, parse_pages, Builder, PAGES_SHA, pressure_display_module
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts, hashes as _source_hashes


def hashes(root):
    return {name.replace('\\','/'):digest for name,digest in _source_hashes(root).items()}

STUB = r'''unit UiApi;
{$mode objfpc}{$H+}{$codepage utf8}
interface
uses SysUtils;
type TControl=class public Text:string;end;
 TM_Variable=class public Outer,IsGoodQuality:Boolean;Address,ComputerName,OPCServerName:string;OriginalAsInt:Int64;end;
 TM_Page=class public procedure GoToPageClient(Client:string);end;
 TM_Window=class public procedure ShowClient(Client:string);end;
 TM_TrendGroup=class public ID:Integer;end;
var __CONTROLS__:TControl;
 V:array[0..1,0..6]of TM_Variable;
 P:TM_Page;W:TM_Window;G:TM_TrendGroup;Clock:Double;
 LastClient,LastName,Notice:string;Calls,GroupID:Integer;
function GetVariableByAddress(const Address:string):TM_Variable;
function GetPageByName(const Name:string):TM_Page;
function GetWindowByName(const Name:string):TM_Window;
function GetTrendGroupByName(const Name:string):TM_TrendGroup;
function GetClientName:string;
function Now:Double;
procedure ShowMessageClient(const Client,Title,Text:string);
procedure GoToTrendsGroupClient(Client:string;ID:Integer;From_,To_:Double);
procedure GoToTrendsClient(Client:string;From_,To_:Double);
procedure GoToMessagesGroupClient(Client:string;ID:Integer);
implementation
procedure TM_Page.GoToPageClient(Client:string);begin LastClient:=Client;Inc(Calls);end;
procedure TM_Window.ShowClient(Client:string);begin LastClient:=Client;Inc(Calls);end;
function GetVariableByAddress(const Address:string):TM_Variable;
var I,J:Integer;begin Result:=nil;for I:=0 to 1 do for J:=0 to 6 do if V[I,J].Address=Address then begin Result:=V[I,J];Exit;end;end;
function GetPageByName(const Name:string):TM_Page;begin LastName:=Name;Result:=P;end;
function GetWindowByName(const Name:string):TM_Window;begin LastName:=Name;Result:=W;end;
function GetTrendGroupByName(const Name:string):TM_TrendGroup;begin LastName:=Name;Result:=G;end;
function GetClientName:string;begin Result:='ClientA';end;
function Now:Double;begin Result:=Clock/86400.0;end;
procedure ShowMessageClient(const Client,Title,Text:string);begin LastClient:=Client;Notice:=Text;end;
procedure GoToTrendsGroupClient(Client:string;ID:Integer;From_,To_:Double);begin LastClient:=Client;GroupID:=ID;Inc(Calls);end;
procedure GoToTrendsClient(Client:string;From_,To_:Double);begin LastClient:=Client;Inc(Calls);end;
procedure GoToMessagesGroupClient(Client:string;ID:Integer);begin LastClient:=Client;GroupID:=ID;Inc(Calls);end;
end.
'''


def two_stations():
    data=json.loads((UI/'catalog.json').read_text(encoding='utf8'))
    s=dict(data['stations'][0],id='station-002',name='Вторая станция',itemPrefix='codex.Device2.',commandEnabled=False)
    data['stations'].append(s)
    return data


def runtime(folder):
    b=Builder(two_stations()).build()
    names=sorted(set(re.findall(r'\b(Ui\w+|ProcessTitle)\.Text',b.module)))
    (folder/'UiApi.pas').write_text(STUB.replace('__CONTROLS__',','.join(names)),encoding='utf8')
    code='unit UiConsole;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+b.module.replace('interface','interface\nuses SysUtils,UiApi;',1)
    (folder/'UiConsole.pas').write_text(code,encoding='utf8')
    init='\n'.join(n+':=TControl.Create;' for n in names)
    callbacks='\n'.join('procedure TestClick'+str(i)+';\n'+e['body'].rsplit('end.',1)[0]+'end;' for i,e in enumerate(b.events))
    harness=r'''program VerifyUi;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,UiApi,UiConsole;
const Items:array[0..6]of string=('MapVersion','PlcAliveCounter','StationMode','PressureSourceOK','PressurePV_x100','PressureSP_x100','Vfd1FaultCode');
 Values:array[0..6]of Int64=(32,100,0,0,0,400,0);
var I,J,N,C:Integer;
procedure Check(Value:Boolean;const Why:string);begin Inc(N);if not Value then raise Exception.Create(Why);end;
procedure Tick(T:Double;A,B:Int64);begin Clock:=T;V[0,1].OriginalAsInt:=A;V[1,1].OriginalAsInt:=B;OperatorUiUpdate;end;
__CALLBACKS__
begin
 DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';
 __INIT__
 P:=TM_Page.Create;W:=TM_Window.Create;
 for I:=0 to 1 do for J:=0 to 6 do begin V[I,J]:=TM_Variable.Create;V[I,J].Outer:=True;V[I,J].IsGoodQuality:=True;V[I,J].ComputerName:='localhost';V[I,J].OPCServerName:='InSAT.ModbusOPCServer.DA';V[I,J].Address:='codex.Device'+IntToStr(I+1)+'.'+Items[J];V[I,J].OriginalAsInt:=Values[J];end;
 Tick(1000,100,100);Check(UiRow0Setpoint.Text='Нет данных','startup requires new PLC progress');
 Tick(1001,101,101);Check(UiRow0Setpoint.Text='4.0 бар','common setpoint displays live readback');
 Check(UiRow0Mode.Text='СТОП','STOP comes from PLC mode');
 Check(UiRow0Pressure.Text='Нет достоверных данных','no source is not zero');
 V[0,3].OriginalAsInt:=1;Tick(1002,102,102);Check(UiRow0Pressure.Text='0.0 бар','valid zero remains zero');
 V[0,4].OriginalAsInt:=290;OperatorUiUpdate;Check(UiRow0Pressure.Text='2.9 бар','calibrator value displays one decimal');
 V[0,4].OriginalAsInt:=294;OperatorUiUpdate;Check(UiRow0Pressure.Text='2.9 бар','presentation rounds only');
 Check(V[0,4].OriginalAsInt=294,'formatting retains raw hundredths');
 V[0,4].OriginalAsInt:=299;OperatorUiUpdate;Check(UiRow0Pressure.Text='3.0 бар','display rounding carries');
 V[0,4].IsGoodQuality:=False;Tick(1003,103,103);Check(UiRow0Pressure.Text='Нет достоверных данных','bad pressure quality hidden');
 V[0,4].IsGoodQuality:=True;V[0,4].ComputerName:='wrong';Tick(1004,104,104);Check(UiRow0Pressure.Text='Нет достоверных данных','wrong OPC endpoint rejected');V[0,4].ComputerName:='localhost';
 V[1,2].OriginalAsInt:=12;Tick(1005,105,105);Check(UiRow1Mode.Text='АВТО','second station binding independent');
 V[0,0].OriginalAsInt:=31;Tick(1006,106,106);Check(UiRow0Setpoint.Text='Нет данных','unsupported map hides values');Check(UiRow1Setpoint.Text='4.0 бар','another station stays valid');V[0,0].OriginalAsInt:=32;
 Tick(1007,107,107);Tick(1008,108,108);Tick(1015,108,115);Tick(1022,108,122);Tick(1023,108,123);Check(UiRow0Setpoint.Text='Нет данных','stale counter hidden despite fresh OPC quality');
 Tick(1040,30000,124);Check(UiRow1Setpoint.Text='Нет данных','clock gap invalidates cached freshness');Tick(1041,30001,125);Check(UiRow0Setpoint.Text='4.0 бар','new progress recovers');
 Check(V[0,5].OriginalAsInt=400,'refresh never writes setpoint');
 C:=Calls;UiGoPage('PageProcess','');Check(Calls=C,'missing caller cannot navigate every client');UiGoPage('PageProcess','ClientB');Check(LastClient='ClientB','navigation is caller-local');
 C:=Calls;UiOpenWindow(16,'ClientA');Check(Calls=C,'invalid station cannot open another window');UiOpenWindow(1,'ClientB');Check((LastName='UiWindow_station_002')and(LastClient='ClientB'),'separate window uses exact station and client');
 UiOpenTrends(0,'ClientB');Check(Notice<>'','unconfigured group explained without fake history');G:=TM_TrendGroup.Create;G.ID:=21;UiOpenTrends(1,'ClientB');Check((GroupID=21)and(LastClient='ClientB'),'native trend group resolves by name not invented ID');
 WriteLn('PASS native UI runtime assertions=',N);
end.
'''.replace('__INIT__',init).replace('__CALLBACKS__',callbacks)
    (folder/'VerifyUi.pas').write_text(harness,encoding='utf8')
    compiler=fpc();cmd=[str(compiler),'-gl','-Cr','-Co','-Fu'+str(folder),'-FE'+str(folder),'-FU'+str(folder)]+['-Fu'+str(p) for p in fpc_units(compiler)]+[str(folder/'VerifyUi.pas')]
    compiled=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    r=subprocess.run([str(folder/'VerifyUi')],text=True,capture_output=True,timeout=20)
    assert r.returncode==0,r.stdout+r.stderr
    assert not re.search(r'\.Value\s*:=|SetVariableValue|AddActionMessage',b.module)
    return r.stdout.strip()


def windows(raw):
    # Exact frame fields are from official2.6.15; GUI reading remains a local gate.
    pos=0;names=[];uids=[]
    def scalar(fmt):
        nonlocal pos
        v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=struct.calcsize('<'+fmt);return v
    def text(wide=False):
        nonlocal pos
        n=scalar('I');b=raw[pos:pos+n*(2 if wide else 1)];pos+=len(b);return b.decode('utf-16le' if wide else 'utf8')
    assert text()=='..\\' and scalar('I')==0 and scalar('I')==0
    assert text()=='..\\' and scalar('I')==0
    for i in range(scalar('I')):
        assert scalar('B')==254 and scalar('q')==i+1
        names.append(text());pos+=63;text(True)
        tail=raw[pos:pos+42];assert tail[:4]==bytes(4) and tail[9:33]==b'\xff'*24;uids.append(struct.unpack_from('<I',tail,5)[0]);pos+=42
        for _ in range(scalar('I')):
            assert scalar('H')==4;names.append(text());body=raw[pos:pos+141];uids.append(struct.unpack_from('<I',body,107)[0]);pos+=141;text(True);pos+=9
    assert pos==len(raw) and len(set(names))==len(names) and len(set(uids))==len(uids)
    return len(names)


def copies(folder,out):
    source=folder/'Current10';shutil.copytree(SCADA_SEED,source)
    for p in source.rglob('.gitkeep'):p.unlink()
    (source/'Pages.spg').write_bytes((ROOT/'source/scada-native-08/Pages.spg').read_bytes())
    rows=parse_scripts((ROOT/'source/scada-native-08/Scripts.ssc').read_bytes())
    for i,(id_,name,meta,lines) in enumerate(rows):
        path=ROOT/'artifacts/station-setpoint-click-fix-01/scripts'/(name+'.txt')
        if path.exists():rows[i]=(id_,name,meta,path.read_text(encoding='utf8').splitlines())
    (source/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(rows))
    (source/'PrivateSettings.fixture').write_text('SYNTHETIC settings retained locally')
    (source/'Scripts/Compiled').mkdir(exist_ok=True);(source/'Scripts/Compiled/cache.exs').write_bytes(b'cache')
    base=hashes(source);installer=(out/'Install-Operator-Console-01.ps1').read_text(encoding='utf8')
    for name,pinned in [('Scripts/Scripts.ssc','51cc9561bb7a2b3ad3b7068db28b860d70ef9587a4586ea27a0d0eb683e7a858'),('Variables.svr','c13c163398f114a4c8ba96a93f1355a876692a65ee3b020cf32e95bb9634fd3a'),('Servers.ssr','c0662185786f2204479c9ad90d2dcc2ed0dbb79d9d532942f1841f650ef498b6')]:
        installer=installer.replace(pinned,base[name])
    results=[]
    for case in ['normal','destination_exists','nested_destination','edited_pages','edited_scripts','edited_variables','edited_server','existing_window','wrong_version','corrupt_packet']:
        src=folder/('source-'+case);shutil.copytree(source,src);target=folder/('target-'+case)
        code=installer
        filename={'edited_pages':'Pages.spg','edited_scripts':'Scripts/Scripts.ssc','edited_variables':'Variables.svr','edited_server':'Servers.ssr','existing_window':'Windows.swn','wrong_version':'Project.spr'}.get(case)
        if filename:
            p=src/filename;raw=bytearray(p.read_bytes());raw[8 if case=='wrong_version' else -1]^=1;p.write_bytes(raw)
        if case=='destination_exists':target.mkdir();(target/'keep').write_text('preserve')
        if case=='nested_destination':target=src/'nested'
        if case=='corrupt_packet':code=code.replace("if((UiHash $packetRaw) -ne '","if((UiHash $packetRaw) -ne '00",1)
        script=folder/('install-'+case+'.ps1');script.write_text(code,encoding='utf8')
        env=dict(os.environ,XDG_CACHE_HOME=str(folder/'cache'),XDG_CONFIG_HOME=str(folder/'config'),XDG_DATA_HOME=str(folder/'data'))
        before=hashes(src)
        p=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(script),'-SourcePath',str(src),'-TargetPath',str(target)],env=env,text=True,capture_output=True,timeout=30)
        assert hashes(src)==before,(case,'source modified')
        if case=='normal':
            assert p.returncode==0 and 'SAVED:' in p.stdout,(case,p.stdout,p.stderr)
            after=hashes(target)
            for name,digest in before.items():
                if name in ['Pages.spg','Windows.swn','Scripts/Scripts.ssc'] or name.startswith('Scripts/Compiled/'):continue
                assert after[name]==digest,(case,name)
            assert not (target/'Scripts/Compiled/cache.exs').exists()
            updated=parse_scripts((target/'Scripts/Scripts.ssc').read_bytes())
            by_name={r[1]:r for r in updated}
            old_by_name={r[1]:r for r in rows}
            for row in updated[7:]:
                prototype=old_by_name['StationDiagnostics' if row[1]=='OperatorConsole' else 'ProcessSpPlus_OnClick'][2]
                assert row[2][:2]==prototype[:2] and row[2][6:9]==prototype[6:9],row[1]
                assert row[2][6]==1 and row[2][8]==0,row[1]
            assert by_name['OperatorConsole'][2][1]==16
            for a,b in zip(rows,updated[:7]):
                if a[1]=='StationDiagnosticsTimer':assert '\n'.join(b[3]).count('OperatorUiUpdate;')==1
                elif a[1]=='StationDiagnostics':assert b[3]==pressure_display_module('\n'.join(a[3]),a[1]).split('\n')
                else:assert a[3]==b[3],a[1]
            assert len({r[0] for r in updated})==len(updated)==len({r[1] for r in updated})
        else:
            assert p.returncode!=0,(case,'unexpected success')
            if case=='destination_exists':assert (target/'keep').read_text()=='preserve'
            else:assert not target.exists(),case
        results.append(dict(case=case,passed=True))
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path);parser.add_argument('--vendor-pages',action='store_true',default=os.environ.get('CODEX_PAGE_LOADER')=='1');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-operator-checks-') as tmp:
        folder=Path(tmp);out=folder/'build';result=build(out=out)
        parsed=parse_pages((out/'Pages.spg').read_bytes());assert len(parsed)==6
        assert windows((out/'Windows.swn').read_bytes())==7
        cfg=two_stations();c=folder/'catalog.json';c.write_text(json.dumps(cfg));many=build(c,folder/'multi');assert many['stationCount']==2 and many['pageCount']==7
        assert windows((folder/'multi/Windows.swn').read_bytes())==14
        expanded=two_stations()
        for n in range(3,17):expanded['stations'].append(dict(expanded['stations'][1],id=f'station-{n:03}',name=f'Станция {n}',itemPrefix=f'codex.Device{n}.'))
        c.write_text(json.dumps(expanded));large=build(c,folder/'sixteen');assert large['pageCount']==22 and windows((folder/'sixteen/Windows.swn').read_bytes())==112
        assert len({p['id'] for p in parse_pages((folder/'sixteen/Pages.spg').read_bytes())})==22
        for mutate in [lambda x:x['stations'].append(dict(x['stations'][0])),lambda x:x['stations'][0].update(password='PRIVATE_FIXTURE'),lambda x:x['stations'][1].update(commandEnabled=True)]:
            bad=two_stations();mutate(bad);c.write_text(json.dumps(bad))
            try:catalog(c)
            except ValueError:pass
            else:raise AssertionError('Invalid catalog accepted')
        logic=runtime(folder);copied=copies(folder,out)
        vendor=None
        if args.vendor_pages:
            from verify_scada_native_loader_01 import read_pages
            native=read_pages(out/'Pages.spg');assert len(native['objects'])==131
            vendor=dict(pagesReadByOriginalX86Loader=True,objects=131,GUI=False,windowFrameStructuralOnly=True)
        report=dict(date='2026-11-02',base='eb1cb9cb0fefe85dd542cbbb65a56fa4cc19a8c8',passed=True,runtime=logic,copyCases=copied,defaultPages=6,defaultNativeObjects=131,stationExpansionPassed=True,windowStructurePassed=True,vendor=vendor,noLiveConnections=True,WindowsGUIF9=False)
        if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
