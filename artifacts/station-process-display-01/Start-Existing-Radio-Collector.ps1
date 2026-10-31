& {
 $radioRoots=@(
  [Environment]::GetFolderPath('Desktop'),
  (Join-Path $env:USERPROFILE 'Documents\Simple-Scada 2\Projects'),
  (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Simple-Scada 2\Projects')
 )
 $radioPaths=foreach($root in $radioRoots){
  foreach($project in @('codex_diag_03','codex_diag_02')){
   Join-Path $root ($project+'\Tools\Run-Radio-Usb-Collector-01.ps1')
  }
 }
 $radioPath=$radioPaths | Where-Object {Test-Path -LiteralPath $_ -PathType Leaf} | Select-Object -First 1
 if(-not $radioPath){Write-Host 'Radio collector file not found.';return}
 & ([scriptblock]::Create([IO.File]::ReadAllText($radioPath)))
}
