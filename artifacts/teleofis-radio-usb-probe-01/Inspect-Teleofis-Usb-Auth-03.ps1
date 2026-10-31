& {
$ErrorActionPreference='Stop'
if(-not ('TeleofisRadioProbe01' -as [type])){
    Write-Host 'ERROR: Use the same PowerShell window as the first USB test.' -ForegroundColor Red
    return
}
$diagSerial=$null;$diagKey=$null;$diagPacket=$null
try{
    $diagSecure=Read-Host 'TELEOFIS settings password (4 characters)' -AsSecureString
    $diagPtr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($diagSecure)
    try{
        $diagText=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($diagPtr)
        if($diagText -cnotmatch '^[\x20-\x7e]{4}$'){throw 'Password must contain 4 ASCII characters'}
        $diagKey=[Text.Encoding]::ASCII.GetBytes($diagText)
    }finally{
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($diagPtr)
        $diagText=$null;$diagSecure.Dispose()
    }
    [byte[]]$diagPacket=[TeleofisRadioProbe01]::Frame(4,78,$diagKey)
    [Array]::Clear($diagKey,0,$diagKey.Length)
    $diagSerial=[IO.Ports.SerialPort]::new('COM18',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
    $diagSerial.Handshake=[IO.Ports.Handshake]::None
    $diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true
    $diagSerial.ReadTimeout=100;$diagSerial.WriteTimeout=1000
    $diagSerial.Open()
    Start-Sleep -Milliseconds 200
    $diagSerial.Write($diagPacket,0,$diagPacket.Length)
    Write-Host ('TX_BYTES='+$diagPacket.Length)
    [Array]::Clear($diagPacket,0,$diagPacket.Length)
    $diagRaw=[Collections.Generic.List[byte]]::new()
    $diagWatch=[Diagnostics.Stopwatch]::StartNew()
    while($diagWatch.ElapsedMilliseconds -lt 4000 -and $diagRaw.Count -lt 4096){
        $count=[Math]::Min($diagSerial.BytesToRead,4096-$diagRaw.Count)
        if($count -gt 0){
            $buffer=[byte[]]::new($count)
            $got=$diagSerial.Read($buffer,0,$buffer.Length)
            for($j=0;$j -lt $got;$j++){$diagRaw.Add($buffer[$j])}
        }else{Start-Sleep -Milliseconds 10}
    }
    Write-Host ('RX_BYTES='+$diagRaw.Count)
    $body=[Collections.Generic.List[byte]]::new()
    $inside=$false;$escaped=$false;$frames=0
    foreach($rawByte in $diagRaw){
        $x=[int]$rawByte
        if($x -eq 192){$body.Clear();$inside=$true;$escaped=$false;continue}
        if(-not $inside){continue}
        if($escaped){
            if($x -eq 193){$x=192}elseif($x -eq 195){$x=194}elseif($x -ne 196){$inside=$false;continue}
            $escaped=$false
        }elseif($x -eq 196){$escaped=$true;continue
        }elseif($x -eq 194){
            $inside=$false;$frames++
            [byte[]]$a=$body.ToArray();$n=$a.Length
            if($n -lt 6){Write-Host ('FRAME SHORT; BYTES='+$n);continue}
            $v=[int]$a[0];$action=[int]$a[1]
            if($v -eq 1 -and $n -ge 7){$cmd=[int]$a[2]+256*[int]$a[3];$size=[int]$a[4];$head=5
            }elseif($v -eq 0){$cmd=[int]$a[2];$size=[int]$a[3];$head=4
            }else{Write-Host ('FRAME UNKNOWN VERSION='+$v+'; BYTES='+$n);continue}
            $crc=if([TeleofisRadioProbe01]::Crc($a,$n-2) -eq ([int]$a[$n-2]+256*[int]$a[$n-1])){'OK'}else{'BAD'}
            $length=if($n -eq $head+$size+2){'OK'}else{'BAD'}
            Write-Host ('FRAME V='+$v+' ACTION='+$action+' CMD='+$cmd+' DATA_LEN='+$size+' CRC='+$crc+' LENGTH='+$length)
            continue
        }
        $body.Add([byte]$x)
    }
    Write-Host ('COMPLETE_FRAMES='+$frames)
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($null -ne $diagKey){[Array]::Clear($diagKey,0,$diagKey.Length)}
    if($null -ne $diagPacket){[Array]::Clear($diagPacket,0,$diagPacket.Length)}
    if($null -ne $diagSerial){if($diagSerial.IsOpen){$diagSerial.Close()};$diagSerial.Dispose()}
}
};
