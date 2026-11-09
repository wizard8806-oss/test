param([string]$FontPath = (Join-Path $PSScriptRoot '..\assets\hmi\pump-animation\PumpStationRotor.ttf'))
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $FontPath).Path
$expected = '70c76c96778838c13b384cee32578b6ef967ef0774165b02bf5173f4dd862f22'
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
    throw 'Font checksum differs.'
}
$fontDir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
New-Item -ItemType Directory -Path $fontDir -Force | Out-Null
$dest = Join-Path $fontDir 'PumpStationRotor.ttf'
if (Test-Path -LiteralPath $dest) {
    if ((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        throw 'A different existing rotor font was preserved.'
    }
} else { Copy-Item -LiteralPath $source -Destination $dest }
$key = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts'
New-Item -Path $key -Force | Out-Null
New-ItemProperty -Path $key -Name 'Pump Station Rotor (TrueType)' -Value $dest -PropertyType String -Force | Out-Null
if (-not ('PumpAnimationFont.Native' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace PumpAnimationFont {
 public static class Native {
  [DllImport("gdi32.dll", CharSet=CharSet.Unicode)] public static extern int AddFontResourceEx(string path, uint flags, IntPtr reserved);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r);
 }
}
'@
}
$loaded = [PumpAnimationFont.Native]::AddFontResourceEx($dest, 0, [IntPtr]::Zero)
if ($loaded -lt 1) { throw 'Windows did not load the rotor font.' }
$result = [IntPtr]::Zero
[void][PumpAnimationFont.Native]::SendMessageTimeout([IntPtr]0xffff, 0x001d, [IntPtr]::Zero, [IntPtr]::Zero, 2, 2000, [ref]$result)
Write-Output "Rotor font installed for current user: $dest"
