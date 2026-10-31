#!/usr/bin/env python3
"""Test the real delivery wrapper without cloud access or user credentials."""
from _runtime import PWSH as PWSH_RUNTIME
import hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
from build_radio_service_delivery_01 import ROOT,OUT,sha
from build_radio_display_01 import bootstrap

PWSH=PWSH_RUNTIME

def main():
    original=(OUT/'Install-And-Run-Radio-Service-01.ps1').read_text()
    launch="& ([scriptblock]::Create([IO.File]::ReadAllText($collector,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath $config"
    assert original.count(launch)==1
    cases=[]
    for case in ['new_install','repeat_install','collector_changed','config_changed','corrupt_transfer']:
        with tempfile.TemporaryDirectory(prefix='service-delivery-') as t:
            p=Path(t);dst=p/'ProgramData/Automatika/RadioServicePilot01'
            if case!='new_install':
                dst.mkdir(parents=True)
                for name in ['Run-Radio-Service-Collector-01.ps1','stations.json']:(dst/name).write_bytes((OUT/name).read_bytes())
            if case=='collector_changed':(dst/'Run-Radio-Service-Collector-01.ps1').write_text('user changed code')
            if case=='config_changed':(dst/'stations.json').write_text('{"user":"different station"}')
            before={f.name:sha(f.read_bytes()) for f in dst.iterdir()} if dst.exists() else None
            code=re.sub(r'^\$serviceTarget=.*$',lambda _:"$serviceTarget='"+str(dst)+"'",original,count=1,flags=re.M)
            # Only the final launch is instrumented. Actual transport has separate loopback coverage.
            code=code.replace(launch,"Write-Host ('LAUNCH_READY: '+$collector+' | '+$config)")
            if case=='corrupt_transfer':
                b=re.search(r"\$serviceBundle=@'\n(.*?)\n'@",code,re.S)[1]
                code=code.replace(b,('B' if b[0]!='B' else 'A')+b[1:],1)
            runner=p/'run.ps1';runner.write_text(bootstrap(code))
            env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=20)
            assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            if case in ['new_install','repeat_install']:
                assert 'SAVED:' in r.stdout and 'LAUNCH_READY:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                for name in ['Run-Radio-Service-Collector-01.ps1','stations.json']:assert (dst/name).read_bytes()==(OUT/name).read_bytes()
            else:
                assert 'ERROR:' in r.stdout and 'LAUNCH_READY:' not in r.stdout,(case,r.stdout)
                after={f.name:sha(f.read_bytes()) for f in dst.iterdir()} if dst.exists() else None
                assert before==after,(case,'Existing files changed')
            assert not list(dst.glob('*.tmp')) if dst.exists() else True
            cases.append(dict(case=case,passed=True));print('PASS Service delivery',case,flush=True)
    report=dict(date='2026-10-30',cases=cases,runtime='Actual PowerShell7.6.9/Linux through compressed inline wrapper',
        collector_launched_in_delivery_tests=False,collector_transport_validation='22 independent loopback cases already passed; collector code unchanged',
        real_cloud_or_Windows_test_passed=False)
    (OUT/'delivery-validation-2026-10-30.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
