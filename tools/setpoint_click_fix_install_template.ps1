& {
$ErrorActionPreference='Stop'
$clickTarget=Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_09'
$clickStage=$null
$clickCatalog='__CATALOG__'
function ClickHash([byte[]]$data){$h=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($h.ComputeHash($data))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function ClickReadString($r){$n=$r.ReadInt32();if($n -lt 0 -or $n -gt 65536){throw 'Invalid script string'};$b=$r.ReadBytes($n*2);if($b.Length -ne $n*2){throw 'Truncated script string'};return [Text.Encoding]::Unicode.GetString($b)}
function ClickWriteString($w,[string]$s){$b=[Text.Encoding]::Unicode.GetBytes($s);$w.Write([int]($b.Length/2));$w.Write([byte[]]$b)}
function ClickBody($rec){$s=[string]::Join("`n",[string[]]$rec.Lines);return ([regex]::Replace($s.Trim(),'\Aunit\s+'+[regex]::Escape($rec.Name)+'\s*;\s*','',[Text.RegularExpressions.RegexOptions]::IgnoreCase)).Trim()}
try{
 if(Test-Path -LiteralPath $clickTarget){throw ('Destination exists; preserved: '+$clickTarget)}
 $candidates=@(
  (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects\codex_diag_08'),
  (Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Documents\Simple-Scada 2\Projects\codex_diag_08'),
  (Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_diag_08')
 )
 $found=@($candidates|Where-Object {Test-Path -LiteralPath (Join-Path $_ 'Project.spr')}|Select-Object -Unique)
 if($found.Count -eq 1){$clickSource=$found[0]}else{$clickSource=(Read-Host 'Folder of current codex_diag_08 project').Trim().Trim('"')}
 $clickSource=(Get-Item -LiteralPath $clickSource).FullName.TrimEnd([char[]]'\/')
 if(-not (Test-Path -LiteralPath (Join-Path $clickSource 'Project.spr'))){$child=Join-Path $clickSource 'codex_diag_08';if(Test-Path -LiteralPath (Join-Path $child 'Project.spr')){$clickSource=$child}else{throw 'Choose the codex_diag_08 folder containing Project.spr'}}
 [byte[]]$project=[IO.File]::ReadAllBytes((Join-Path $clickSource 'Project.spr'))
 if($project.Length -lt 16 -or [BitConverter]::ToUInt16($project,8) -ne 2 -or [BitConverter]::ToUInt16($project,10) -ne 6 -or [BitConverter]::ToUInt16($project,12) -ne 15 -or [BitConverter]::ToUInt16($project,14) -ne 0){throw 'Expected Simple-Scada2.6.15.0; source preserved'}
 foreach($name in @('Variables.svr','Servers.ssr','Pages.spg','Scripts\Scripts.ssc')){if(-not (Test-Path -LiteralPath (Join-Path $clickSource $name) -PathType Leaf)){throw ('Missing file: '+$name)}}
 if((ClickHash ([IO.File]::ReadAllBytes((Join-Path $clickSource 'Pages.spg')))) -ne '__PAGES_SHA__'){throw 'Pages differ from reviewed native08; source preserved'}
 [byte[]]$raw=[IO.File]::ReadAllBytes((Join-Path $clickSource 'Scripts\Scripts.ssc'))
 $stream=[IO.MemoryStream]::new($raw);$r=[IO.BinaryReader]::new($stream)
 try{
  $next=$r.ReadInt64();$n=$r.ReadInt32();if($next -lt 7 -or $next -gt 100000 -or $n -lt 0 -or $n -gt 1024){throw 'Unexpected script header'}
  $root=$r.ReadBytes($n);if($root.Length -ne $n -or $r.ReadInt32() -ne 0 -or $r.ReadInt32() -ne 7){throw 'Expected seven scripts of08'}
  $rows=@()
  for($i=0;$i -lt 7;$i++){
   $start=$stream.Position;$id=$r.ReadInt64();$name=ClickReadString $r;$meta=$r.ReadBytes(17)
   $count=$r.ReadInt32();if($meta.Length -ne 17 -or $count -lt 1 -or $count -gt 4096){throw 'Invalid script record'}
   $lines=[Collections.Generic.List[string]]::new();for($j=0;$j -lt $count;$j++){$lines.Add((ClickReadString $r))}
   [byte[]]$original=New-Object byte[] ([int]($stream.Position-$start));[Array]::Copy($raw,[long]$start,$original,[long]0,[long]$original.Length)
   $rows+=@{Id=$id;Name=$name;Meta=$meta;Lines=$lines.ToArray();Original=$original;Changed=$false}
  }
  if($stream.Position -ne $stream.Length){throw 'Unexpected trailing script data'}
 }finally{$r.Dispose();$stream.Dispose()}
 $clickSeenIDs=@{};$clickSeenNames=@{}
 foreach($row in $rows){
  $clickIDKey=[string]$row['Id'];$clickNameKey=[string]$row['Name']
  if($clickSeenIDs.ContainsKey($clickIDKey) -or $clickSeenNames.ContainsKey($clickNameKey)){throw 'Duplicate script names or IDs'}
  $clickSeenIDs[$clickIDKey]=$true;$clickSeenNames[$clickNameKey]=$true
 }
 $core=@($rows|Where-Object {$_.Name -eq 'StationDiagnostics'});if($core.Count -ne 1 -or $core[0].Id -ne 0 -or $core[0].Meta[0] -ne 10){throw 'Core module not found'};$core=$core[0]
 $body=ClickBody $core;if((ClickHash ([Text.Encoding]::UTF8.GetBytes($body))) -ne '__OLD_CORE_SHA__'){throw 'Core differs from reviewed08; source preserved'}
 [byte[]]$catalogBytes=[Convert]::FromBase64String($clickCatalog);if((ClickHash $catalogBytes) -ne '__CATALOG_SHA__'){throw 'Patch checksum mismatch'}
 $catalog=[Text.Encoding]::UTF8.GetString($catalogBytes)|ConvertFrom-Json
 foreach($patch in $catalog.changes){if([regex]::Matches($body,[regex]::Escape([string]$patch.old)).Count -ne [int]$patch.count){throw 'Patch context differs; source preserved'};$body=$body.Replace([string]$patch.old,[string]$patch.new)}
 if((ClickHash ([Text.Encoding]::UTF8.GetBytes($body))) -ne '__NEW_CORE_SHA__'){throw 'Patched core verification failed'}
 $core.Lines=$body.Split([string[]]@("`n"),[StringSplitOptions]::None);$core.Changed=$true
 $eventNames=@('ProcessSpMinus_OnClick','ProcessSpPlus_OnClick','ProcessSpApply_OnClick','ProcessSpCancel_OnClick')
 for($i=0;$i -lt 4;$i++){
  $name=$eventNames[$i];$event=@($rows|Where-Object {$_.Name -eq $name})
  if($event.Count -ne 1 -or $event[0].Id -ne (3+$i) -or $event[0].Meta[0] -ne 1 -or $event[0].Meta[1] -ne 0){throw ('Unexpected event: '+$name)};$event=$event[0]
  if((ClickBody $event) -ne [string]$catalog.oldEvents.$name){throw ('Event changed; preserved: '+$name)}
  $event.Lines=([string]$catalog.newEvents.$name).Split([string[]]@("`n"),[StringSplitOptions]::None);$event.Changed=$true
 }
 $mem=[IO.MemoryStream]::new();$w=[IO.BinaryWriter]::new($mem)
 try{
  $w.Write([long]$next);$w.Write([int]$root.Length);$w.Write([byte[]]$root);$w.Write([int]0);$w.Write([int]7)
  foreach($row in $rows){if(-not $row.Changed){$w.Write([byte[]]$row.Original);continue};[Array]::Clear($row.Meta,9,8);$w.Write([long]$row.Id);ClickWriteString $w $row.Name;$w.Write([byte[]]$row.Meta);$w.Write([int]$row.Lines.Count);foreach($line in $row.Lines){ClickWriteString $w $line}}
  $w.Flush();[byte[]]$new=$mem.ToArray()
 }finally{$w.Dispose();$mem.Dispose()}
 $clickStage=$clickTarget+'.stage-'+[Guid]::NewGuid().ToString('N');$null=[IO.Directory]::CreateDirectory($clickStage)
 foreach($dir in Get-ChildItem -LiteralPath $clickSource -Directory -Recurse -Force){$rel=$dir.FullName.Substring($clickSource.Length+1);$null=[IO.Directory]::CreateDirectory((Join-Path $clickStage $rel))}
 foreach($file in Get-ChildItem -LiteralPath $clickSource -File -Recurse -Force){$rel=$file.FullName.Substring($clickSource.Length+1);if($rel.Replace('\','/') -like 'Scripts/Compiled/*'){continue};Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $clickStage $rel)}
 [IO.File]::WriteAllBytes((Join-Path $clickStage 'Scripts\Scripts.ssc'),$new)
 foreach($file in Get-ChildItem -LiteralPath $clickSource -File -Recurse -Force){$rel=$file.FullName.Substring($clickSource.Length+1);if($rel -eq 'Scripts\Scripts.ssc' -or $rel -eq 'Scripts/Scripts.ssc' -or $rel.Replace('\','/') -like 'Scripts/Compiled/*'){continue};if((ClickHash ([IO.File]::ReadAllBytes($file.FullName))) -ne (ClickHash ([IO.File]::ReadAllBytes((Join-Path $clickStage $rel))))){throw ('Copied file verification failed: '+$rel)}}
 if((ClickHash ([IO.File]::ReadAllBytes((Join-Path $clickStage 'Scripts\Scripts.ssc')))) -ne (ClickHash $new)){throw 'Script copy verification failed'}
 [IO.Directory]::Move($clickStage,$clickTarget);$clickStage=$null
 Write-Host ('SAVED: '+$clickTarget) -ForegroundColor Green
 Write-Host 'Open09 in Editor2.6.15, F9, save; run its Server/Client. Existing pages, variables, users and OPC settings preserved. Test plus then Cancel only.'
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{if($clickStage -and (Test-Path -LiteralPath $clickStage)){Remove-Item -LiteralPath $clickStage -Recurse -Force}}
};
