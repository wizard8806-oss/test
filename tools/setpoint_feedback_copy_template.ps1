param([string]$SourcePath,[string]$OutputDirectory)
$ErrorActionPreference='Stop'
$spTemporary=$null
function SpFileHash([byte[]]$Data){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash($Data))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
try{
 if([string]::IsNullOrWhiteSpace($SourcePath)){
  Add-Type -AssemblyName System.Windows.Forms
  $spDialog=New-Object System.Windows.Forms.OpenFileDialog
  try{
   $spDialog.Title='Select the original station_MC_CM55_900G_04.pdw'
   $spDialog.Filter='WinProLadder project (*.pdw)|*.pdw'
   $spDialog.FileName='station_MC_CM55_900G_04.pdw'
   $spDialog.InitialDirectory=[Environment]::GetFolderPath('Desktop')
   $spDialog.CheckFileExists=$true
   if($spDialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){Write-Host 'Cancelled. No file created.';return}
   $SourcePath=$spDialog.FileName
  }finally{$spDialog.Dispose()}
 }
 $SourcePath=(Get-Item -LiteralPath ($SourcePath.Trim().Trim('"'))).FullName
 [byte[]]$spOriginal=[IO.File]::ReadAllBytes($SourcePath)
 if((SpFileHash $spOriginal) -ne '__SOURCE_SHA__'){throw 'The selected source differs from the uploaded _04.pdw. Source preserved; select the exact original file.'}
 $spPacked='__PATCH_GZIP__'
 $spInput=[IO.MemoryStream]::new([Convert]::FromBase64String($spPacked))
 $spGzip=[IO.Compression.GZipStream]::new($spInput,[IO.Compression.CompressionMode]::Decompress)
 $spPlain=[IO.MemoryStream]::new()
 try{$spGzip.CopyTo($spPlain);[byte[]]$spPatch=$spPlain.ToArray()}
 finally{$spGzip.Dispose();$spInput.Dispose();$spPlain.Dispose()}
 if((SpFileHash $spPatch) -ne '__PATCH_SHA__'){throw 'Patch transfer checksum mismatch. Copy the complete block again.'}
 $spPatchStream=[IO.MemoryStream]::new($spPatch)
 $spReader=[IO.BinaryReader]::new($spPatchStream)
 $spOutput=[IO.MemoryStream]::new()
 $spWriter=[IO.BinaryWriter]::new($spOutput)
 try{
  if([Text.Encoding]::ASCII.GetString($spReader.ReadBytes(9)) -ne 'FSPPATCH1'){throw 'Invalid patch format'}
  $spSourceSize=$spReader.ReadUInt32();$spTargetSize=$spReader.ReadUInt32();$spOperations=$spReader.ReadUInt32()
  if($spSourceSize -ne $spOriginal.Length -or $spTargetSize -ne __TARGET_SIZE__ -or $spOperations -ne __PATCH_COUNT__){throw 'Patch size or operation count differs'}
  [long]$spCursor=0
  for($spIndex=0;$spIndex -lt $spOperations;$spIndex++){
   [long]$spOffset=$spReader.ReadUInt32();[long]$spRemove=$spReader.ReadUInt32();[long]$spAdd=$spReader.ReadUInt32()
   if($spOffset -lt $spCursor -or $spOffset+$spRemove -gt $spOriginal.Length -or $spAdd -gt $spTargetSize){throw 'Patch range is invalid'}
   $spWriter.Write($spOriginal,[int]$spCursor,[int]($spOffset-$spCursor))
   [byte[]]$spChunk=$spReader.ReadBytes([int]$spAdd)
   if($spChunk.Length -ne $spAdd){throw 'Truncated patch'}
   $spWriter.Write($spChunk)
   $spCursor=$spOffset+$spRemove
  }
  $spWriter.Write($spOriginal,[int]$spCursor,[int]($spOriginal.Length-$spCursor));$spWriter.Flush()
  if($spPatchStream.Position -ne $spPatchStream.Length){throw 'Unexpected trailing patch data'}
  [byte[]]$spResult=$spOutput.ToArray()
 }finally{$spWriter.Dispose();$spOutput.Dispose();$spReader.Dispose();$spPatchStream.Dispose()}
 if($spResult.Length -ne $spTargetSize -or (SpFileHash $spResult) -ne '__TARGET_SHA__'){throw 'Output verification failed. No file was created.'}
 if([string]::IsNullOrWhiteSpace($OutputDirectory)){$OutputDirectory=Join-Path ([Environment]::GetFolderPath('Desktop')) 'codex_plc_sp_feedback_01'}
 $spBaseDirectory=[IO.Path]::GetFullPath($OutputDirectory)
 $spDirectory=$spBaseDirectory;$spSuffix=1
 while($true){
  $spTarget=Join-Path $spDirectory 'station_MC_CM55_900G_05.pdw'
  if([string]::Equals($spTarget,$SourcePath,[StringComparison]::OrdinalIgnoreCase)){throw 'Source and target are the same file; source preserved'}
  if(-not [IO.File]::Exists($spTarget)){break}
  if((SpFileHash ([IO.File]::ReadAllBytes($spTarget))) -eq '__TARGET_SHA__'){
   Write-Host ('SAVED: '+$spTarget) -ForegroundColor Green
   Write-Host 'The verified copy already exists. Open it in WinProLadder, F8, save, then upload the saved file.'
   return
  }
  $spSuffix++
  if($spSuffix -gt 100){throw 'Too many existing destinations; all preserved'}
  $spDirectory=$spBaseDirectory+'_'+$spSuffix
 }
 if((SpFileHash ([IO.File]::ReadAllBytes($SourcePath))) -ne '__SOURCE_SHA__'){throw 'Source changed during preparation; no output created'}
 $null=[IO.Directory]::CreateDirectory($spDirectory)
 $spTemporary=$spTarget+'.tmp-'+[Guid]::NewGuid().ToString('N')
 $spFile=[IO.File]::Open($spTemporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try{$spFile.Write($spResult,0,$spResult.Length);$spFile.Flush()}finally{$spFile.Dispose()}
 if((SpFileHash ([IO.File]::ReadAllBytes($spTemporary))) -ne '__TARGET_SHA__'){throw 'Written file verification failed'}
 [IO.File]::Move($spTemporary,$spTarget);$spTemporary=$null
 Write-Host ('SAVED: '+$spTarget) -ForegroundColor Green
 Write-Host 'Added seven feedback MOV networks. Map32 and all nine Modbus tables are preserved.'
 Write-Host 'Open the NEW _05.pdw in WinProLadder. Press F8, save, then upload the saved file. No PLC connection or download was performed.'
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
finally{if($spTemporary -and [IO.File]::Exists($spTemporary)){[IO.File]::Delete($spTemporary)}}
