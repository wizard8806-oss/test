param([string]$OutPath)
# Metadata only: no clicks, foreground changes, SCADA starts or OPC activation.
$ErrorActionPreference='Stop'
$interopSource=@'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class CodexScadaUiContextV1 {
  public delegate bool EnumProc(IntPtr hwnd, IntPtr data);
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll", SetLastError=true)] public static extern bool EnumWindows(EnumProc callback, IntPtr data);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out Rect rect);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern IntPtr GetProcessWindowStation();
  [DllImport("user32.dll")] public static extern IntPtr GetThreadDesktop(uint id);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
  [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  static extern bool GetUserObjectInformation(IntPtr obj, int index, StringBuilder text, uint bytes, out uint required);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
  [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr token, int kind, out int value, int bytes, out int returned);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
  public static string ObjectName(IntPtr obj) {
    StringBuilder b=new StringBuilder(1024); uint needed;
    return obj!=IntPtr.Zero && GetUserObjectInformation(obj,2,b,2048,out needed) ? b.ToString() : null;
  }
  public static bool? Elevated(uint pid) {
    IntPtr p=OpenProcess(0x1000,false,pid), t=IntPtr.Zero;
    if(p==IntPtr.Zero) return null;
    try {
      if(!OpenProcessToken(p,8,out t)) return null;
      int value,returned;
      return GetTokenInformation(t,20,out value,4,out returned) ? (bool?)(value!=0) : null;
    } finally { if(t!=IntPtr.Zero) CloseHandle(t); CloseHandle(p); }
  }
}
'@

function Get-UiHash([string]$Text) {
 $hash=[Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() }
 finally {$hash.Dispose()}
}

function Get-UiComRegistration([string]$ProgId,[Microsoft.Win32.RegistryView]$View) {
 $root=$null;$key=$null;$class=$null;$inproc=$null;$local=$null
 $row=[ordered]@{progId=$ProgId;view=[string]$View;registered=$false;inProcessServer=$false;inProcessFileExists=$false;localServer=$false;readSucceeded=$false}
 try {
  $root=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::ClassesRoot,$View)
  $key=$root.OpenSubKey($ProgId+'\CLSID',$false)
  if($null -ne $key) {
   $clsid=[string]$key.GetValue('')
   $guid=[Guid]::Empty
   if([Guid]::TryParse($clsid,[ref]$guid)) {
    $row.registered=$true
    $class=$root.OpenSubKey('CLSID\'+$clsid,$false)
    if($null -ne $class) {
     $inproc=$class.OpenSubKey('InprocServer32',$false);$local=$class.OpenSubKey('LocalServer32',$false)
     if($null -ne $inproc) {
      $value=[string]$inproc.GetValue('')
      $row.inProcessServer=-not [string]::IsNullOrWhiteSpace($value)
      if($row.inProcessServer){$row.inProcessFileExists=[IO.File]::Exists([Environment]::ExpandEnvironmentVariables($value).Trim('"'))}
     }
     $row.localServer=$null -ne $local -and -not [string]::IsNullOrWhiteSpace([string]$local.GetValue(''))
    }
   }
  }
  $row.readSucceeded=$true
 } catch { $row.readSucceeded=$false }
 finally {foreach($item in @($local,$inproc,$class,$key,$root)){if($null -ne $item){$item.Dispose()}}}
 return [pscustomobject]$row
}

$result=[ordered]@{
 schemaVersion=1;measuredAtUTC=[DateTime]::UtcNow.ToString('o')
 platformSupported=([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT)
 status='unsupported-platform';powerShellVersion=$PSVersionTable.PSVersion.ToString()
 languageMode=[string]$ExecutionContext.SessionState.LanguageMode
 is64BitProcess=[Environment]::Is64BitProcess
 userInteractive=[Environment]::UserInteractive
 caller=$null;processes=@();windows=@();comRegistration=@()
 fullWindowTitlesExported=$false;windowActionsInvoked=0;equipmentCommands=0;opcObjectsCreated=0
}
if($result.platformSupported) {
 if(-not ('CodexScadaUiContextV1' -as [type])){Add-Type -TypeDefinition $interopSource}
 $caller=[Diagnostics.Process]::GetCurrentProcess()
 $station=[CodexScadaUiContextV1]::ObjectName([CodexScadaUiContextV1]::GetProcessWindowStation())
 $desktop=[CodexScadaUiContextV1]::ObjectName([CodexScadaUiContextV1]::GetThreadDesktop([CodexScadaUiContextV1]::GetCurrentThreadId()))
 $result.caller=[ordered]@{processId=$PID;sessionId=$caller.SessionId;elevated=[CodexScadaUiContextV1]::Elevated([uint32]$PID);windowStation=$station;desktop=$desktop;activeConsoleSessionId=[CodexScadaUiContextV1]::WTSGetActiveConsoleSessionId()}
 $processRows=[Collections.Generic.List[object]]::new();$processById=@{}
 foreach($process in @(Get-Process | Where-Object {$_.ProcessName -match '^(Server|Client|Editor|modbusopcserver|MasterOPC)$'})) {
  $session=$null;$hasMain=$null
  try{$process.Refresh();$session=$process.SessionId;$hasMain=$process.MainWindowHandle -ne [IntPtr]::Zero}catch{}
  $row=[pscustomobject]@{name=$process.ProcessName;id=$process.Id;sessionId=$session;sameSessionAsCaller=($null -ne $session -and $session -eq $caller.SessionId);elevated=[CodexScadaUiContextV1]::Elevated([uint32]$process.Id);hasMainWindow=$hasMain}
  $processRows.Add($row);$processById[[int]$process.Id]=$row
 }
 $windowRows=[Collections.Generic.List[object]]::new();$enumState=@{seen=0;errors=0}
 $foreground=[CodexScadaUiContextV1]::GetForegroundWindow()
 $callback=[CodexScadaUiContextV1+EnumProc]{param([IntPtr]$Window,[IntPtr]$Unused)
  $enumState.seen++
  try {
   [uint32]$owner=0;[void][CodexScadaUiContextV1]::GetWindowThreadProcessId($Window,[ref]$owner)
   if($processById.ContainsKey([int]$owner)) {
    $text=[Text.StringBuilder]::new(2048);$className=[Text.StringBuilder]::new(256)
    [void][CodexScadaUiContextV1]::GetWindowText($Window,$text,$text.Capacity)
    [void][CodexScadaUiContextV1]::GetClassName($Window,$className,$className.Capacity)
    $title=$text.ToString();$project=[regex]::Match($title,'\bcodex_diag_[A-Za-z0-9_-]{1,100}\b').Value
    $rect=[CodexScadaUiContextV1+Rect]::new();$hasRect=[CodexScadaUiContextV1]::GetClientRect($Window,[ref]$rect)
    $dpi=$null;try{$dpi=[CodexScadaUiContextV1]::GetDpiForWindow($Window)}catch{}
    $windowRows.Add([pscustomobject]@{processId=$owner;processName=$processById[[int]$owner].name;handle=('0x{0:X}' -f $Window.ToInt64());visible=[CodexScadaUiContextV1]::IsWindowVisible($Window);foreground=($Window -eq $foreground);className=$className.ToString();titlePresent=($title.Length -gt 0);titleSHA256=(Get-UiHash $title);projectName=$project;clientRectRead=$hasRect;clientWidth=($rect.Right-$rect.Left);clientHeight=($rect.Bottom-$rect.Top);dpi=$dpi})
   }
  } catch { $enumState.errors++ }
  return $true
 }
 $result.enumWindowsSucceeded=[CodexScadaUiContextV1]::EnumWindows($callback,[IntPtr]::Zero)
 $result.enumWindowsError=0
 if(-not $result.enumWindowsSucceeded){$result.enumWindowsError=[Runtime.InteropServices.Marshal]::GetLastWin32Error()}
 [GC]::KeepAlive($callback)
 $result.enumeratedWindowCount=$enumState.seen;$result.windowReadErrors=$enumState.errors
 $result.processes=$processRows.ToArray();$result.windows=$windowRows.ToArray()
 $registrations=[Collections.Generic.List[object]]::new()
 $views=@([Microsoft.Win32.RegistryView]::Registry32)
 if([Environment]::Is64BitOperatingSystem){$views+=@([Microsoft.Win32.RegistryView]::Registry64)}
 foreach($view in $views){foreach($name in @('OPC.Automation.1','OPC.Automation','InSAT.ModbusOPCServer.DA')){$registrations.Add((Get-UiComRegistration $name $view))}}
 $result.comRegistration=$registrations.ToArray();$result.status='measured'
}
$json=$result|ConvertTo-Json -Depth 7
if($OutPath) {
 # Never overwrite a report; output contains no arbitrary window titles or DLL paths.
 $stream=[IO.File]::Open([IO.Path]::GetFullPath($OutPath),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 $writer=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
 try{$writer.WriteLine($json)}finally{$writer.Dispose();$stream.Dispose()}
}
Write-Output $json
