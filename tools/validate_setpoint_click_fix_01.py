#!/usr/bin/env python3
"""Test actual caller-aware callbacks and native08 ->09 preservation."""
import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from _runtime import PWSH, SCADA_SEED
from build_setpoint_click_fix_01 import OUT, SOURCE, EVENTS
from validate_process_display_01 import serialize_scripts
from validate_radio_install_01 import parse_scripts, hashes
from validate_setpoint_control_01 import HARNESS, run_logic, legacy_checks
import validate_setpoint_control_01 as original_checks

EXTRA = '''
 Prime;
 Check((GetClientName='')and(GetUserID=-1),'global module ambient context intentionally unavailable');
 StationSpAdjust(10);
 Check(ProcessSpDraft.Text='3.6','actual OnClick passes valid caller across module boundary');
 StationSpCancel;Tick(2.2,2);
 Check((ProcessSpDraft.Text='3.5')and(WriteCount=0),'actual cancel callback edits no PLC value');
 Prime;ActorClient:='';StationSpAdjust(10);Tick(2.2,2);
 Check(Pos('Не удалось определить клиент',ProcessMainScope.Text)>0,'missing client has visible persistent explanation');
 Check((WriteCount=0)and(NoticeCount=0),'missing client cannot send write or targeted popup');
 Prime;ActorID:=-1;StationSpAdjust(10);Tick(2.2,2);
 Check(Pos('Войдите в клиент',ProcessMainScope.Text)>0,'unauthorized caller sees persistent reason');
 Check((WriteCount=0)and(NoticeCount=1),'unauthorized caller stays blocked');
 Prime;V[20].Raw:=340;StationSpAdjust(10);Tick(2.2,2);
 Check(Pos('не согласованы',ProcessMainScope.Text)>0,'write-gate readback disagreement is explained');
 Check(WriteCount=0,'mismatch diagnostic cannot write');
'''


def logic():
    module = (OUT/'scripts/StationDiagnostics.txt').read_text()
    events = {n:(OUT/'scripts'/(n+'_OnClick.txt')).read_text() for n,_ in EVENTS}
    for text in events.values():
        assert text.count('GetClientName') == text.count('GetUserName') == text.count('GetUserID') == 1
        assert '.Value' not in text
    runner=lambda harness:run_logic(harness,module_source=module,event_sources=events)
    harness=HARNESS.replace(" WriteLn('PASS operator control assertions=',N);",EXTRA+"\n WriteLn('PASS caller-aware control assertions=',N);")
    primary=runner(harness)
    return primary, legacy_checks(runner)


def old_context_regression():
    saved=original_checks.STUB
    original_checks.STUB=saved.replace('Result:=ActorClient',"Result:=''").replace('Result:=ActorName',"Result:=''").replace('Result:=ActorID','Result:=-1')
    try:
        try:original_checks.run_logic()
        except AssertionError as error:
            assert 'draft plus step' in str(error), str(error)
        else:raise AssertionError('Old ambient-context dependency was not detected')
    finally:original_checks.STUB=saved
    print('PASS regression: old module fails draft adjustment when its ambient caller is empty',flush=True)


def copies():
    results=[]
    installer=(OUT/'Install-Setpoint-Click-Fix-01.ps1').read_text()
    capsule=(OUT/'Paste-Setpoint-Click-Fix-01.ps1').read_text()
    packed=re.search(r"\$clickPacked=@'\n(.*?)\n'@",capsule,re.S)[1]
    assert gzip.decompress(base64.b64decode(packed)) == installer.encode()
    for case in ['native08','unit_headers','edited_core','edited_event','edited_pages','duplicate_id','wrong_version','destination_exists','corrupt_catalog']:
        with tempfile.TemporaryDirectory(prefix='sp-click-copy-') as name:
            p=Path(name);src=p/'Current08';dst=p/'Desktop/codex_diag_09';dst.parent.mkdir()
            shutil.copytree(SCADA_SEED,src)
            for f in src.rglob('.gitkeep'):f.unlink()
            (src/'Pages.spg').write_bytes((SOURCE/'Pages.spg').read_bytes())
            (src/'Scripts/Scripts.ssc').write_bytes((SOURCE/'Scripts.ssc').read_bytes())
            # Synthetic placeholders check preservation, not real user credentials.
            (src/'Users.fixture').write_text('synthetic account settings to preserve')
            (src/'.hidden.fixture').write_text('synthetic hidden project resource')
            (src/'Scripts/Compiled/old.exs').write_bytes(b'stale compiled cache')
            rows=parse_scripts((src/'Scripts/Scripts.ssc').read_bytes())
            if case=='unit_headers':rows=[(i,n,m,['unit '+n+';']+l) for i,n,m,l in rows]
            if case=='edited_core':i,n,m,l=rows[0];rows[0]=(i,n,m,l+['// preserve my edit'])
            if case=='edited_event':i,n,m,l=rows[4];rows[4]=(i,n,m,l+['// preserve my handler'])
            if case=='duplicate_id':i,n,m,l=rows[4];rows[4]=(3,n,m,l)
            if case in ['unit_headers','edited_core','edited_event','duplicate_id']:(src/'Scripts/Scripts.ssc').write_bytes(serialize_scripts(rows))
            if case=='edited_pages':b=bytearray((src/'Pages.spg').read_bytes());b[0]^=1;(src/'Pages.spg').write_bytes(b)
            if case=='wrong_version':b=bytearray((src/'Project.spr').read_bytes());b[10]=7;(src/'Project.spr').write_bytes(b)
            if case=='destination_exists':dst.mkdir();(dst/'keep.txt').write_text('existing user project')
            before=hashes(src);old_destination=hashes(dst) if dst.exists() else None
            code=re.sub(r'^\$clickTarget=.*$',lambda _:"$clickTarget='"+str(dst)+"'",installer,count=1,flags=re.M)
            code=re.sub(r' \$candidates=@\(.*?\n \)',lambda _:" $candidates=@('"+str(src)+"')",code,count=1,flags=re.S)
            if case=='corrupt_catalog':code=code.replace("$clickCatalog='","$clickCatalog='AAAA",1)
            runner=p/'run.ps1';runner.write_text(code)
            env=dict(os.environ,XDG_CACHE_HOME=str(p/'cache'),XDG_CONFIG_HOME=str(p/'config'),XDG_DATA_HOME=str(p/'data'))
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=25)
            assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            assert hashes(src)==before
            if case in ['native08','unit_headers']:
                assert 'SAVED:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                new=parse_scripts((dst/'Scripts/Scripts.ssc').read_bytes())
                assert new[1:3]==rows[1:3]
                assert new[0][3]==(OUT/'scripts/StationDiagnostics.txt').read_text().splitlines()
                for index,(object_name,_) in enumerate(EVENTS):
                    a=new[3+index];b=rows[3+index]
                    assert a[:2]==b[:2] and a[2][:9]==b[2][:9] and a[2][9:]==bytes(8)
                    assert a[3]==(OUT/'scripts'/(object_name+'_OnClick.txt')).read_text().splitlines()
                after=hashes(dst)
                for path,digest in before.items():
                    if path=='Scripts/Scripts.ssc' or path.startswith('Scripts/Compiled/'):continue
                    assert after[path]==digest,(case,path)
                assert not list((dst/'Scripts/Compiled').iterdir())
            else:
                assert 'ERROR:' in r.stdout and 'SAVED:' not in r.stdout,(case,r.stdout)
                assert hashes(dst)==old_destination if old_destination is not None else not dst.exists()
            assert not list(dst.parent.glob('*.stage-*'))
            results.append(dict(case=case,passed=True));print('PASS click-fix copy',case,flush=True)
    return results


def main():
    old_context_regression()
    primary,prior=logic();print(primary,flush=True)
    for report in prior:print(report,flush=True)
    copy_cases=copies()
    report=dict(date='2026-10-31',logic=primary,legacyReports=prior,copyCases=copy_cases,
                oldAmbientContextRegressionDetected=True,
                contextTest='Actual four event sources compiled as a separate unit; module ambient identity empty/-1, callback identity supplied by event API seam',
                noHardwareConnections=True,native09WindowsObserved=False,actualPLCWriteObserved=False)
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
