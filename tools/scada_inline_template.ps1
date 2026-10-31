& {
$ErrorActionPreference='Stop'
$diagSource=Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects\codex'
$diagTarget=Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_01'
$diagStage=$null
$diagCapsule=@'
__CAPSULE__
'@
function Get-DiagHash([byte[]]$bytes){
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()}
    finally{$sha.Dispose()}
}
try{
    [byte[]]$diagBytes=[Convert]::FromBase64String($diagCapsule)
    if((Get-DiagHash $diagBytes) -ne '__CAPSULE_SHA__'){throw 'Transfer checksum mismatch. Copy the complete block again.'}
    if(!(Test-Path -LiteralPath $diagSource -PathType Container)){
        $diagSource=Read-Host 'Full path to the original codex project folder'
    }
    $diagSource=(Get-Item -LiteralPath $diagSource).FullName.TrimEnd([char[]]'\/')
    if(Test-Path -LiteralPath $diagTarget){throw 'Destination already exists. Existing files were preserved.'}
    $diagExpected=@{
__SOURCE_HASHES__
    }
    foreach($rel in $diagExpected.Keys){
        $path=Join-Path $diagSource $rel
        if(!(Test-Path -LiteralPath $path -PathType Leaf)){throw ('Missing source file: '+$rel)}
        if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $diagExpected[$rel]){
            throw ('Source changed since upload: '+$rel+'. Nothing was replaced.')
        }
    }
    Add-Type -AssemblyName System.IO.Compression
    $diagStage=$diagTarget+'.stage-'+[Guid]::NewGuid().ToString('N')
    $null=[IO.Directory]::CreateDirectory($diagStage)
    foreach($dir in Get-ChildItem -LiteralPath $diagSource -Directory -Recurse){
        $rel=$dir.FullName.Substring($diagSource.Length+1)
        $null=[IO.Directory]::CreateDirectory((Join-Path $diagStage $rel))
    }
    foreach($file in Get-ChildItem -LiteralPath $diagSource -File -Recurse){
        $rel=$file.FullName.Substring($diagSource.Length+1)
        if($rel.Replace('\','/') -like 'Scripts/Compiled/*'){continue}
        $path=Join-Path $diagStage $rel
        $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
        Copy-Item -LiteralPath $file.FullName -Destination $path
    }
    $memory=[IO.MemoryStream]::new($diagBytes)
    $zip=[IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Read,$false)
    try{
        if($zip.Entries.Count -ne 2){throw 'Unexpected capsule entry count'}
        foreach($entry in $zip.Entries){
            if($entry.FullName -notin @('Pages.spg','Scripts/Scripts.ssc')){throw 'Unexpected capsule entry name'}
            $path=Join-Path $diagStage $entry.FullName
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
            $diagEntryInput=$entry.Open();$diagEntryOutput=[IO.MemoryStream]::new()
            try{$diagEntryInput.CopyTo($diagEntryOutput);[IO.File]::WriteAllBytes($path,$diagEntryOutput.ToArray())}
            finally{$diagEntryInput.Dispose();$diagEntryOutput.Dispose()}
        }
    }finally{$zip.Dispose();$memory.Dispose()}
    $diagOutputHashes=@{
__OUTPUT_HASHES__
    }
    foreach($rel in $diagOutputHashes.Keys){
        if((Get-FileHash -LiteralPath (Join-Path $diagStage $rel) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $diagOutputHashes[$rel]){
            throw 'Prepared output checksum mismatch'
        }
    }
    $null=[IO.Directory]::CreateDirectory((Join-Path $diagStage 'Scripts/Compiled'))
    [IO.Directory]::Move($diagStage,$diagTarget)
    $diagStage=$null
    Write-Host ('SAVED: '+$diagTarget) -ForegroundColor Green
    Write-Host 'Original preserved. Open Project.spr in Editor 2.6.15, press F9, then save.'
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($null -ne $diagStage -and (Test-Path -LiteralPath $diagStage)){
        Remove-Item -LiteralPath $diagStage -Recurse -Force
    }
}
};
