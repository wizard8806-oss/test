& {
$ErrorActionPreference='Stop'
$processTarget=Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_08'
$processStage=$null
$controlBundle='__BUNDLE__'
function ProcessHash([byte[]]$data){$h=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($h.ComputeHash($data))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function ReadProcessString($reader){
    $n=$reader.ReadInt32();if($n -lt 0 -or $n -gt 65536){throw 'Invalid script string length'}
    $b=$reader.ReadBytes($n*2);if($b.Length -ne $n*2){throw 'Truncated script string'}
    return [Text.Encoding]::Unicode.GetString($b)
}
function WriteProcessString($writer,[string]$value){$b=[Text.Encoding]::Unicode.GetBytes($value);$writer.Write([int]($b.Length/2));$writer.Write([byte[]]$b)}
function ProcessCodeHash($rec){
    $text=([string]::Join("`n",[string[]]$rec.Lines)).Trim()
    $text=[regex]::Replace($text,'\Aunit\s+'+[regex]::Escape($rec.Name)+'\s*;\s*','',[Text.RegularExpressions.RegexOptions]::IgnoreCase)
    return ProcessHash ([Text.Encoding]::UTF8.GetBytes($text.Trim()))
}
try{
    if(Test-Path -LiteralPath $processTarget){throw ('Destination exists; preserved: '+$processTarget)}
    $candidates=@(
        (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects\codex_diag_07'),
        (Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Documents\Simple-Scada 2\Projects\codex_diag_07'),
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_07')
    )
    $processCandidates=@($candidates | Where-Object {Test-Path -LiteralPath (Join-Path $_ 'Scripts\Scripts.ssc')} | Select-Object -Unique)
    if($processCandidates.Count -eq 1){$processSource=$processCandidates[0]}
    else{$processSource=(Read-Host 'Folder of current codex_diag_07 project').Trim().Trim('"')}
    $processSource=(Get-Item -LiteralPath $processSource).FullName.TrimEnd([char[]]'\/')
    if(-not (Test-Path -LiteralPath (Join-Path $processSource 'Project.spr') -PathType Leaf)){
        $child=Join-Path $processSource 'codex_diag_07'
        if(Test-Path -LiteralPath (Join-Path $child 'Project.spr') -PathType Leaf){$processSource=$child}
        else{throw 'Choose the codex_diag_07 folder containing Project.spr, Pages.spg and Scripts.'}
    }
    $projectBytes=[IO.File]::ReadAllBytes((Join-Path $processSource 'Project.spr'))
    if($projectBytes.Length -lt 16 -or [BitConverter]::ToUInt16($projectBytes,8) -ne 2 -or [BitConverter]::ToUInt16($projectBytes,10) -ne 6 -or [BitConverter]::ToUInt16($projectBytes,12) -ne 15 -or [BitConverter]::ToUInt16($projectBytes,14) -ne 0){throw 'Expected Simple-Scada2.6.15.0 project; source preserved'}
    foreach($required in @('Variables.svr','Servers.ssr','Pages.spg')){
        if(-not (Test-Path -LiteralPath (Join-Path $processSource $required) -PathType Leaf)){throw ('Missing project file: '+$required)}
    }
    if((ProcessHash ([IO.File]::ReadAllBytes((Join-Path $processSource 'Pages.spg')))) -ne '__OLD_PAGES_SHA__'){throw 'Station pages differ from codex_diag_07; source preserved'}
    [byte[]]$old=[IO.File]::ReadAllBytes((Join-Path $processSource 'Scripts\Scripts.ssc'))
    $processInput=[IO.MemoryStream]::new($old);$reader=[IO.BinaryReader]::new($processInput)
    try{
        $next=$reader.ReadInt64();if($next -lt 3 -or $next -gt 100000){throw 'Unexpected script ID counter'}
        $n=$reader.ReadInt32();if($n -lt 0 -or $n -gt 1024){throw 'Unexpected script root'}
        $root=$reader.ReadBytes($n);if($root.Length -ne $n){throw 'Truncated script root'}
        if($reader.ReadInt32() -ne 0 -or $reader.ReadInt32() -ne 3){throw 'Expected three scripts of codex_diag_07; source preserved'}
        $records=@()
        for($i=0;$i -lt 3;$i++){
            $recordStart=$processInput.Position
            $id=$reader.ReadInt64();$name=ReadProcessString $reader;$meta=$reader.ReadBytes(17)
            if($meta.Length -ne 17){throw 'Truncated script metadata'}
            $count=$reader.ReadInt32();if($count -lt 1 -or $count -gt 4096){throw 'Unexpected script size'}
            $lines=[Collections.Generic.List[string]]::new()
            for($j=0;$j -lt $count;$j++){$lines.Add((ReadProcessString $reader))}
            [byte[]]$recordBytes=New-Object byte[] ([int]($processInput.Position-$recordStart))
            [Array]::Copy($old,[long]$recordStart,$recordBytes,[long]0,[long]$recordBytes.Length)
            $records+=@{Id=$id;Name=$name;Meta=$meta;Lines=$lines.ToArray();OriginalBytes=$recordBytes}
        }
        if($processInput.Position -ne $processInput.Length){throw 'Unexpected trailing script data'}
    }finally{$reader.Dispose();$processInput.Dispose()}
    $core=@($records | Where-Object {$_.Name -eq 'StationDiagnostics'})
    $radio=@($records | Where-Object {$_.Name -eq 'StationRadioDiagnostics'})
    $timer=@($records | Where-Object {$_.Name -eq 'StationDiagnosticsTimer'})
    if($core.Count -ne 1 -or $radio.Count -ne 1 -or $timer.Count -ne 1){throw 'Script names do not match; source preserved'}
    $core=$core[0];$radio=$radio[0];$timer=$timer[0]
    if($core.Meta[0] -ne 10 -or $radio.Meta[0] -ne 10 -or $timer.Meta[0] -ne 1){throw 'Unexpected script kinds'}
    if((ProcessCodeHash $core) -ne '__OLD_CORE_SHA__'){throw 'Diagnostic code changed; source preserved'}
    if(([string]::Join("`n",[string[]]$radio.Lines)) -notmatch '(?i)\bprocedure\s+StationRadioUpdate\s*;'){throw 'Expected StationRadioUpdate procedure; source preserved'}
    if(([string]::Join("`n",[string[]]$timer.Lines)).Trim() -ne "begin`n  StationProcessUpdate;`n  StationRadioUpdate;`nend."){throw 'Timer code changed; source preserved'}
    [byte[]]$packed=[Convert]::FromBase64String($controlBundle)
    if((ProcessHash $packed) -ne '__BUNDLE_SHA__'){throw 'Control bundle checksum mismatch'}
    Add-Type -AssemblyName System.IO.Compression
    $mem=[IO.MemoryStream]::new($packed)
    $zip=[IO.Compression.ZipArchive]::new($mem,[IO.Compression.ZipArchiveMode]::Read)
    $items=@{}
    try{
        foreach($entry in $zip.Entries){
            if($entry.Length -gt 1048576 -or $items.ContainsKey($entry.FullName)){throw 'Unexpected or duplicate control entry'}
            $controlEntryStream=$entry.Open();$plain=[IO.MemoryStream]::new()
            try{$controlEntryStream.CopyTo($plain);$items[$entry.FullName]=$plain.ToArray()}
            finally{$controlEntryStream.Dispose();$plain.Dispose()}
        }
    }finally{$zip.Dispose();$mem.Dispose()}
    if($items.Count -ne 6){throw 'Expected six control resources'}
    [byte[]]$moduleBytes=$items['Module.txt'];[byte[]]$newPages=$items['Pages.spg']
    if($moduleBytes.Length -gt 65536 -or (ProcessHash $moduleBytes) -ne '__MODULE_SHA__'){throw 'Module checksum mismatch'}
    if((ProcessHash $newPages) -ne '__PAGES_SHA__'){throw 'Page checksum mismatch'}
    $moduleText=[Text.Encoding]::UTF8.GetString($moduleBytes).TrimEnd([char[]]"`r`n")
    $core.Lines=$moduleText.Split([string[]]@("`r`n","`n"),[StringSplitOptions]::None)
    [Array]::Clear($core.Meta,9,8)
    if(@($records|Where-Object {$_.Id -notin @(0,1,2)}).Count -ne 0){throw 'Unexpected original script IDs'}
    $eventObjects=@('ProcessSpMinus','ProcessSpPlus','ProcessSpApply','ProcessSpCancel')
    $events=@()
    for($eventIndex=0;$eventIndex -lt 4;$eventIndex++){
        $eventName=$eventObjects[$eventIndex]+'_OnClick'
        [byte[]]$eventMeta=New-Object byte[] 17;$eventMeta[0]=1;$eventMeta[6]=1
        [byte[]]$eventBody=$items[$eventName+'.txt']
        if($null -eq $eventBody -or $eventBody.Length -gt 4096){throw 'Missing event source'}
        $eventText=[Text.Encoding]::UTF8.GetString($eventBody).TrimEnd([char[]]"`r`n")
        $events+=@{Id=[long](3+$eventIndex);Name=$eventName;Meta=$eventMeta;Lines=$eventText.Split([string[]]@("`r`n","`n"),[StringSplitOptions]::None)}
    }
    $output=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($output)
    try{
        $writer.Write([long]([Math]::Max($next,7)));$writer.Write([int]$root.Length);$writer.Write([byte[]]$root)
        $writer.Write([int]0);$writer.Write([int]7)
        foreach($rec in $records){
            if($rec.Name -ne 'StationDiagnostics'){$writer.Write([byte[]]$rec.OriginalBytes);continue}
            $writer.Write([long]$rec.Id);WriteProcessString $writer $rec.Name;$writer.Write([byte[]]$rec.Meta)
            $writer.Write([int]$rec.Lines.Count)
            foreach($line in $rec.Lines){WriteProcessString $writer $line}
        }
        foreach($rec in $events){
            $writer.Write([long]$rec.Id);WriteProcessString $writer $rec.Name;$writer.Write([byte[]]$rec.Meta)
            $writer.Write([int]$rec.Lines.Count)
            foreach($line in $rec.Lines){WriteProcessString $writer $line}
        }
        $writer.Flush();[byte[]]$newScripts=$output.ToArray()
    }finally{$writer.Dispose();$output.Dispose()}
    $processStage=$processTarget+'.stage-'+[Guid]::NewGuid().ToString('N')
    $null=[IO.Directory]::CreateDirectory($processStage)
    foreach($dir in Get-ChildItem -LiteralPath $processSource -Directory -Recurse){
        $rel=$dir.FullName.Substring($processSource.Length+1);$null=[IO.Directory]::CreateDirectory((Join-Path $processStage $rel))
    }
    foreach($file in Get-ChildItem -LiteralPath $processSource -File -Recurse){
        $rel=$file.FullName.Substring($processSource.Length+1)
        if($rel.Replace('\','/') -like 'Scripts/Compiled/*'){continue}
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $processStage $rel)
    }
    [IO.File]::WriteAllBytes((Join-Path $processStage 'Scripts\Scripts.ssc'),$newScripts)
    [IO.File]::WriteAllBytes((Join-Path $processStage 'Pages.spg'),$newPages)
    $null=[IO.Directory]::CreateDirectory((Join-Path $processStage 'Scripts\Compiled'))
    foreach($same in @('Project.spr','Variables.svr','Servers.ssr')){
        if((ProcessHash ([IO.File]::ReadAllBytes((Join-Path $processSource $same)))) -ne (ProcessHash ([IO.File]::ReadAllBytes((Join-Path $processStage $same))))){throw ('Copied file verification failed: '+$same)}
    }
    if((ProcessHash ([IO.File]::ReadAllBytes((Join-Path $processStage 'Scripts\Scripts.ssc')))) -ne (ProcessHash $newScripts)){throw 'Script verification failed'}
    if((ProcessHash ([IO.File]::ReadAllBytes((Join-Path $processStage 'Pages.spg')))) -ne '__PAGES_SHA__'){throw 'Copied page verification failed'}
    [IO.Directory]::Move($processStage,$processTarget);$processStage=$null
    Write-Host ('SAVED: '+$processTarget) -ForegroundColor Green
    Write-Host 'Open this copy in Editor. Import PressureSP_Command (ReadWrite R2100, no scaling), F9, save. Buttons write only after Apply from a logged-in SCADA client.'
    Write-Host 'Operator setpoint controls; original project preserved. Installation sends no PLC command. Keep the remote radio collector running.'
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{if($processStage -and (Test-Path -LiteralPath $processStage)){Remove-Item -LiteralPath $processStage -Recurse -Force}}
};
