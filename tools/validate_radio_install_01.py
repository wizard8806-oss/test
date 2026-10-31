#!/usr/bin/env python3
from _runtime import SCADA_SEED
from _runtime import PWSH as PWSH_RUNTIME
import hashlib,json,os,re,shutil,struct,subprocess,tempfile
from pathlib import Path
from build_radio_display_01 import ROOT,OUT,bootstrap
PWSH=PWSH_RUNTIME

def hashes(p):return {str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}
def parse_scripts(raw):
 pos=0
 def n(fmt):
  nonlocal pos
  v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=struct.calcsize('<'+fmt);return v
 def w():
  nonlocal pos
  l=n('I');v=raw[pos:pos+l*2].decode('utf-16le');pos+=l*2;return v
 nextid=n('q');l=n('I');pos+=l;assert n('I')==0;count=n('I');records=[]
 for _ in range(count):
  uid=n('q');name=w();meta=raw[pos:pos+17];pos+=17;lines=[w() for _ in range(n('I'))]
  records.append((uid,name,meta,lines))
 assert pos==len(raw) and nextid>max(r[0] for r in records)
 return records

def main():
 code=(OUT/'Install-Radio-Display-01.ps1').read_text();cases=[]
 targetline=next(x for x in code.splitlines() if x.startswith('$radioTarget='))
 for case in ['normal','native_caret_changed','source_edited','destination_exists','corrupt_bundle']:
  with tempfile.TemporaryDirectory(prefix='radio-install-') as t:
   p=Path(t);src=p/'codex_diag_01';dst=p/'Desktop/codex_diag_02';dst.parent.mkdir()
   shutil.copytree(SCADA_SEED,src)
   for rel,artifact in [('Pages.spg','Pages.spg'),('Scripts/Scripts.ssc','Scripts.ssc')]:
    (src/rel).write_bytes((ROOT/'artifacts/simple-scada-diagnostics-01'/artifact).read_bytes())
   if case=='native_caret_changed':
    f=src/'Scripts/Scripts.ssc';b=f.read_bytes();pattern=bytes.fromhex('0a10')+struct.pack('<I',62008)
    pos=b.index(pattern);v=bytearray(b);v[pos+9:pos+17]=bytes.fromhex('0100000002000000');f.write_bytes(v)
   if case=='source_edited':
    f=src/'Scripts/Scripts.ssc';b=f.read_bytes();v='Станция отвечает'.encode('utf-16le');f.write_bytes(b.replace(v,'Станция ОТВЕЧАЕТ'.encode('utf-16le'),1))
   if case=='destination_exists':dst.mkdir();(dst/'Keep.txt').write_text('User edits')
   before=hashes(src);existing=hashes(dst) if dst.exists() else None
   test=code.replace(targetline,"$radioTarget='"+str(dst)+"'")
   test=re.sub(r'\$candidates=@\(.*?\n    \)',lambda _: "$candidates=@('"+str(src)+"')",test,count=1,flags=re.S)
   if case=='corrupt_bundle':
    b=re.search(r"\$radioBundle=@'\n(.*?)\n'@",test,re.S)[1];test=test.replace(b,('B' if b[0]!='B' else 'A')+b[1:],1)
   runner=p/'run.ps1';runner.write_text(bootstrap(test))
   env=os.environ|{'XDG_CACHE_HOME':str(p/'cache'),'XDG_CONFIG_HOME':str(p/'config'),'XDG_DATA_HOME':str(p/'store')}
   r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=25)
   assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
   assert hashes(src)==before and not list(dst.parent.glob('*.stage-*'))
   if case in ['normal','native_caret_changed']:
    assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
    rec=parse_scripts((dst/'Scripts/Scripts.ssc').read_bytes());assert [v[1] for v in rec]==['StationDiagnostics','StationRadioDiagnostics','StationDiagnosticsTimer']
    old=parse_scripts((src/'Scripts/Scripts.ssc').read_bytes());assert rec[0]==old[0]
    assert '\n'.join(rec[1][3])==(OUT/'scripts/StationRadioDiagnostics.txt').read_text().rstrip('\n')
    assert rec[2][3]==['begin','  StationDiagUpdate;','  StationRadioUpdate;','end.']
    for rel,hash in before.items():
     if rel=='Scripts/Scripts.ssc' or rel.startswith('Scripts/Compiled/'):continue
     assert hashlib.sha256((dst/rel).read_bytes()).hexdigest()==hash,(case,rel)
    assert not list((dst/'Scripts/Compiled').iterdir())
    assert (dst/'Tools/Run-Radio-Usb-Collector-01.ps1').read_bytes()==(OUT/'Run-Radio-Usb-Collector-01.ps1').read_bytes()
   else:
    assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout,(case,r.stdout)
    assert hashes(dst)==existing if existing is not None else not dst.exists()
   cases.append(dict(case=case,passed=True,source_unchanged=True));print('PASS install',case,flush=True)
 (OUT/'install-validation-2026-10-29.json').write_text(json.dumps(dict(cases=cases,
  runtime='Actual PowerShell7.6.9/Linux fixtures through the SHA-checked compressed bootstrap',
  native_editor_F9_passed=False,copy_fields_servers_variables_preserved=True),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
