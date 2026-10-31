#!/usr/bin/env python3
"""Compile the unchanged C# payload against .NET Framework4.8 references.

Also exercise the Windows-install repair on real PowerShell/Linux, without cloud.
The Framework references are public Microsoft NuGet package1.0.3, downloaded
only to /tmp; no reference assemblies or compiler are sent to the user.
"""
import concurrent.futures,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
from validate_radio_service_01 import run,OUT,SCRIPT,PWSH

OLD_SHA='d09c645ace7a060f5d78e9d8b026ba61245f8607e9c07e772deeea5165d18502'
NEW_SHA='e334ef94c55230352441ba44471598faa2212e4dcfa7217a46d2f9d952624585'

def sha(b):return hashlib.sha256(b).hexdigest()
def old_source():
    current=SCRIPT.read_text()
    added="$svcTypeOptions=@{}\nif($PSVersionTable.PSVersion.Major -lt 6){\n $svcTypeOptions.ReferencedAssemblies=@('System.dll','System.Core.dll','System.Xml.dll')\n}\nAdd-Type @svcTypeOptions -TypeDefinition @'"
    assert current.count(added)==1
    old=current.replace(added,"Add-Type -TypeDefinition @'")
    assert sha(old.encode())==OLD_SHA and sha(current.encode())==NEW_SHA
    old_cs=re.search(r"(?ms)^Add-Type.*?@'\n(.*?)\n'@",old)[1]
    new_cs=re.search(r"(?ms)^Add-Type.*?@'\n(.*?)\n'@",current)[1]
    assert old_cs==new_cs,'Transport code changed'
    return old,new_cs

def framework_compile():
    old,cs=old_source()
    ref=Path(os.environ['CODEX_FRAMEWORK48_REFS'])
    assert all((ref/n).exists() for n in ['mscorlib.dll','System.dll','System.Core.dll','System.Xml.dll'])
    with tempfile.TemporaryDirectory(prefix='service-fw48-') as t:
        p=Path(t);(p/'source.cs').write_text(cs)
        code=r'''
Add-Type -AssemblyName Microsoft.CodeAnalysis
Add-Type -AssemblyName Microsoft.CodeAnalysis.CSharp
$tree=[Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText('__SOURCE__'))
foreach($includeXml in @($false,$true)){
 $references=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
 $names=@('mscorlib.dll','System.dll','System.Core.dll')
 if($includeXml){$names+=@('System.Xml.dll')}
 foreach($name in $names){$references.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile((Join-Path '__REF__' $name)))}
 $options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]::DynamicallyLinkedLibrary)
 $comp=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create('ServiceFrameworkTest',[Microsoft.CodeAnalysis.SyntaxTree[]]@($tree),[Microsoft.CodeAnalysis.MetadataReference[]]$references.ToArray(),$options)
 $output=[IO.MemoryStream]::new()
 try{
  $result=$comp.Emit($output)
  $errors=@($result.Diagnostics|Where-Object {$_.Severity -eq 'Error'})
  if($includeXml){if(-not $result.Success){throw ($errors -join "`n")};Write-Host 'PASS Framework4.8: C# payload compiles with explicit System.Xml.dll'}
  else{if($result.Success -or -not ($errors|Where-Object {$_.Id -eq 'CS0234'})){throw 'Missing-Xml baseline was not reproduced'};Write-Host 'PASS Framework4.8: missing System.Xml reproduces CS0234'}
 }finally{$output.Dispose()}
}
'''.replace('__SOURCE__',str(p/'source.cs')).replace('__REF__',str(ref))
        (p/'run.ps1').write_text(code)
        env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
        r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(p/'run.ps1')],env=env,capture_output=True,text=True,timeout=30)
        assert r.returncode==0 and not r.stderr,(r.stdout,r.stderr)
        return dict(result=r.stdout.strip(),reference_sha256={n:sha((ref/n).read_bytes()) for n in ['mscorlib.dll','System.dll','System.Core.dll','System.Xml.dll']},actual_Windows_PowerShell_run=False)

def repair():
    old,cs=old_source();source=(OUT/'Fix-Service-Xml-Reference-01.ps1').read_text()
    launch="& ([scriptblock]::Create([IO.File]::ReadAllText($xmlPath,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath (Join-Path $xmlDirectory 'stations.json')"
    assert source.count(launch)==1
    cases=[]
    for case in ['old_file','already_fixed','modified_file','foreign_backup','known_backup','CRLF_paste']:
        with tempfile.TemporaryDirectory(prefix='service-xml-repair-') as t:
            p=Path(t);dst=p/'RadioServicePilot01';dst.mkdir();f=dst/SCRIPT.name
            data=SCRIPT.read_bytes() if case=='already_fixed' else old.encode()
            if case=='modified_file':data+=b'\n# User changes\n'
            f.write_bytes(data);(dst/'stations.json').write_text('user config remains unchanged')
            backup=Path(str(f)+'.before-xml-fix.bak')
            if case in ['foreign_backup','known_backup']:backup.write_bytes(b'foreign file' if case=='foreign_backup' else old.encode())
            before={x.name:sha(x.read_bytes()) for x in dst.iterdir()}
            code=re.sub(r'^\$xmlDirectory=.*$',lambda _:"$xmlDirectory='"+str(dst)+"'",source,count=1,flags=re.M)
            code=code.replace(launch,"Write-Host 'LAUNCH_READY'")
            if case=='CRLF_paste':code=code.replace('\n','\r\n')
            runner=p/'run.ps1';runner.write_bytes(code.encode())
            env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
            r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(runner)],env=env,capture_output=True,text=True,timeout=15)
            assert r.returncode==0 and not r.stderr,(case,r.stdout,r.stderr)
            assert (dst/'stations.json').read_text()=='user config remains unchanged'
            if case in ['modified_file','foreign_backup']:
                assert 'ERROR:' in r.stdout and 'LAUNCH_READY' not in r.stdout
                assert {x.name:sha(x.read_bytes()) for x in dst.iterdir()}==before
            else:
                assert 'LAUNCH_READY' in r.stdout and 'ERROR:' not in r.stdout,(case,r.stdout)
                assert f.read_bytes()==SCRIPT.read_bytes()
                if case!='already_fixed':assert backup.read_bytes()==old.encode()
            assert not list(dst.glob('*.tmp'))
            cases.append(dict(case=case,passed=True));print('PASS XML repair',case,flush=True)
    return cases

def main():
    compiled=framework_compile();print(compiled['result'],flush=True)
    copies=repair()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:transport=list(pool.map(run,['normal','fragmented']))
    for case in transport:print('PASS unchanged transport',case['case'],flush=True)
    report=dict(date='2026-10-30',CSharp_transport_unchanged=True,framework_compile=compiled,repair_cases=copies,transport_cases=transport,
        old_collector_sha256=OLD_SHA,new_collector_sha256=NEW_SHA,actual_cloud_success=False,native_Windows_run=False)
    (OUT/'xml-reference-validation-2026-10-30.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
