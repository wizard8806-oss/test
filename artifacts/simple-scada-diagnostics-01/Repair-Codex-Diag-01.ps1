& {
$ErrorActionPreference='Stop'
$diagFolders=@(
    (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects\codex_diag_01'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_01')
)
function Get-DiagHash([byte[]]$bytes){
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}
    finally{$sha.Dispose()}
}
$diagOld='8f2f1221fb2527ba4348f900634a09f3a7e6d94c0101babb0b1df45ae92af882'
$diagNew='c6c8cee14b108244e9dd78a3323ca98fff3b5513ded1ec3cbfecb974171655e7'
$diagTemp=$null
try{
    $diagFound=@($diagFolders | Where-Object {Test-Path -LiteralPath (Join-Path $_ 'Pages.spg')} | Select-Object -Unique)
    if($diagFound.Count -eq 0){
        $diagFound=@((Read-Host 'Full path to codex_diag_01 folder').Trim().Trim('"'))
    }
    $diagJobs=@()
    foreach($folder in $diagFound){
        $path=Join-Path $folder 'Pages.spg'
        [byte[]]$bytes=[IO.File]::ReadAllBytes($path)
        $hash=Get-DiagHash $bytes
        if($hash -eq $diagNew){Write-Host ('ALREADY FIXED: '+$folder) -ForegroundColor Green;continue}
        if($hash -ne $diagOld){throw ('Unexpected Pages.spg. Nothing replaced: '+$path)}
        if((Get-FileHash -LiteralPath (Join-Path $folder 'Scripts\Scripts.ssc') -Algorithm SHA256).Hash.ToLowerInvariant() -ne '9de6f831ff9235552e1f4992f03b8d1eb747b3927c60b655521ce61581dc09e4'){
            throw ('Scripts changed. Nothing replaced: '+$folder)
        }
        [BitConverter]::GetBytes([long]2).CopyTo($bytes,0)
        [BitConverter]::GetBytes([long]1).CopyTo($bytes,1994)
        $starts=@(599,849,1121,1359,1577,1775,2167,2375,2621,2888,3143,3410,3658,3909,4234,4519,4767,5204)
        for($i=0;$i -lt $starts.Count;$i++){
            $offset=$starts[$i]
            [Array]::Clear($bytes,$offset+49,9)
            $layer=if($i -lt 6){$i+2}else{$i-6}
            [BitConverter]::GetBytes([int]$layer).CopyTo($bytes,$offset+54)
            [BitConverter]::GetBytes([long]-1).CopyTo($bytes,$offset+111)
        }
        if((Get-DiagHash $bytes) -ne $diagNew){throw 'Repair checksum mismatch. Nothing replaced.'}
        $diagJobs+=@{Path=$path;Bytes=$bytes}
    }
    foreach($job in $diagJobs){
        if((Get-FileHash -LiteralPath $job.Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $diagOld){throw 'Pages changed during repair. Close Editor and repeat.'}
        $id=[Guid]::NewGuid().ToString('N')
        $diagTemp=$job.Path+'.repair-'+$id
        $backup=$job.Path+'.before-repair-'+$id+'.bak'
        [IO.File]::WriteAllBytes($diagTemp,$job.Bytes)
        [IO.File]::Replace($diagTemp,$job.Path,$backup)
        $diagTemp=$null
        Write-Host ('FIXED: '+$job.Path) -ForegroundColor Green
        Write-Host ('BACKUP: '+$backup)
    }
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($diagTemp -and (Test-Path -LiteralPath $diagTemp)){Remove-Item -LiteralPath $diagTemp -Force}
}
};
