param(
 [Parameter(Mandatory=$true)][string]$SourcePath,
 [string]$TargetPath
)
# File-only SCADA10 -> SCADA11 copy. No Editor/Server/OPC/SQL is started.
$ErrorActionPreference='Stop'
$uiStage=$null
function UiHash([byte[]]$Bytes) {
 $digest=[Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($digest.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
 finally { $digest.Dispose() }
}
function UiReadString($Reader) {
 $count=$Reader.ReadInt32()
 if($count -lt 0 -or $count -gt 65536){throw 'Invalid script string length'}
 $bytes=$Reader.ReadBytes($count*2)
 if($bytes.Length -ne $count*2){throw 'Truncated script string'}
 return [Text.Encoding]::Unicode.GetString($bytes)
}
function UiWriteString($Writer,[string]$Text) {
 $bytes=[Text.Encoding]::Unicode.GetBytes($Text)
 $Writer.Write([int]($bytes.Length/2));$Writer.Write([byte[]]$bytes)
}
function UiFiles([string]$Directory) {
 $table=@{}
 foreach($file in Get-ChildItem -LiteralPath $Directory -Force -Recurse -File) {
  $relative=$file.FullName.Substring($Directory.Length+1).Replace('\','/')
  $table[$relative]=UiHash ([IO.File]::ReadAllBytes($file.FullName))
 }
 return $table
}
try {
 $uiSource=(Get-Item -LiteralPath $SourcePath).FullName.TrimEnd([char[]]'\/')
 if(-not (Test-Path -LiteralPath $uiSource -PathType Container)){throw 'Expected an existing SCADA10 directory'}
 if(-not $TargetPath) {
  if(-not $env:LOCALAPPDATA){throw 'Specify a private TargetPath outside the source project'}
  $TargetPath=Join-Path $env:LOCALAPPDATA 'CodexCandidates\SCADA11\codex_diag_11'
 }
 $uiTarget=[IO.Path]::GetFullPath($TargetPath).TrimEnd([char[]]'\/')
 $comparison=[StringComparison]::OrdinalIgnoreCase
 if($uiTarget.Equals($uiSource,$comparison) -or $uiTarget.StartsWith($uiSource+[IO.Path]::DirectorySeparatorChar,$comparison) -or $uiSource.StartsWith($uiTarget+[IO.Path]::DirectorySeparatorChar,$comparison)){throw 'Destination must be separate from source'}
 if(Test-Path -LiteralPath $uiTarget){throw 'Destination already exists; preserved'}
 foreach($item in Get-ChildItem -LiteralPath $uiSource -Recurse -Force) {
  if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Reparse points are not accepted in the source copy'}
 }
 $before=UiFiles $uiSource
 $pinned=@{
  'Pages.spg'='7ac3a4647f7a49b0d5c50d88dd024ab38e92ee427e59101dd929c3ebcc1e631b'
  'Scripts/Scripts.ssc'='51cc9561bb7a2b3ad3b7068db28b860d70ef9587a4586ea27a0d0eb683e7a858'
  'Variables.svr'='c13c163398f114a4c8ba96a93f1355a876692a65ee3b020cf32e95bb9634fd3a'
  'Servers.ssr'='c0662185786f2204479c9ad90d2dcc2ed0dbb79d9d532942f1841f650ef498b6'
 }
 foreach($name in $pinned.Keys) {
  if(-not $before.ContainsKey($name) -or $before[$name] -ne $pinned[$name]){throw ('Source differs from reviewed SCADA10: '+$name)}
 }
 $project=[IO.File]::ReadAllBytes((Join-Path $uiSource 'Project.spr'))
 if($project.Length -lt 16 -or [BitConverter]::ToUInt16($project,8) -ne 2 -or [BitConverter]::ToUInt16($project,10) -ne 6 -or [BitConverter]::ToUInt16($project,12) -ne 15 -or [BitConverter]::ToUInt16($project,14) -ne 0){throw 'Expected Simple-Scada2.6.15.0'}
 [byte[]]$emptyWindows=@(3,0,0,0,46,46,92,0,0,0,0,0,0,0,0,3,0,0,0,46,46,92,0,0,0,0,0,0,0,0)
 if(-not $before.ContainsKey('Windows.swn') -or $before['Windows.swn'] -ne (UiHash $emptyWindows)){throw 'Existing windows require a reviewed merge; source preserved'}
 [byte[]]$packetRaw=[Convert]::FromBase64String('__PACKET__')
 if((UiHash $packetRaw) -ne '__PACKET_SHA__'){throw 'Package checksum mismatch'}
 $packet=[Text.Encoding]::UTF8.GetString($packetRaw)|ConvertFrom-Json
 if($packet.schemaVersion -ne 1){throw 'Unknown UI package'}
 [byte[]]$raw=[IO.File]::ReadAllBytes((Join-Path $uiSource 'Scripts/Scripts.ssc'))
 $memory=[IO.MemoryStream]::new($raw);$reader=[IO.BinaryReader]::new($memory)
 try {
  $next=$reader.ReadInt64();$length=$reader.ReadInt32();if($length -lt 0 -or $length -gt 1024){throw 'Unexpected scripts root'}
  $root=$reader.ReadBytes($length);$groups=$reader.ReadInt32();$count=$reader.ReadInt32()
  if($root.Length -ne $length -or $groups -ne 0 -or $count -ne 7 -or $next -ne 7){throw 'Expected the seven reviewed SCADA10 scripts'}
  $rows=[Collections.Generic.List[object]]::new()
  for($i=0;$i -lt $count;$i++) {
   $id=$reader.ReadInt64();$name=UiReadString $reader;$meta=$reader.ReadBytes(17);$linesCount=$reader.ReadInt32()
   if($meta.Length -ne 17 -or $linesCount -lt 1 -or $linesCount -gt 4096){throw 'Invalid script record'}
   $lines=[Collections.Generic.List[string]]::new()
   for($j=0;$j -lt $linesCount;$j++){$lines.Add((UiReadString $reader))}
   $rows.Add(@{Id=$id;Name=$name;Meta=$meta;Lines=$lines.ToArray()})
  }
  if($memory.Position -ne $memory.Length){throw 'Unexpected trailing script data'}
 } finally {$reader.Dispose();$memory.Dispose()}
 $displayCore=@($rows|Where-Object {$_.Name -ceq 'StationDiagnostics'})
 if($displayCore.Count -ne 1 -or @($packet.pressureDisplayChanges).Count -ne 8){throw 'Reviewed pressure display module not found'}
 $displayBody=[string]::Join("`n",[string[]]$displayCore[0].Lines)
 foreach($edit in $packet.pressureDisplayChanges) {
  if([regex]::Matches($displayBody,[regex]::Escape([string]$edit.old)).Count -ne 1){throw 'Pressure display expression differs; source preserved'}
  $displayBody=$displayBody.Replace([string]$edit.old,[string]$edit.new)
 }
 $displayCore[0].Lines=$displayBody.Split([string[]]@("`n"),[StringSplitOptions]::None)
 $timer=@($rows|Where-Object {$_.Name -eq 'StationDiagnosticsTimer'})
 if($timer.Count -ne 1 -or $timer[0].Id -ne 1){throw 'Reviewed timer not found'}
 $timer=$timer[0];$body=[string]::Join("`n",[string[]]$timer.Lines)
 if([regex]::Matches($body,'StationProcessUpdate\s*;').Count -ne 1){throw 'Reviewed process refresh call not found'}
 $body=[regex]::Replace($body,'StationProcessUpdate\s*;','StationProcessUpdate;'+"`n"+'  OperatorUiUpdate;')
 $timer.Lines=$body.Split([string[]]@("`n"),[StringSplitOptions]::None)
 $added=@(@{id=7;name='OperatorConsole';body=[string]$packet.module;prototype='StationDiagnostics'})
 foreach($event in $packet.events){$added+=@{id=[long]$event.id;name=[string]$event.name;body=[string]$event.body;prototype='ProcessSpPlus_OnClick'}}
 foreach($item in $added) {
  $prototype=@($rows|Where-Object {$_.Name -ceq $item.prototype})
  if($prototype.Count -ne 1){throw 'Reviewed script metadata prototype not found'}
  [byte[]]$meta=$prototype[0].Meta.Clone()
  [BitConverter]::GetBytes([int](170000+4*$item.id)).CopyTo($meta,2)
  $rows.Add(@{Id=[long]$item.id;Name=[string]$item.name;Meta=$meta;Lines=$item.body.Split([string[]]@("`n"),[StringSplitOptions]::None)})
 }
 $stream=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($stream)
 try {
  $writer.Write([long](8+$packet.events.Count));$writer.Write([int]$root.Length);$writer.Write([byte[]]$root);$writer.Write([int]0);$writer.Write([int]$rows.Count)
  foreach($row in $rows) {
   [Array]::Clear($row.Meta,9,8)
   $writer.Write([long]$row.Id);UiWriteString $writer $row.Name;$writer.Write([byte[]]$row.Meta);$writer.Write([int]$row.Lines.Count)
   foreach($line in $row.Lines){UiWriteString $writer $line}
  }
  $writer.Flush();$newScripts=$stream.ToArray()
 } finally {$writer.Dispose();$stream.Dispose()}
 $uiStage=$uiTarget+'.stage-'+[Guid]::NewGuid().ToString('N')
 $null=[IO.Directory]::CreateDirectory($uiStage)
 if([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
  $acl=[Security.AccessControl.DirectorySecurity]::new();$acl.SetAccessRuleProtection($true,$false)
  $inherit=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
  foreach($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))){$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl',$inherit,'None','Allow'))}
  Set-Acl -LiteralPath $uiStage -AclObject $acl
 }
 foreach($dir in Get-ChildItem -LiteralPath $uiSource -Directory -Recurse -Force) {
  $relative=$dir.FullName.Substring($uiSource.Length+1);$null=[IO.Directory]::CreateDirectory((Join-Path $uiStage $relative))
 }
 foreach($file in Get-ChildItem -LiteralPath $uiSource -File -Recurse -Force) {
  $relative=$file.FullName.Substring($uiSource.Length+1).Replace('\','/')
  if($relative -like 'Scripts/Compiled/*' -or $file.Extension -ieq '.exs'){continue}
  Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $uiStage $relative)
 }
 [IO.File]::WriteAllBytes((Join-Path $uiStage 'Pages.spg'),[Convert]::FromBase64String($packet.pages))
 [IO.File]::WriteAllBytes((Join-Path $uiStage 'Windows.swn'),[Convert]::FromBase64String($packet.windows))
 [IO.File]::WriteAllBytes((Join-Path $uiStage 'Scripts/Scripts.ssc'),$newScripts)
 $afterSource=UiFiles $uiSource;$candidate=UiFiles $uiStage
 if($afterSource.Count -ne $before.Count){throw 'Source changed while copying; retry after preserving Editor state'}
 foreach($relative in $before.Keys) {
  if(-not $afterSource.ContainsKey($relative) -or $before[$relative] -ne $afterSource[$relative]){throw ('Source changed while copying: '+$relative)}
  if($relative -in @('Pages.spg','Windows.swn','Scripts/Scripts.ssc') -or $relative -like 'Scripts/Compiled/*' -or [IO.Path]::GetExtension($relative) -ieq '.exs'){continue}
  if(-not $candidate.ContainsKey($relative) -or $before[$relative] -ne $candidate[$relative]){throw ('Preservation check failed: '+$relative)}
 }
 $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($uiTarget))
 [IO.Directory]::Move($uiStage,$uiTarget);$uiStage=$null
 Write-Host ('SAVED: '+$uiTarget) -ForegroundColor Green
 Write-Host 'Candidate only. Native compile/save and trend/archive checks are required before activation. Source SCADA10 and all processes preserved.'
} finally {
 if($uiStage -and (Test-Path -LiteralPath $uiStage)){Remove-Item -LiteralPath $uiStage -Recurse -Force}
}
