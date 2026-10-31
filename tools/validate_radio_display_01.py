#!/usr/bin/env python3
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
import json,os,pty,select,struct,subprocess,tempfile,time,tty
from pathlib import Path
from validate_teleofis_radio_usb_probe_01 import frame,packet,PWSH
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/teleofis-radio-display-01'

def collector(case):
 with tempfile.TemporaryDirectory(prefix='radio-loop-') as t:
  p=Path(t);master,slave=pty.openpty();tty.setraw(slave);dev=os.ttyname(slave)
  s=(OUT/'Run-Radio-Usb-Collector-01.ps1').read_text()
  s=s.replace("$diagDir='C:\\ProgramData\\Automatika\\Station50008'","$diagDir='"+str(p/'data')+"'")
  s=s.replace("'COM18',115200",repr(dev)+',115200').replace('$diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true','$diagSerial.DtrEnable=$false;$diagSerial.RtsEnable=$false')
  s=s.replace('ElapsedMilliseconds<3000','ElapsedMilliseconds<120').replace('ElapsedMilliseconds -lt 5000','ElapsedMilliseconds -lt 80')
  s="function Read-Host {param([string]$Prompt,[switch]$AsSecureString) ConvertTo-SecureString 'TEST' -AsPlainText -Force}\n"+s
  f=p/'run.ps1';f.write_text(s);data=p/'data/radio.txt';stop=p/'data/radio.stop'
  env=os.environ|{'XDG_CACHE_HOME':str(p/'cache'),'XDG_CONFIG_HOME':str(p/'config'),'XDG_DATA_HOME':str(p/'store')}
  proc=subprocess.Popen([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
  buf=bytearray();seen={};req=[];deadline=time.monotonic()+15;dropped=False
  try:
   while proc.poll() is None and time.monotonic()<deadline:
    if data.exists():
     text=data.read_text();rows=text.splitlines();assert len(rows)==10 and rows[0]=='ARADIO1',text
     assert 'TEST' not in text;seen[rows[3]]=rows
     if len(seen)>=3:stop.touch()
    if not select.select([master],[],[],.01)[0]:continue
    buf.extend(os.read(master,4096))
    while 194 in buf:
     n=buf.index(194)+1;wire=bytes(buf[:n]);del buf[:n];act,cmd,payload=packet(wire);req.append((act,cmd))
     assert (act,cmd) in [(4,78),(0,123),(0,131),(0,148)]
     if cmd==78:
      assert payload==b'TEST'
      reply=frame(5,65535,b'\x4e\x00\x01') if case=='auth' else frame(5,78)
     else:
      if case=='recover' and cmd==123 and not dropped:dropped=True;continue
      value={123:bytes([99 if case=='unknown' else 26]),131:struct.pack('<I',11794),148:b'\x02'}[cmd]
      reply=frame(2,cmd,value)
     os.write(master,reply)
   if proc.poll() is None:proc.kill();raise AssertionError((case,'Collector failed to stop',seen))
   stdout,stderr=proc.communicate(timeout=2);out=stdout.decode();err=stderr.decode()
   assert proc.returncode==0 and not err and 'ERROR:' not in out,(case,out,err)
   assert 'TEST' not in out+err and not list((p/'data').glob('*.tmp'))
   last=data.read_text().splitlines()
   if case=='auth':assert len(req)==1 and last[6]=='1',req
   else:
    assert last[6]=='5',last
    good=[r for r in seen.values() if r[6]=='0'];assert good,(case,seen)
    assert any(r[7:]==['99' if case=='unknown' else '26','2','11794'] for r in good),good
    if case=='recover':assert any(r[6]=='2' and r[5]=='0' and r[7:]==['-1','-1','-1'] for r in seen.values()),seen
   return dict(case=case,passed=True,read_only_requests=len(req),atomic_complete_records=len(seen),stop_or_auth_failure_reported=True)
  finally:
   if proc.poll() is None:proc.kill();proc.communicate()
   os.close(master);os.close(slave)

STUB=r'''unit RadioStubs;
{$mode objfpc}{$H+}{$codepage utf8}
interface
uses SysUtils,Classes;
type TM_FileCodePage=(fcpUTF8);
 TM_StringList=class(TStringList)
 public procedure LoadFromFile(const N:string;C:TM_FileCodePage);reintroduce;
 function Item(I:Integer):string;property Items[I:Integer]:string read Item;default;end;
 TControl=class public Text:string;Color:Cardinal;end;
var DiagRadio,DiagRadioNote:TControl;FakeUnix:Int64;
function Now:TDateTime;
function DateTimeToUnix(V:TDateTime;UTC:Boolean):Int64;
function RGB(R,G,B:Byte):Cardinal;
implementation
procedure TM_StringList.LoadFromFile(const N:string;C:TM_FileCodePage);begin inherited LoadFromFile(N);end;
function TM_StringList.Item(I:Integer):string;begin Result:=Strings[I];end;
function Now:TDateTime;begin Result:=0;end;
function DateTimeToUnix(V:TDateTime;UTC:Boolean):Int64;
begin if UTC then raise Exception.Create('Native Now must be treated as local');Result:=FakeUnix;end;
function RGB(R,G,B:Byte):Cardinal;begin Result:=(Cardinal(R) shl 16) or (Cardinal(G) shl 8) or B;end;
initialization DiagRadio:=TControl.Create;DiagRadioNote:=TControl.Create;
end.
'''

def pascal():
 with tempfile.TemporaryDirectory(prefix='radio-ui-') as t:
  p=Path(t);file=p/'radio.txt';(p/'RadioStubs.pas').write_text(STUB)
  src=(OUT/'scripts/StationRadioDiagnostics.txt').read_text().replace('C:\\ProgramData\\Automatika\\Station50008\\radio.txt',str(file))
  src='unit RadioUi;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+src.replace('interface\n','interface\nuses SysUtils,RadioStubs;\n',1)
  (p/'RadioUi.pas').write_text(src)
  harness=r'''program CheckRadio;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,Classes,RadioStubs,RadioUi;
var L:TStringList;N:Integer;
procedure Check(B:Boolean);begin Inc(N);if not B then raise Exception.Create('assertion '+IntToStr(N));end;
procedure Save;begin L.SaveToFile('__PATH__');StationRadioUpdate;end;
procedure Good;
begin L.Clear;L.Add('ARADIO1');L.Add('USB');L.Add('0123456789abcdef0123456789abcdef');L.Add('1');L.Add('1700000000');L.Add('1700000000');L.Add('0');L.Add('26');L.Add('2');L.Add('11794');FakeUnix:=1700000000;end;
procedure Hidden;begin Check(Pos('нет данных',DiagRadio.Text)>0);end;
begin
DefaultSystemCodePage:=65001;DefaultFormatSettings.DecimalSeparator:='.';L:=TStringList.Create;N:=0;
StationRadioUpdate;Hidden;
Good;Save;Check(Pos('26',DiagRadio.Text)>0);Check(Pos('4G',DiagRadio.Text)>0);Check(Pos('11.794',DiagRadio.Text)>0);Check(Pos('стенд',DiagRadioNote.Text)>0);
FakeUnix:=1700000021;StationRadioUpdate;Hidden;
Good;L[4]:='1700000016';FakeUnix:=1700000016;Save;Hidden;
Good;L[4]:='1700000003';L[5]:='1700000003';Save;Hidden;
Good;L[6]:='1';Save;Hidden;Check(Pos('пароль',DiagRadioNote.Text)>0);
FakeUnix:=1700000100;StationRadioUpdate;Hidden;Check(Pos('Последний результат',DiagRadioNote.Text)>0);
Good;L[6]:='5';Save;Hidden;Check(Pos('остановлен',DiagRadioNote.Text)>0);
Good;L[7]:='99';Save;Check(Pos('не определён',DiagRadio.Text)>0);Check(Pos('11.794',DiagRadio.Text)>0);
Good;L[7]:='32';Save;Check(Pos('32 (шкала TELEOFIS)',DiagRadio.Text)>0);
Good;L[1]:='SERVICE';Save;Check(Pos('служебный канал',DiagRadioNote.Text)>0);
Good;L[1]:='MAIN';Save;Hidden;
Good;L[2]:='g123456789abcdef0123456789abcdef';Save;Hidden;
Good;L[3]:='9223372036854775808';Save;Hidden;
Good;L.Delete(9);Save;Hidden;
Good;L[9]:='4294967296';Save;Hidden;
Good;L[9]:='0';Save;Check(Pos('0.000',DiagRadio.Text)>0);
Good;L[8]:='8';Save;Check(Pos('код 8',DiagRadio.Text)>0);
Good;L[6]:='bad';Save;Hidden;
Good;L[4]:='1700000000';L[5]:='1700000001';Save;Hidden;
WriteLn('PASS radio-ui assertions=',N);L.Free;
end.
'''.replace('__PATH__',str(file))
  (p/'check.pas').write_text(harness)
  compiler=runtime_fpc()
  args=[str(compiler),'-gl','-Cr','-Co','-Fu'+str(p),'-FU'+str(p),'-FE'+str(p)]
  args+=['-Fu'+str(d) for d in runtime_units(compiler) if d.is_dir()]
  r=subprocess.run(args+[str(p/'check.pas')],capture_output=True,text=True,timeout=20);assert r.returncode==0,r.stdout+r.stderr
  r=subprocess.run([str(p/'check')],capture_output=True,text=True,timeout=10);assert r.returncode==0,r.stdout+r.stderr
  return r.stdout.strip()

def main():
 ui=pascal();print(ui,flush=True);results=[]
 for case in ['normal','unknown','auth','recover']:results.append(collector(case));print('PASS collector',case,flush=True)
 (OUT/'validation-2026-10-29.json').write_text(json.dumps(dict(ui=ui,collectors=results,
  native_file_APIs_confirmed='Official2.6.15 Scripts.chm: TM_StringList,LoadFromFile,fcpUTF8,DateTimeToUnix(Now,False),FreeAndNil',
  limitations='Strict FreePascal stubs and PowerShell7.6.9/LinuxPTY. NativeWindows F9/new collector not yet run; electrical lines disabled solely for PTY.'),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
