#!/usr/bin/env python3
"""Verify group separation setup and one-owner session replacement handling."""
import json,os,re,subprocess,tempfile
from pathlib import Path
import validate_radio_service_01 as peer
from build_service_group_split_02 import ROOT,OUT,OLD,sha

PWSH=peer.PWSH

def setup_cases():
    original=(OUT/'Set-Service-Group-And-Run-02.ps1').read_text()
    launch="& ([scriptblock]::Create([IO.File]::ReadAllText($newPath,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath $configPath"
    cases=[]
    for case in ['valid','repeat','Main_group_rejected','invalid_id','source_changed','other_station','lock_held','new_collector_changed','CRLF_paste']:
        with tempfile.TemporaryDirectory(prefix='service-group-split-') as t:
            p=Path(t);dst=p/'RadioServicePilot01';dst.mkdir();data=p/'radio';data.mkdir()
            (dst/'Run-Radio-Service-Collector-01.ps1').write_bytes((OLD/'Run-Radio-Service-Collector-01.ps1').read_bytes())
            conf=json.loads((OLD/'stations.json').read_text());conf['Stations'][0]['RadioDataDirectory']=str(data)
            if case=='other_station':conf['Stations'][0]['Imei']='555555555555555'
            if case=='repeat':
                conf['Groups'][0].update(Id='teleofis-service-8765',Login=8765);conf['Stations'][0]['GroupId']='teleofis-service-8765'
                (dst/'Run-Radio-Service-Collector-02.ps1').write_bytes((OUT/'Run-Radio-Service-Collector-02.ps1').read_bytes())
            (dst/'stations.json').write_text(json.dumps(conf))
            if case=='source_changed':(dst/'Run-Radio-Service-Collector-01.ps1').write_text('User changes retained')
            if case=='new_collector_changed':(dst/'Run-Radio-Service-Collector-02.ps1').write_text('Other code retained')
            before={f.name:sha(f.read_bytes()) for f in dst.iterdir()}
            value='7058' if case=='Main_group_rejected' else 'invalid' if case=='invalid_id' else '8765'
            code=re.sub(r'^\$groupDirectory=.*$',lambda _:"$groupDirectory='"+str(dst)+"'",original,count=1,flags=re.M)
            code=code.replace(launch,"Write-Host ('LAUNCH_READY: '+$newPath)")
            prefix="function Read-Host {param([string]$Prompt) return '"+value+"'}\n"
            if case=='lock_held':prefix+="$testLock=[IO.File]::Open('"+str(data/'collector.lock')+"',[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)\n"
            code=prefix+code
            if case=='CRLF_paste':code=code.replace('\n','\r\n')
            f=p/'run.ps1';f.write_bytes(code.encode())
            env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)],env=env,capture_output=True,text=True,timeout=20)
            assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            if case in ['valid','repeat','CRLF_paste']:
                assert 'READY:' in r.stdout and 'LAUNCH_READY:' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                after=json.loads((dst/'stations.json').read_text())
                assert after['Groups'][0]['Login']==8765
                assert after['Groups'][0]['Id']==after['Stations'][0]['GroupId']=='teleofis-service-8765'
                assert after['Stations'][0]['RadioDataDirectory']==conf['Stations'][0]['RadioDataDirectory']
                assert (dst/'Run-Radio-Service-Collector-01.ps1').read_bytes()==(OLD/'Run-Radio-Service-Collector-01.ps1').read_bytes()
                assert (dst/'Run-Radio-Service-Collector-02.ps1').read_bytes()==(OUT/'Run-Radio-Service-Collector-02.ps1').read_bytes()
                backup=list(dst.glob('stations.json.before-service-group-*.bak'));assert len(backup)==1
                assert sha(backup[0].read_bytes())==before['stations.json']
            else:
                assert 'ERROR:' in r.stdout and 'LAUNCH_READY:' not in r.stdout,(case,r.stdout)
                assert {f.name:sha(f.read_bytes()) for f in dst.iterdir()}==before,(case,'Files changed on rejected setup')
            assert not list(dst.glob('*.tmp'))
            cases.append(dict(case=case,passed=True));print('PASS group setup',case,flush=True)
    return cases

def main():
    old=(OLD/'Run-Radio-Service-Collector-01.ps1').read_text();new=(OUT/'Run-Radio-Service-Collector-02.ps1').read_text()
    pattern=r"(?ms)^Add-Type.*?@'\n(.*?)\n'@"
    assert re.search(pattern,old)[1]==re.search(pattern,new)[1]
    setups=setup_cases();old_path=peer.SCRIPT;peer.SCRIPT=OUT/'Run-Radio-Service-Collector-02.ps1'
    try:
        transport=[]
        for name in ['normal','cloud_rejected','session_replaced']:
            result=peer.run(name)
            if name in ['cloud_rejected','session_replaced']:
                assert result['final_status_code']=='CLOUD_SESSION_REPLACED',result
                assert result['group_logins']==1,'Session replacement triggered reconnect contest'
            transport.append(result);print('PASS session policy',name,flush=True)
    finally:peer.SCRIPT=old_path
    report=dict(date='2026-10-30',setup_cases=setups,transport=transport,CSharpTransportUnchanged=True,
        real_cloud_group_changed=False,native_Windows_revision02_tested=False,actual_Service_radio_read=False,
        limitations='Actual PowerShell7.6.9/Linux and independent loopback, with user group creation still pending. Does not prove group split alone resolves earlier list timeout.')
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

def site9336():
    source=(OUT/'Start-ServiceDiag-9336.ps1').read_text()
    assert "$inputId='9336'" in source
    launch="& ([scriptblock]::Create([IO.File]::ReadAllText($newPath,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath $configPath"
    with tempfile.TemporaryDirectory(prefix='service-9336-') as t:
        p=Path(t);dst=p/'RadioServicePilot01';dst.mkdir();data=p/'radio';data.mkdir()
        old=dst/'Run-Radio-Service-Collector-01.ps1';old.write_bytes((OLD/old.name).read_bytes())
        conf=json.loads((OLD/'stations.json').read_text());conf['Stations'][0]['RadioDataDirectory']=str(data)
        config=dst/'stations.json';config.write_text(json.dumps(conf));before=config.read_bytes()
        code=re.sub(r'^\$groupDirectory=.*$',lambda _:"$groupDirectory='"+str(dst)+"'",source,count=1,flags=re.M)
        code=code.replace(launch,"Write-Host 'LAUNCH_READY'")
        code="function Read-Host {throw 'Group9336 must already be configured'}\n"+code
        f=p/'run.ps1';f.write_text(code)
        env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
        r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)],env=env,capture_output=True,text=True,timeout=20)
        assert r.returncode==0 and not r.stderr and 'READY: Service group 9336.' in r.stdout and 'LAUNCH_READY' in r.stdout and 'ERROR:' not in r.stdout,(r.stdout,r.stderr)
        actual=json.loads(config.read_text())
        assert actual['Groups'][0]['Login']==9336 and actual['Groups'][0]['Id']=='teleofis-service-9336'
        assert actual['Stations'][0]['GroupId']=='teleofis-service-9336'
        assert actual['Stations'][0]['RadioDataDirectory']==str(data)
        assert old.read_bytes()==(OLD/old.name).read_bytes()
        assert (dst/'Run-Radio-Service-Collector-02.ps1').read_bytes()==(OUT/'Run-Radio-Service-Collector-02.ps1').read_bytes()
        backup=list(dst.glob('stations.json.before-service-group-*.bak'));assert len(backup)==1 and backup[0].read_bytes()==before
        assert not list(dst.glob('*.tmp'))
    return dict(groupId=9336,configuration_and_copy_passed=True,old_collector_preserved=True,configuration_backup_verified=True,native_Windows_launch=False)

if __name__=='__main__':main()
