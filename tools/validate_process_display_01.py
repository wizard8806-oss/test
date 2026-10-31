#!/usr/bin/env python3
"""Exercise read-only card behavior, native record loading, and copy delivery.

Windows UI/F9 and live process telemetry are deliberately not claimed.
"""
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
from _runtime import PWSH as PWSH_RUNTIME
import base64, gzip, hashlib, json, os, re, shutil, struct, subprocess, tempfile
from pathlib import Path
from build_process_display_01 import ROOT, OUT, SOURCE, sha
from build_radio_display_01 import bootstrap
from validate_radio_install_01 import parse_scripts, hashes

PWSH = PWSH_RUNTIME
SCRIPT_SOURCE = OUT / 'scripts/StationDiagnostics.txt'

STUB = r'''unit ProcessStubs;
{$mode objfpc}{$H+}{$codepage utf8}
interface
uses SysUtils;
type
 TControl=class public Text:string; Color:Cardinal;end;
 TM_Variable=class
 public Good,Outer,FailRead:Boolean; Raw,Reads:Int64; Address,OPCServerName,ComputerName:string;
 function GetOriginal:Integer;
 property IsGoodQuality:Boolean read Good;
 property OriginalAsInt:Integer read GetOriginal;
 end;
var
 ProcessPressure,ProcessPressureNote,ProcessSetpoint,ProcessFrequency,
 ProcessFrequencyNote,ProcessCurrent,ProcessFault,ProcessCurrentNote,
 ProcessFaultNote,ProcessValidity,ProcessAlarmWords,ProcessFreshness,
 ProcessStatus,ProcessDetail,ProcessOPC,ProcessMap:TControl;
 V:array[0..7]of TM_Variable; Present:array[0..7]of Boolean;
 LookupFailure:Boolean; Lookups:Integer;
function GetVariableByAddress(const Address:string):TM_Variable;
function RGB(R,G,B:Byte):Cardinal;
implementation
function TM_Variable.GetOriginal:Integer;
begin
 Inc(Reads);if not Good then raise Exception.Create('Read attempted on BAD quality');
 if FailRead then raise Exception.Create('Fixture read failure');Result:=Raw;
end;
function GetVariableByAddress(const Address:string):TM_Variable;
var I:Integer;
begin
 Inc(Lookups);if LookupFailure then raise Exception.Create('Fixture lookup failure');
 Result:=nil;
 for I:=0 to 7 do if Present[I] and (V[I].Address=Address) then begin Result:=V[I];Exit;end;
end;
function RGB(R,G,B:Byte):Cardinal;
begin Result:=(Cardinal(R) shl 16) or (Cardinal(G) shl 8) or B;end;
end.
'''

HARNESS = r'''program CheckProcess;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,ProcessStubs,ProcessCard;
var N,I,J:Integer;R:Int64;BeforeText:string;
const Items:array[0..7]of string=('MapVersion','PressurePV_x100','PressureSourceOK',
 'PressureSP_x100','Vfd1FreqRaw','Vfd1FreqState','AlarmLo','AlarmHi');
 Values:array[0..7]of Int64=(31,0,0,350,0,1,7624,8960);
procedure Check(B:Boolean;const S:string);
begin Inc(N);if not B then raise Exception.Create(IntToStr(N)+' '+S);end;
procedure Fresh;
var K:Integer;
begin
 LookupFailure:=False;
 for K:=0 to 7 do begin
  Present[K]:=True;V[K].Good:=True;V[K].Outer:=True;V[K].FailRead:=False;
  V[K].Address:='codex.Device1.'+Items[K];V[K].OPCServerName:='InSAT.ModbusOPCServer.DA';
  V[K].ComputerName:='localhost';V[K].Raw:=Values[K];V[K].Reads:=0;
 end;
end;
procedure UnknownPressure;
begin Check(Pos('бар',ProcessPressure.Text)=0,'invalid pressure must hide numeric value');end;
begin
 DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';N:=0;
 for I:=0 to 7 do V[I]:=TM_Variable.Create;
 __CONTROLS__
 Fresh;StationProcessUpdate;
 Check(ProcessPressure.Text='Нет достоверных данных','actual observed missing source');
 Check(ProcessSetpoint.Text='3.50 бар','setpoint factor100');
 Check(ProcessFrequency.Text='0.0 Гц','zero frequency valid');
 Check(Pos('7624 / 8960',ProcessAlarmWords.Text)>0,'raw alarm words');
 Check(ProcessCurrent.Text='Не подключён','absent current is not zero');
 Check(ProcessFault.Text='Не подключён','absent native fault is not no-fault');
 Check(Pos('нет достоверного',ProcessStatus.Text)>0,'PLC pressure state drives banner');
 Check(ProcessStatus.Color<>RGB(40,140,90),'GOOD is not green station health');
 V[2].Raw:=1;StationProcessUpdate;
 Check(ProcessPressure.Text='0.00 бар','valid zero is not sensor failure');
 Check(ProcessValidity.Color=RGB(40,140,90),'PLC flag preserved');
 V[1].Raw:=345;V[4].Raw:=437;V[5].Raw:=2;StationProcessUpdate;
 Check(ProcessPressure.Text='3.45 бар','pressure division100');
 Check(ProcessFrequency.Text='43.7 Гц','900G manual factor10');
 BeforeText:=ProcessPressure.Text;
 for I:=1 to 300 do StationProcessUpdate;
 Check(ProcessPressure.Text=BeforeText,'unchanged pressure does not imply freeze');
 Check(Pos('30 с',ProcessStatus.Text)=0,'no CL50S freeze rule');
 for I:=0 to 7 do begin
  Fresh;Present[I]:=False;StationProcessUpdate;
  if I<=2 then UnknownPressure;
  if I=3 then Check(ProcessSetpoint.Text='Нет данных','missing SP');
  if (I=4)or(I=5) then Check(ProcessFrequency.Text='Нет данных','missing freq');
  if (I=6)or(I=7) then Check(Pos('нет данных',ProcessAlarmWords.Text)>0,'partial alarm snapshot');
 end;
 for I:=0 to 7 do begin
  Fresh;V[I].Good:=False;StationProcessUpdate;
  Check(V[I].Reads=0,'BAD quality is never converted');
  if I<=2 then UnknownPressure;
 end;
 for J:=0 to 4 do begin
  Fresh;
  case J of
   0:V[1].Outer:=False;
   1:V[1].ComputerName:='OtherCityServer';
   2:V[1].OPCServerName:='Other.Server';
   3:V[1].Address:='OtherStation.Device1.PressurePV_x100';
   4:V[1].FailRead:=True;
  end;
  StationProcessUpdate;UnknownPressure;
 end;
 Fresh;V[0].Raw:=32;StationProcessUpdate;UnknownPressure;
 Check(Pos('Не совпадает',ProcessStatus.Text)>0,'map mismatch');
 for I:=1 to 7 do Check(V[I].Reads=0,'mismatched map stops payload reads');
 Fresh;LookupFailure:=True;StationProcessUpdate;UnknownPressure;
 Fresh;V[2].Raw:=2;StationProcessUpdate;UnknownPressure;
 Check(Pos('неизвестный',ProcessValidity.Text)>0,'invalid source enum');
 Fresh;V[4].Raw:=50;V[5].Raw:=1;StationProcessUpdate;
 Check(ProcessFrequency.Text='Нет данных','stopped state with nonzero frequency');
 Fresh;V[4].Raw:=0;V[5].Raw:=2;StationProcessUpdate;
 Check(ProcessFrequency.Text='Нет данных','nonzero state with zero frequency');
 Fresh;V[4].Raw:=6000;V[5].Raw:=2;StationProcessUpdate;
 Check(ProcessFrequency.Text='Нет данных','PLC frequency guard');
 Fresh;V[5].Raw:=0;StationProcessUpdate;
 Check(ProcessFrequency.Text='Нет данных','stale frequency state');
 Fresh;V[1].Raw:=-1;V[2].Raw:=1;StationProcessUpdate;UnknownPressure;
 Fresh;V[1].Raw:=65536;V[2].Raw:=1;StationProcessUpdate;UnknownPressure;
 Fresh;V[3].Raw:=0;StationProcessUpdate;Check(ProcessSetpoint.Text='0.00 бар','read-only zero SP');
 Fresh;V[6].Raw:=0;V[7].Raw:=0;StationProcessUpdate;
 Check(ProcessFault.Text='Не подключён','zero general alarm word is not native fault acknowledgement');
 Check(Pos('не подтверждается',ProcessFreshness.Text)>0,'freshness limits remain visible');
 WriteLn('PASS process-card assertions=',N);
end.
'''

def pascal():
    src = SCRIPT_SOURCE.read_text()
    assert 'CL50S' not in src and 'Timestamp' not in src and 'AddMessage' not in src
    assert not re.search(r'\b(?:V|codex_\w+)\.(?:Value|As\w+|Active)\s*:=', src)
    controls = re.findall(r'\b(Process\w+)\.(?:Text|Color)\s*:=', src)
    with tempfile.TemporaryDirectory(prefix='process-ui-') as t:
        p = Path(t); (p / 'ProcessStubs.pas').write_text(STUB)
        module = 'unit ProcessCard;\n{$mode objfpc}{$H+}{$codepage utf8}\n' + src.replace('interface\n', 'interface\nuses SysUtils,ProcessStubs;\n', 1)
        (p / 'ProcessCard.pas').write_text(module)
        harness = HARNESS.replace('__CONTROLS__', '\n'.join(n + ':=TControl.Create;' for n in sorted(set(controls))))
        (p / 'check.pas').write_text(harness)
        compiler = runtime_fpc()
        args = [str(compiler), '-gl', '-Cr', '-Co', '-Fu' + str(p), '-FU' + str(p), '-FE' + str(p)]
        args += ['-Fu' + str(d) for d in runtime_units(compiler) if d.is_dir()]
        r = subprocess.run(args + [str(p / 'check.pas')], capture_output=True, text=True, timeout=25)
        assert r.returncode == 0, r.stdout + r.stderr
        r = subprocess.run([str(p / 'check')], capture_output=True, text=True, timeout=10)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout.strip()

def serialize_scripts(records):
    def w(s): b = s.encode('utf-16le'); return struct.pack('<I', len(b)//2) + b
    raw = struct.pack('<qI', max(r[0] for r in records)+1, 3) + b'..\\' + struct.pack('<II', 0, len(records))
    for uid, name, meta, lines in records:
        raw += struct.pack('<q', uid) + w(name) + meta + struct.pack('<I', len(lines)) + b''.join(w(s) for s in lines)
    return raw

def fixture_source(folder):
    shutil.copytree(SOURCE, folder)
    (folder / 'Pages.spg').write_bytes((ROOT / 'artifacts/simple-scada-diagnostics-01/Pages.spg').read_bytes())
    base = parse_scripts((ROOT / 'artifacts/simple-scada-diagnostics-01/Scripts.ssc').read_bytes())
    core, timer = base
    meta = bytearray(core[2]);struct.pack_into('<I', meta, 2, 63000)
    radio = (2, 'StationRadioDiagnostics', bytes(meta), (ROOT / 'artifacts/teleofis-radio-display-01/scripts/StationRadioDiagnostics.txt').read_text().splitlines())
    timer = (*timer[:3], ['begin', '  StationDiagUpdate;', '  StationRadioUpdate;', 'end.'])
    records = [core, radio, timer]
    (folder / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
    (folder / 'Tools').mkdir(); (folder / 'Tools/Run-Radio-Usb-Collector-01.ps1').write_bytes(b'fixture collector preserved\r\n')
    (folder / 'Scripts/Compiled').mkdir(exist_ok=True); (folder / 'Scripts/Compiled/old.bin').write_bytes(b'compiled old code')
    return records

def powershell():
    original = (OUT / 'Install-Process-Display-01.ps1').read_text()
    cases = []
    for case in ['normal', 'caret_and_unit_header', 'core_changed', 'radio_changed', 'radio_renamed_identifier', 'radio_missing_procedure', 'destination_exists', 'corrupt_bundle', 'wrong_version']:
        with tempfile.TemporaryDirectory(prefix='process-install-') as t:
            p = Path(t);src = p / 'Current source';dst = p / 'Desktop/codex_diag_03';dst.parent.mkdir()
            records = fixture_source(src)
            if case == 'caret_and_unit_header':
                records = [(uid,name,meta[:9]+struct.pack('<II',7,12),(['unit '+name+';']+lines) if name!='StationDiagnosticsTimer' else lines) for uid,name,meta,lines in records]
                (src / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            if case in ['core_changed', 'radio_changed']:
                index = 0 if case == 'core_changed' else 1
                row = records[index];records[index] = (*row[:3], row[3] + ['// User edit retained'])
                (src / 'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            if case == 'radio_renamed_identifier':
                row=records[1];records[1]=(*row[:3],[s.replace('RadioPublishedUnix','RadioPublishedSeconds') for s in row[3]])
                (src/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            if case == 'radio_missing_procedure':
                row=records[1];records[1]=(*row[:3],[s.replace('StationRadioUpdate','DifferentRadioUpdate') for s in row[3]])
                (src/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            if case == 'destination_exists': dst.mkdir(); (dst / 'Keep.txt').write_text('user copy')
            if case == 'wrong_version':
                b = bytearray((src / 'Project.spr').read_bytes());struct.pack_into('<H',b,12,16);(src / 'Project.spr').write_bytes(b)
            before = hashes(src);existing = hashes(dst) if dst.exists() else None
            code = re.sub(r'^\$processTarget=.*$', lambda _: "$processTarget='"+str(dst)+"'", original, count=1, flags=re.M)
            code = re.sub(r'\$candidates=@\(.*?\n    \)', lambda _: "$candidates=@('"+str(src)+"')", code, count=1, flags=re.S)
            if case == 'corrupt_bundle':
                b = re.search(r"\$processBundle=@'\n(.*?)\n'@",code,re.S)[1];code=code.replace(b,('B' if b[0]!='B' else 'A')+b[1:],1)
            runner = p / 'run.ps1';runner.write_text(bootstrap(code))
            env = os.environ | {k: str(p / v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
            r = subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=25)
            assert r.returncode == 0 and not r.stderr,(case,r.stdout,r.stderr)
            assert hashes(src) == before,(case,'source modified')
            assert not list(dst.parent.glob('*.stage-*'))
            if case in ['normal','caret_and_unit_header','radio_changed','radio_renamed_identifier']:
                assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                result = parse_scripts((dst / 'Scripts/Scripts.ssc').read_bytes())
                assert result[1] == records[1], 'radio module altered'
                radio_only=serialize_scripts([records[1]])
                record_offset=8+4+3+4+4
                radio_bytes=radio_only[record_offset:]
                assert (src/'Scripts/Scripts.ssc').read_bytes().count(radio_bytes)==1
                assert (dst/'Scripts/Scripts.ssc').read_bytes().count(radio_bytes)==1,'radio record not byte-exact'
                assert result[0][3] == SCRIPT_SOURCE.read_text().splitlines()
                assert result[2][3] == ['begin','  StationProcessUpdate;','  StationRadioUpdate;','end.']
                assert not list((dst / 'Scripts/Compiled').iterdir())
                for rel,h in before.items():
                    if rel in ['Pages.spg','Scripts/Scripts.ssc'] or rel.startswith('Scripts/Compiled/'):continue
                    assert sha((dst / rel).read_bytes()) == h,(case,rel)
                assert (dst / 'Pages.spg').read_bytes() == (OUT / 'Pages.spg').read_bytes()
            else:
                assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout,(case,r.stdout)
                assert hashes(dst)==existing if existing is not None else not dst.exists()
            cases.append(dict(case=case,passed=True,source_preserved=True));print('PASS copy',case,flush=True)
    return cases

def native_records():
    if os.environ.get('CODEX_PAGE_LOADER') != '1':
        return dict(skipped=True, reason='Optional vendor page loader disabled', native_GUI_F9_passed=False)
    from verify_scada_native_loader_01 import read_pages,IMAGE
    result = read_pages(OUT / 'Pages.spg')
    assert result['page_ids']==[0,1] and len(result['objects'])==32
    data=(OUT / 'Pages.spg').read_bytes()
    for item in result['objects']:
        assert item['kind']==4
        assert struct.unpack_from('<q',data,item['body']+111)[0]==-1
    names = {item['name'] for item in result['objects']}
    references = set(re.findall(r'\b(\w+)\.(?:Text|Color)\s*:=', SCRIPT_SOURCE.read_text()))
    assert references <= names,references-names
    assert {'DiagRadio','DiagRadioNote'} <= names
    return dict(objects=len(result['objects']),pages=2,reader='Official2.6.15 x86 object loader in Unicorn with stream/UI adapters',editor_sha256=sha(IMAGE.read_bytes()),native_GUI_F9_passed=False)

def continuation():
    code=(OUT/'Continue-Process-Install-01.ps1').read_text()
    patch_packed=re.search(r"\$continuePatch=@'\n(.*?)\n'@",code,re.S)[1]
    changes=json.loads(gzip.decompress(base64.b64decode(patch_packed)))
    old=(OUT/'Install-Process-Display-01.ps1').read_text()
    for change in reversed(changes):
        assert old.count(change['new'])==1
        old=old.replace(change['new'],change['old'])
    assert sha(old.encode())=='ad60d2f46b6eee6c3d0bb57c7e7166981ff353c7b98f5d05c1f4b0870cd6665f'
    cases=[]
    for case in ['changed_radio_history','base64_whitespace','wrong_original','missing_history','corrupt_patch']:
        with tempfile.TemporaryDirectory(prefix='process-continue-') as t:
            p=Path(t);src=p/'Current source';dst=p/'Desktop/codex_diag_03';dst.parent.mkdir()
            records=fixture_source(src)
            row=records[1];records[1]=(*row[:3],[line.replace('RadioPublishedUnix','RadioPublishedSeconds') for line in row[3]])
            (src/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(records))
            before=hashes(src)
            original=old.replace('Read-only process card','Altered card') if case=='wrong_original' else old
            history=bootstrap(original).replace('$radio','$process')
            if case=='base64_whitespace':history=history.replace('$processPacked=@\'\n','$processPacked=@\'\n   ',1)
            setup="function Join-Path {param([string]$Path,[string]$ChildPath)\n"
            setup+="if($ChildPath -eq 'codex_diag_03'){return '"+str(dst)+"'}\n"
            setup+="if($ChildPath -like '*codex_diag_02'){return '"+str(src)+"'}\n"
            setup+="Microsoft.PowerShell.Management\\Join-Path -Path $Path -ChildPath $ChildPath\n}\n"
            if case!='missing_history':
                setup+="$historyText=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+base64.b64encode(history.encode()).decode()+"'))\n"
                setup+="Add-History -InputObject ([pscustomobject]@{CommandLine=$historyText;ExecutionStatus='Completed';StartExecutionTime=[DateTime]::Now;EndExecutionTime=[DateTime]::Now})\n"
            test=code
            if case=='corrupt_patch':test=test.replace(patch_packed,'AAAA'+patch_packed[4:],1)
            runner=p/'run.ps1';runner.write_text(setup+test)
            env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=25)
            assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            assert hashes(src)==before and not list(dst.parent.glob('*.stage-*'))
            if case in ['changed_radio_history','base64_whitespace']:
                assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                result=parse_scripts((dst/'Scripts/Scripts.ssc').read_bytes())
                assert result[1]==records[1]
                radio_bytes=serialize_scripts([records[1]])[23:]
                assert (dst/'Scripts/Scripts.ssc').read_bytes().count(radio_bytes)==1
            else:
                assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout and not dst.exists(),(case,r.stdout)
            cases.append(dict(case=case,passed=True,source_preserved=True));print('PASS continuation',case,flush=True)
    return cases

def main():
    logic=pascal();print(logic,flush=True)
    native=native_records();print('Page loader:',native,flush=True)
    copies=powershell()
    report=dict(date='2026-10-30',logic=logic,native_records=native,copy_cases=copies,
        API_reference='Official2.6.15 Scripts.chm: GetVariableByAddress,TM_Variable.Outer/Address/OPCServerName/ComputerName/IsGoodQuality/OriginalAsInt',
        limits='FreePascal strict stubs, real PowerShell7.6.9/Linux, x86 stream loading with adapters; Windows GUI/F9, process card live readings and nonzero frequency scaling remain unverified')
    if (OUT/'Continue-Process-Install-01.ps1').exists():report['continuation_cases']=continuation()
    (OUT / 'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
