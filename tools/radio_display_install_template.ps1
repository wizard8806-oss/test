& {
$ErrorActionPreference='Stop'
$radioTarget=Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_02'
$radioStage=$null
$radioBundle=@'
__BUNDLE__
'@
function RadioHash([byte[]]$data){$h=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($h.ComputeHash($data))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function ReadRadioString($reader){
    $n=$reader.ReadInt32();if($n -lt 0 -or $n -gt 65536){throw 'Invalid script string length'}
    $b=$reader.ReadBytes($n*2);if($b.Length -ne $n*2){throw 'Truncated script string'}
    return [Text.Encoding]::Unicode.GetString($b)
}
function WriteRadioString($writer,[string]$value){$b=[Text.Encoding]::Unicode.GetBytes($value);$writer.Write([int]($b.Length/2));$writer.Write([byte[]]$b)}
try{
    if(Test-Path -LiteralPath $radioTarget){throw ('Destination exists; preserved: '+$radioTarget)}
    $candidates=@(
        (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects\codex_diag_01'),
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_01')
    )
    $radioSource=$candidates | Where-Object {Test-Path -LiteralPath (Join-Path $_ 'Scripts\Scripts.ssc')} | Select-Object -First 1
    if(-not $radioSource){$radioSource=(Read-Host 'Folder of current codex_diag_01 project').Trim().Trim('"')}
    $radioSource=(Get-Item -LiteralPath $radioSource).FullName.TrimEnd([char[]]'\/')
    [byte[]]$old=[IO.File]::ReadAllBytes((Join-Path $radioSource 'Scripts\Scripts.ssc'))
    $radioInput=[IO.MemoryStream]::new($old);$reader=[IO.BinaryReader]::new($radioInput)
    try{
        $next=$reader.ReadInt64();if($next -lt 2 -or $next -gt 100000){throw 'Unexpected script ID counter'}
        $n=$reader.ReadInt32();if($n -lt 0 -or $n -gt 1024){throw 'Unexpected script root'}
        $root=$reader.ReadBytes($n)
        if($reader.ReadInt32() -ne 0 -or $reader.ReadInt32() -ne 2){throw 'Expected the two original diagnostic scripts; nothing changed'}
        $records=@()
        for($i=0;$i -lt 2;$i++){
            $id=$reader.ReadInt64();$name=ReadRadioString $reader;$meta=$reader.ReadBytes(17)
            if($meta.Length -ne 17){throw 'Truncated script metadata'}
            $count=$reader.ReadInt32();if($count -lt 1 -or $count -gt 4096){throw 'Unexpected script size'}
            $lines=[Collections.Generic.List[string]]::new()
            for($j=0;$j -lt $count;$j++){$lines.Add((ReadRadioString $reader))}
            $records+=@{Id=$id;Name=$name;Meta=$meta;Lines=$lines.ToArray()}
        }
        if($radioInput.Position -ne $radioInput.Length){throw 'Unexpected trailing script data'}
    }finally{$reader.Dispose();$radioInput.Dispose()}
    $core=@($records | Where-Object {$_.Name -eq 'StationDiagnostics'})
    $timer=@($records | Where-Object {$_.Name -eq 'StationDiagnosticsTimer'})
    if($core.Count -ne 1 -or $timer.Count -ne 1){throw 'Diagnostic script names do not match'}
    $core=$core[0];$timer=$timer[0]
    if($core.Meta[0] -ne 10 -or $timer.Meta[0] -ne 1){throw 'Unexpected script kinds'}
    if((RadioHash ([Text.Encoding]::UTF8.GetBytes(([string]::Join("`n",[string[]]$core.Lines)).Trim()))) -ne '__CORE_SHA__'){throw 'Main diagnostic code changed; preserved'}
    if((RadioHash ([Text.Encoding]::UTF8.GetBytes(([string]::Join("`n",[string[]]$timer.Lines)).Trim()))) -ne '__TIMER_SHA__'){throw 'Timer code changed; preserved'}
    [byte[]]$bundle=[Convert]::FromBase64String($radioBundle)
    if((RadioHash $bundle) -ne '__BUNDLE_SHA__'){throw 'Transfer checksum mismatch; copy the complete block again'}
    Add-Type -AssemblyName System.IO.Compression
    $mem=[IO.MemoryStream]::new($bundle);$zip=[IO.Compression.ZipArchive]::new($mem,[IO.Compression.ZipArchiveMode]::Read,$false)
    $payload=@{}
    try{
        if($zip.Entries.Count -ne 2){throw 'Invalid radio bundle'}
        foreach($entry in $zip.Entries){
            if($entry.FullName -notin @('RadioModule.txt','RadioCollector.ps1')){throw 'Invalid bundle entry'}
            $s=$entry.Open();$m=[IO.MemoryStream]::new()
            try{$s.CopyTo($m);$payload[$entry.FullName]=$m.ToArray()}finally{$s.Dispose();$m.Dispose()}
        }
    }finally{$zip.Dispose();$mem.Dispose()}
    $meta=[byte[]]$core.Meta.Clone();[BitConverter]::GetBytes([int]63000).CopyTo($meta,2)
    [Array]::Clear($meta,9,8)
    $moduleText=[Text.Encoding]::UTF8.GetString($payload['RadioModule.txt']).TrimEnd([char[]]"`r`n")
    $module=@{Id=$next;Name='StationRadioDiagnostics';Meta=$meta;Lines=$moduleText.Split([string[]]@("`r`n","`n"),[StringSplitOptions]::None)}
    $timer.Lines=@('begin','  StationDiagUpdate;','  StationRadioUpdate;','end.')
    $output=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($output)
    try{
        $writer.Write([long]($next+1));$writer.Write([int]$root.Length);$writer.Write([byte[]]$root)
        $writer.Write([int]0);$writer.Write([int]3)
        foreach($rec in @($core,$module,$timer)){
            $writer.Write([long]$rec.Id);WriteRadioString $writer $rec.Name;$writer.Write([byte[]]$rec.Meta)
            $writer.Write([int]$rec.Lines.Count)
            foreach($line in $rec.Lines){WriteRadioString $writer $line}
        }
        $writer.Flush();[byte[]]$newScripts=$output.ToArray()
    }finally{$writer.Dispose();$output.Dispose()}
    $radioStage=$radioTarget+'.stage-'+[Guid]::NewGuid().ToString('N')
    $null=[IO.Directory]::CreateDirectory($radioStage)
    foreach($dir in Get-ChildItem -LiteralPath $radioSource -Directory -Recurse){
        $rel=$dir.FullName.Substring($radioSource.Length+1);$null=[IO.Directory]::CreateDirectory((Join-Path $radioStage $rel))
    }
    foreach($file in Get-ChildItem -LiteralPath $radioSource -File -Recurse){
        $rel=$file.FullName.Substring($radioSource.Length+1)
        if($rel.Replace('\','/') -like 'Scripts/Compiled/*'){continue}
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $radioStage $rel)
    }
    [IO.File]::WriteAllBytes((Join-Path $radioStage 'Scripts\Scripts.ssc'),$newScripts)
    $null=[IO.Directory]::CreateDirectory((Join-Path $radioStage 'Scripts\Compiled'))
    $tools=Join-Path $radioStage 'Tools';$null=[IO.Directory]::CreateDirectory($tools)
    [IO.File]::WriteAllBytes((Join-Path $tools 'Run-Radio-Usb-Collector-01.ps1'),$payload['RadioCollector.ps1'])
    [IO.Directory]::Move($radioStage,$radioTarget);$radioStage=$null
    Write-Host ('SAVED: '+$radioTarget) -ForegroundColor Green
    Write-Host 'Open this copy in Editor, F9, save. Then start the collector. Original preserved.'
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{if($radioStage -and (Test-Path -LiteralPath $radioStage)){Remove-Item -LiteralPath $radioStage -Recurse -Force}}
};
