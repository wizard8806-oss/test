#!/usr/bin/env python3
"""Real-PowerShell delivery fixtures and authored-Pascal logic checks.
Neither native Simple-Scada F9 nor a real modem/controller is exercised.
"""
from _runtime import fpc as runtime_fpc, fpc_units as runtime_units
from _runtime import PWSH as PWSH_RUNTIME
import hashlib,json,os,re,shutil,struct,subprocess,tempfile,zipfile
from pathlib import Path
from rebuild_scada_inline_delivery_01 import OUT,SOURCE,ROOT

STUB=r'''unit DiagStubs;
{$mode objfpc}{$H+}{$codepage utf8}
interface
uses SysUtils;
type
 TControl=class
 public Text:string;Color:Cardinal;Visible:Boolean;end;
 TVariable=class
 private Good:Boolean;Raw:Int64;function GetValue:Int64;
 public Reads:Integer;procedure Sample(G:Boolean;V:Int64);
 property IsGoodQuality:Boolean read Good;
 property AsInt64:Int64 read GetValue;end;
 TM_MessageKind=(mkMessage,mkWarning,mkAlarm);
var
 codex_Device1_MapVersion,codex_Device1_CL50S_TxCount:TVariable;
 MainDiagStatus,MainDiagDetail,DiagStatus,DiagDetail,DiagAge,DiagOPC,
 DiagRoute,Field1,Field2,MainMapUnknown,MainCounterUnknown:TControl;
 FakeNow:TDateTime;JournalCount:Integer;
function Now:TDateTime;
function RGB(R,G,B:Byte):Cardinal;
procedure AddMessage(T:TDateTime;K:TM_MessageKind;const Msg:string;Ack,Sound:Boolean);
implementation
function TVariable.GetValue:Int64;
begin
 if not Good then raise Exception.Create('Reading bad-quality value');
 Inc(Reads);Result:=Raw;
end;
procedure TVariable.Sample(G:Boolean;V:Int64);begin Good:=G;Raw:=V;end;
function Now:TDateTime;begin Result:=FakeNow;end;
function RGB(R,G,B:Byte):Cardinal;
begin Result:=(Cardinal(R) shl 16) or (Cardinal(G) shl 8) or B;end;
procedure AddMessage(T:TDateTime;K:TM_MessageKind;const Msg:string;Ack,Sound:Boolean);
begin
 if Ack or Sound then raise Exception.Create('Unexpected sound or acknowledgement');
 Inc(JournalCount);
end;
initialization
 codex_Device1_MapVersion:=TVariable.Create;
 codex_Device1_CL50S_TxCount:=TVariable.Create;
 MainDiagStatus:=TControl.Create;MainDiagDetail:=TControl.Create;
 DiagStatus:=TControl.Create;DiagDetail:=TControl.Create;DiagAge:=TControl.Create;
 DiagOPC:=TControl.Create;DiagRoute:=TControl.Create;Field1:=TControl.Create;
 Field2:=TControl.Create;MainMapUnknown:=TControl.Create;MainCounterUnknown:=TControl.Create;
end.
'''

HARNESS=r'''program CheckDiagnostics;
{$mode objfpc}{$H+}{$codepage utf8}
uses cwstring,SysUtils,DiagStubs,StationDiagnostics;
var S,A,I,Checks:Integer;Changed:Boolean;
procedure Check(B:Boolean;const Msg:string);
begin Inc(Checks);if not B then raise Exception.Create(Msg);end;
procedure Step(MG,CG:Boolean;M,C:Int64;T:Double;ES,EA:Integer;EC:Boolean);
begin
 DiagCoreStep(MG,CG,M,C,T,S,A,Changed);
 Check(S=ES,'state');Check(A=EA,'age');Check(Changed=EC,'progress proof');
 Check((S<>1) or (MG and CG and (M=31) and (C>=0) and (C<=65535)),'green prerequisites');
end;
procedure UI(T:Integer;MG,CG:Boolean;M,C:Int64);
begin
 FakeNow:=Double(45000)+Double(T)/Double(86400);
 codex_Device1_MapVersion.Sample(MG,M);codex_Device1_CL50S_TxCount.Sample(CG,C);
 StationDiagUpdate;
end;
begin
 DefaultSystemCodePage:=65001;Checks:=0;DiagCoreReset;
 Step(False,False,999,-1,0,2,-1,False);
 Step(True,True,31,100,1,5,0,False);
 Step(True,True,31,100,2,5,1,False);
 Step(True,True,31,101,5,1,0,True);
 for I:=6 to 34 do Step(True,True,31,101,I,1,I-5,False);
 Step(True,True,31,101,35,4,30,False);
 Step(True,True,31,102,36,1,0,True);
 Step(True,False,31,999999,37,2,-1,False);
 Step(True,True,31,102,38,5,0,False);
 Step(True,True,31,102,39,5,1,False);
 Step(True,True,31,103,40,1,0,True);
 Step(True,True,30,104,41,3,-1,False);
 Step(True,True,31,104,42,5,0,False);
 Step(True,True,31,65536,43,7,-1,False);
 Step(True,True,31,-1,44,7,-1,False);
 Step(True,True,31,65535,45,5,0,False);
 Step(True,True,31,0,46,1,0,True);
 Step(True,True,31,100,47,1,0,True);
 Step(True,True,31,0,48,1,0,True);
 Step(True,True,31,1,40,6,0,False);
 Step(True,True,31,1,41,5,1,False);
 Step(True,True,31,2,42,1,0,True);
 Step(True,True,31,3,90,6,0,False);
 Step(True,True,31,3,91,5,1,False);
 Step(True,True,31,4,92,1,0,True);
 DiagCoreReset;
 Step(True,True,31,5,0,5,0,False);
 for I:=1 to 29 do Step(True,True,31,5,I,5,I,False);
 Step(True,True,31,5,30,4,30,False);
 StationDiagReset;UI(0,False,False,999999,-1);
 Check(not Field1.Visible and not Field2.Visible,'hide bad values');
 Check(MainMapUnknown.Visible and MainCounterUnknown.Visible,'unknown placeholders');
 Check(codex_Device1_MapVersion.Reads=0,'no bad map conversion');
 Check(codex_Device1_CL50S_TxCount.Reads=0,'no bad counter conversion');
 UI(1,True,True,31,500);
 Check(Field1.Visible and not Field2.Visible,'wait after reconnect');
 UI(7,True,True,31,501);
 Check(Field1.Visible and Field2.Visible,'live displayed');
 Check(not MainCounterUnknown.Visible,'hide placeholder');
 Check(Pos('отвечает',MainDiagStatus.Text)>0,'live text');
 for I:=8 to 20 do UI(I,True,True,31,501+(I-7) div 5);
 Check(JournalCount=1,'one live message');
 for I:=21 to 27 do UI(I,False,False,888888,-1);
 Check(not Field1.Visible and not Field2.Visible,'hide outage');
 Check(JournalCount=2,'one outage message');
 UI(28,True,True,31,502);Check(not Field2.Visible,'GOOD is not progress');
 UI(29,True,True,31,502);Check(not Field2.Visible,'same sample after reconnect');
 for I:=30 to 37 do UI(I,True,True,31,503);
 Check(JournalCount=3,'one recovery message');
 for I:=38 to 68 do UI(I,True,True,31,503);
 Check(not Field2.Visible and MainCounterUnknown.Visible,'freeze hides value');
 Check(Pos('не обновляется',MainDiagStatus.Text)>0,'freeze warning text');
 Check(JournalCount=4,'no journal flood');
 WriteLn('PASS assertions=',Checks);
end.
'''

def filehashes(folder):
 return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}

def native_streams():
 pages=(OUT/'Pages.spg').read_bytes();original=(SOURCE/'Pages.spg').read_bytes()
 assert pages[:12]==struct.pack('<3I',2,0,2)
 assert pages[197:579]==original[197:]
 core=(OUT/'scripts/StationDiagnostics.txt').read_text()
 assert not re.search(r'codex_\w+\.\w+\s*:=',core)
 for name in ['codex_Device1_MapVersion','codex_Device1_CL50S_TxCount']:
  assert name.encode() in (SOURCE/'Variables.svr').read_bytes()
 # Lightweight structural check only. Independent native-reader verification
 # lives in verify_scada_native_loader_01.py and rejects the previous delivery.
 pos=193;names=[]
 for page in range(2):
  if page==1:
   # Header consists of the unchanged page/subpage shape with four renamed strings.
   h=bytearray(original[12:193]);struct.pack_into('<q',h,33,1);h=bytes(h)
   def a(s):b=s.encode();return struct.pack('<I',len(b))+b
   def w(s):b=s.encode('utf-16le');return struct.pack('<I',len(b)//2)+b
   for before,after in [(a('Page1'),a('PageDiagnostics')),(w('Страница 1'),w('Диагностика')),
      (a('Subpage1'),a('SubpageDiagnostics')),(w('Подстраница 1'),w('Диагностика')),
      (struct.pack('<I',9156),struct.pack('<I',62000)),(struct.pack('<I',9160),struct.pack('<I',62004))]:h=h.replace(before,after,1)
   assert pages[pos:pos+len(h)]==h;pos+=len(h)
  count=struct.unpack_from('<I',pages,pos)[0];pos+=4;assert count==[8,12][page]
  for _ in range(count):
   kind=struct.unpack_from('<H',pages,pos)[0];pos+=2
   n=struct.unpack_from('<I',pages,pos)[0];pos+=4
   names.append(pages[pos:pos+n].decode());pos+=n+141
   if kind==5:pos+=38
   else:
    assert kind==4;n=struct.unpack_from('<I',pages,pos)[0];pos+=4+2*n+9
 assert pos==len(pages) and len(names)==20 and len(names)==len(set(names))
 data=(OUT/'Scripts.ssc').read_bytes();assert data[:8]==struct.pack('<2I',2,0)
 pos=8;n=struct.unpack_from('<I',data,pos)[0];pos+=4+n
 assert data[pos:pos+8]==struct.pack('<2I',0,2);pos+=8
 for uid,name in enumerate(['StationDiagnostics','StationDiagnosticsTimer']):
  assert struct.unpack_from('<2I',data,pos)==(uid,0);pos+=8
  n=struct.unpack_from('<I',data,pos)[0];pos+=4
  assert data[pos:pos+n*2].decode('utf-16le')==name;pos+=n*2+17
  n=struct.unpack_from('<I',data,pos)[0];pos+=4;lines=[]
  for _ in range(n):
   m=struct.unpack_from('<I',data,pos)[0];pos+=4;lines.append(data[pos:pos+m*2].decode('utf-16le'));pos+=m*2
  assert lines==(OUT/'scripts'/(name+'.txt')).read_text().splitlines()
 assert pos==len(data)
 return core

def pascal(core):
 compiler=runtime_fpc()
 with tempfile.TemporaryDirectory(prefix='scada-code-') as tmp:
  p=Path(tmp);(p/'DiagStubs.pas').write_text(STUB)
  source='unit StationDiagnostics;\n{$mode objfpc}{$H+}{$codepage utf8}\n'+core.replace('interface\n','interface\nuses SysUtils,DiagStubs;\n',1)
  (p/'StationDiagnostics.pas').write_text(source);(p/'verify.pas').write_text(HARNESS)
  args=[str(compiler),'-gl','-Cr','-Co','-Fu'+str(p),'-FU'+str(p),'-FE'+str(p)]
  args+=['-Fu'+str(d) for d in runtime_units(compiler) if d.is_dir()]
  r=subprocess.run(args+[str(p/'verify.pas')],capture_output=True,text=True,timeout=30)
  assert r.returncode==0,r.stdout+r.stderr
  r=subprocess.run([str(p/'verify')],capture_output=True,text=True,timeout=10)
  assert r.returncode==0,r.stdout+r.stderr
  return int(re.search(r'assertions=(\d+)',r.stdout)[1])

def powershell():
 code=(OUT/'Save-Codex-Diag-01.ps1').read_text()
 source_line=next(l for l in code.splitlines() if l.startswith('$diagSource=Join-Path'))
 target_line=next(l for l in code.splitlines() if l.startswith('$diagTarget=Join-Path'))
 checks=[]
 for case in ['new_copy','source_changed','destination_exists','corrupt_transfer','source_missing']:
  with tempfile.TemporaryDirectory(prefix='scada-transfer-') as tmp:
   p=Path(tmp);src=p/'Source codex';dst=p/'Desktop/codex_diag_01';dst.parent.mkdir();shutil.copytree(SOURCE,src)
   if case=='source_changed':
    f=src/'Pages.spg';b=bytearray(f.read_bytes());b[-1]^=1;f.write_bytes(b)
   if case=='destination_exists':dst.mkdir();(dst/'User-Edited.txt').write_text('Keep')
   before=filehashes(src);existing=filehashes(dst) if dst.exists() else None
   s=code.replace(source_line,"$diagSource='"+str(src)+"'").replace(target_line,"$diagTarget='"+str(dst)+"'")
   if case=='source_missing':s=s.replace("$diagSource='"+str(src)+"'","$diagSource='"+str(p/'missing')+"'")
   if case=='corrupt_transfer':
    capsule=re.search(r"\$diagCapsule=@'\n(.*?)\n'@",s,re.S)[1];s=s.replace(capsule,('A' if capsule[0]!='A' else 'B')+capsule[1:],1)
   f=p/'run.ps1';f.write_text(s)
   env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
   r=subprocess.run([PWSH_RUNTIME,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)],env=env,capture_output=True,text=True,timeout=20)
   assert r.returncode==0,(case,r.stdout,r.stderr)
   assert filehashes(src)==before,(case,'Source modified')
   assert not list(dst.parent.glob('*.stage-*'))
   if case=='new_copy':
    assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout,r.stderr)
    assert (dst/'Pages.spg').read_bytes()==(OUT/'Pages.spg').read_bytes()
    assert (dst/'Scripts/Scripts.ssc').read_bytes()==(OUT/'Scripts.ssc').read_bytes()
    for rel in before:
     if rel not in ['Pages.spg','Scripts/Scripts.ssc'] and not rel.startswith('Scripts/Compiled/'):
      assert (dst/rel).read_bytes()==(src/rel).read_bytes()
    assert (dst/'Reports').is_dir() and (dst/'Scripts/Compiled').is_dir()
    assert not list((dst/'Scripts/Compiled').glob('*.exs'))
   else:
    assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout,(case,r.stdout,r.stderr)
    assert (filehashes(dst)==existing) if existing is not None else not dst.exists()
   checks.append(dict(case=case,passed=True,source_unchanged=True))
 return checks

def powershell_repair():
 code=(OUT/'Repair-Codex-Diag-01.ps1').read_text()
 # Regenerate exactly the bad file delivered previously for the regression.
 import verify_scada_native_loader_01 as native
 parsed=native.read_pages(OUT/'Pages.spg');bad=bytearray((OUT/'Pages.spg').read_bytes())
 struct.pack_into('<q',bad,0,1)
 struct.pack_into('<q',bad,parsed['objects'][-1]['page_id_offset'],0)
 for obj in parsed['objects']:
  if obj['kind']==4:
   s=obj['body'];layer=struct.unpack_from('<I',bad,s+54)[0]
   bad[s+49:s+58]=bytes(9);struct.pack_into('<I',bad,s+51,layer)
   struct.pack_into('<q',bad,s+111,0xffffffff)
 assert hashlib.sha256(bad).hexdigest()=='8f2f1221fb2527ba4348f900634a09f3a7e6d94c0101babb0b1df45ae92af882'
 checks=[]
 for case in ['repair','already_fixed','edited_pages','original_pages','edited_scripts','multiple_preflight']:
  with tempfile.TemporaryDirectory(prefix='scada-repair-') as tmp:
   p=Path(tmp);dst=p/'codex_diag_01';shutil.copytree(SOURCE,dst)
   (dst/'Pages.spg').write_bytes(bad);(dst/'Scripts/Scripts.ssc').write_bytes((OUT/'Scripts.ssc').read_bytes())
   if case=='already_fixed':(dst/'Pages.spg').write_bytes((OUT/'Pages.spg').read_bytes())
   if case=='edited_pages':(dst/'Pages.spg').write_bytes(bad+b'edit')
   if case=='original_pages':(dst/'Pages.spg').write_bytes((SOURCE/'Pages.spg').read_bytes())
   if case=='edited_scripts':(dst/'Scripts/Scripts.ssc').write_bytes(b'User edit')
   folders=[dst]
   if case=='multiple_preflight':
    second=p/'second/codex_diag_01';shutil.copytree(dst,second);(second/'Pages.spg').write_bytes(b'Unknown');folders.append(second)
   before=filehashes(p)
   paths=','.join("'"+str(f)+"'" for f in folders)
   script=re.sub(r'\$diagFolders=@\(.*?\n\)',lambda _: '$diagFolders=@('+paths+')',code,count=1,flags=re.S)
   f=p/'repair.ps1';f.write_text(script)
   env=os.environ|{'XDG_CACHE_HOME':str(p/'cache'),'XDG_CONFIG_HOME':str(p/'config'),'XDG_DATA_HOME':str(p/'data')}
   args=[PWSH_RUNTIME,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)]
   result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
   assert result.returncode==0,(case,result.stdout,result.stderr)
   if case=='repair':
    assert 'FIXED:' in result.stdout and 'ERROR:' not in result.stdout,result.stdout+result.stderr
    assert (dst/'Pages.spg').read_bytes()==(OUT/'Pages.spg').read_bytes()
    backups=list(dst.glob('Pages.spg.before-repair-*.bak'));assert len(backups)==1 and backups[0].read_bytes()==bad
    for rel,h in before.items():
     if rel!='codex_diag_01/Pages.spg':assert hashlib.sha256((p/rel).read_bytes()).hexdigest()==h
    repeat=subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
    assert 'ALREADY FIXED:' in repeat.stdout and len(list(dst.glob('*.bak')))==1
   elif case=='already_fixed':assert 'ALREADY FIXED:' in result.stdout and 'ERROR:' not in result.stdout
   else:assert 'ERROR:' in result.stdout and 'FIXED:' not in result.stdout,(case,result.stdout)
   if case!='repair':
    for rel,h in before.items():assert hashlib.sha256((p/rel).read_bytes()).hexdigest()==h,(case,rel)
    assert not list(p.rglob('*.bak'))
   assert not list(p.rglob('*.repair-*'))
   checks.append(dict(case=case,passed=True))
 return checks

def main():
 vendor_checked=os.environ.get('CODEX_PAGE_LOADER')=='1'
 if vendor_checked:
  from verify_scada_native_loader_01 import main as native_load
  native_load()
 assertions=pascal(native_streams());checks=powershell()
 repair=powershell_repair() if vendor_checked else dict(skipped=True,reason='Repair regression uses optional vendor page loader')
 report=dict(date='2026-10-29',delivery='Direct inline PowerShell; no chat file download needed',
  native_stream_structure_passed=True,native_x86_object_reader_emulation_passed=vendor_checked,
  previous_delivery_rejected_by_native_Editor=True,existing_fields_byte_exact=True,
  actual_Pascal_source_compiled_with_strict_stubs=True,logic_assertions_passed=assertions,
  transfer_runtime='Real PowerShell7.6.9 on Linux fixtures, not Windows5.1',
  transfer_cases=checks,repair_cases=repair,source_and_existing_output_preserved=True,
  actual_Windows_native_editor_open_and_F9_pending=True,
  native_SCADA_F9_passed=False,live_radio_values_implemented=False,
  original_download_UI_problem_fixed=False)
 (OUT/'validation-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
