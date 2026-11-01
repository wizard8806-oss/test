param([string]$OutputPath)
# Windows PowerShell5.1: source text -> self-contained offline HTML.
# Does not open/modify native SCADA projects or start equipment.
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$source=Join-Path $root 'ui\operator-console'
if(-not $OutputPath){$OutputPath=Join-Path $root 'artifacts\operator-ui-preview-01\operator-preview.html'}
$target=[IO.Path]::GetFullPath($OutputPath)
$sourcePrefix=[IO.Path]::GetFullPath($source)+[IO.Path]::DirectorySeparatorChar
if([IO.Path]::GetExtension($target) -ine '.html' -or $target.StartsWith($sourcePrefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Use an HTML output outside the source directory'}
$utf8=[Text.UTF8Encoding]::new($false,$true)
function Read-Source([string]$Name){return [IO.File]::ReadAllText((Join-Path $source $Name),$utf8).Replace("`r`n","`n")}
$catalog=Read-Source 'catalog.json'
$null=$catalog | ConvertFrom-Json
$catalog=$catalog.Replace('<','\u003c').Replace([string][char]0x2028,'\u2028').Replace([string][char]0x2029,'\u2029')
$html=Read-Source 'index.template.html'
$slots=@{
 '/*__STYLES__*/'=(Read-Source 'styles.css')
 '__CATALOG_JSON__'=$catalog
 '/*__MODEL__*/'=(Read-Source 'model.js')
 '/*__APP__*/'=(Read-Source 'app.js')
}
foreach($key in $slots.Keys){
 if(([regex]::Matches($html,[regex]::Escape($key))).Count -ne 1){throw 'Missing/duplicate template slot'}
 $html=$html.Replace($key,[string]$slots[$key])
}
$null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
[IO.File]::WriteAllText($target,$html,$utf8)
Write-Host ('BUILT: '+$target)
