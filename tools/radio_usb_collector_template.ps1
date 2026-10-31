$diagSerial=$null;$diagSecure=$null;$diagLock=$null;$diagOwn=$false
$diagFatal=0;$diagPublish=@{Seq=[long]0}
$diagDir='C:\ProgramData\Automatika\Station50008'
$diagFile=Join-Path $diagDir 'radio.txt'
$diagStop=Join-Path $diagDir 'radio.stop'
$diagRun=[Guid]::NewGuid().ToString('N')
$diagTemp=$diagFile+'.'+$diagRun+'.tmp'
$diagEpoch=[DateTime]::new(1970,1,1,0,0,0,[DateTimeKind]::Utc)
function Get-RadioEpoch {return [long][Math]::Floor(([DateTime]::UtcNow-$diagEpoch).TotalSeconds)}
function Publish-Radio([int]$state,[long]$sample,[long]$signal,[long]$rat,[long]$mv){
    $diagPublish.Seq++
    [string[]]$rows=@('ARADIO1','USB',$diagRun,[string]$diagPublish.Seq,[string](Get-RadioEpoch),[string]$sample,[string]$state,[string]$signal,[string]$rat,[string]$mv)
    [IO.File]::WriteAllText($diagTemp,([string]::Join("`n",$rows)+"`n"),[Text.UTF8Encoding]::new($false))
    for($attempt=0;$attempt -lt 5;$attempt++){
        try{
            if([IO.File]::Exists($diagFile)){[IO.File]::Replace($diagTemp,$diagFile,[NullString]::Value)}
            else{[IO.File]::Move($diagTemp,$diagFile)}
            return
        }catch{
            if($attempt -eq 4){throw}
            Start-Sleep -Milliseconds 25
        }
    }
}
try{
    $null=[IO.Directory]::CreateDirectory($diagDir)
    try{$diagLock=[IO.File]::Open((Join-Path $diagDir 'collector.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
    catch{throw 'Radio collector already running, or its directory is unavailable'}
    $diagOwn=$true
    if([IO.File]::Exists($diagStop)){[IO.File]::Delete($diagStop)}
    $diagSecure=Read-Host 'TELEOFIS modem settings password (not Gateway group password)' -AsSecureString
    Write-Host ('RADIO COLLECTOR: USB COM18, interval 5 s. Output: '+$diagFile)
    Write-Host 'Keep this window open. Stop with Ctrl+C or radio.stop. No modem/PLC settings are written.'
    $diagAuth=[Diagnostics.Stopwatch]::new()
    while(-not [IO.File]::Exists($diagStop)){
        $state=0;$signal=[long]-1;$rat=[long]-1;$mv=[long]-1;$sample=[long]0
        try{
            if($null -eq $diagSerial){
                $diagSerial=[IO.Ports.SerialPort]::new('COM18',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
                $diagSerial.Handshake=[IO.Ports.Handshake]::None
                $diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true
                $diagSerial.ReadTimeout=100;$diagSerial.WriteTimeout=1000
                $diagSerial.Open();$diagAuth.Reset()
            }
            $diagTx=[Action[byte[]]]{param([byte[]]$packet) $diagSerial.Write($packet,0,$packet.Length)}
            $diagRx=[Func[int]]{try{return $diagSerial.ReadByte()}catch [TimeoutException]{return -1}}
            if(-not $diagAuth.IsRunning -or $diagAuth.ElapsedMilliseconds -gt 420000){
                $key=$null
                $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($diagSecure)
                try{
                    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
                    if($plain -cnotmatch '^[\x20-\x7e]{0,32}$'){throw 'AUTH_REJECTED: settings password must contain 0 to 32 ASCII characters'}
                    [byte[]]$key=[Text.Encoding]::ASCII.GetBytes($plain)
                    $null=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,78,4,$key,5)
                    $diagAuth.Restart()
                }finally{
                    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
                    $plain=$null
                    if($null -ne $key){[Array]::Clear($key,0,$key.Length)}
                }
            }
            [byte[]]$a=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,123,0,[byte[]]@(),2)
            [byte[]]$b=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,131,0,[byte[]]@(),2)
            [byte[]]$c=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,148,0,[byte[]]@(),2)
            if($a.Length -ne 1 -or $b.Length -ne 4 -or $c.Length -ne 1){throw 'Bad radio packet length'}
            $signal=[long]$a[0];$rat=[long]$c[0];$mv=[long][BitConverter]::ToUInt32($b,0)
            if($signal -gt 32 -and $signal -ne 99){throw 'Bad radio packet signal'}
            $sample=Get-RadioEpoch
        }catch{
            $message=$_.Exception.Message
            $signal=[long]-1;$rat=[long]-1;$mv=[long]-1;$sample=[long]0
            if($message -match 'AUTH_REJECTED:'){$state=1;$diagFatal=1}
            elseif($message -match 'No matching reply'){$state=2}
            elseif($message -match 'CRC|packet|escape'){$state=3}
            elseif($message -match 'DEVICE_ERROR:.*CODE=0'){$state=1;$diagAuth.Reset()}
            else{$state=4}
            if($state -eq 4 -and $null -ne $diagSerial){
                try{if($diagSerial.IsOpen){$diagSerial.Close()}}catch{}
                $diagSerial.Dispose();$diagSerial=$null;$diagAuth.Reset()
            }
        }
        Publish-Radio $state $sample $signal $rat $mv
        if($diagFatal -ne 0){break}
        $delay=[Diagnostics.Stopwatch]::StartNew()
        while($delay.ElapsedMilliseconds -lt 5000 -and -not [IO.File]::Exists($diagStop)){Start-Sleep -Milliseconds 100}
    }
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($diagOwn -and $diagPublish.Seq -gt 0 -and $diagFatal -eq 0){try{Publish-Radio 5 0 -1 -1 -1}catch{}}
    if($null -ne $diagSerial){try{if($diagSerial.IsOpen){$diagSerial.Close()}}catch{};$diagSerial.Dispose()}
    if($null -ne $diagSecure){$diagSecure.Dispose()}
    if([IO.File]::Exists($diagTemp)){[IO.File]::Delete($diagTemp)}
    if($null -ne $diagLock){$diagLock.Dispose()}
}
};
