& {
$ErrorActionPreference='Stop'
if(-not ('TeleofisRadioProbe01' -as [type])){
    Write-Host 'ERROR: Use the same PowerShell window as the previous USB test.' -ForegroundColor Red
    return
}
$diagSerial=$null
$diagKey=$null
try{
    $diagSerial=[IO.Ports.SerialPort]::new('COM18',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
    $diagSerial.Handshake=[IO.Ports.Handshake]::None
    $diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true
    $diagSerial.ReadTimeout=100;$diagSerial.WriteTimeout=1000
    $diagSerial.Open()
    $diagSecure=Read-Host 'Password of TELEOFIS settings (4 ASCII characters; not Gateway group password)' -AsSecureString
    $diagPtr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($diagSecure)
    try{
        $diagText=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($diagPtr)
        if($diagText -cnotmatch '^[\x20-\x7e]{4}$'){throw 'Settings password must contain 4 ASCII characters'}
        $diagKey=[Text.Encoding]::ASCII.GetBytes($diagText)
    }finally{
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($diagPtr)
        $diagText=$null;$diagSecure.Dispose()
    }
    $diagSerial.DiscardInBuffer()
    $diagTx=[Action[byte[]]]{param([byte[]]$packet) $diagSerial.Write($packet,0,$packet.Length)}
    $diagRx=[Func[int]]{try{return $diagSerial.ReadByte()}catch [TimeoutException]{return -1}}
    $null=[TeleofisRadioProbe01]::Ask($diagTx,$diagRx,78,4,$diagKey,5)
    [Array]::Clear($diagKey,0,$diagKey.Length)
    [byte[]]$diagSignal=[TeleofisRadioProbe01]::Ask($diagTx,$diagRx,123,0,[byte[]]@(),2)
    [byte[]]$diagSupply=[TeleofisRadioProbe01]::Ask($diagTx,$diagRx,131,0,[byte[]]@(),2)
    [byte[]]$diagRat=[TeleofisRadioProbe01]::Ask($diagTx,$diagRx,148,0,[byte[]]@(),2)
    if($diagSignal.Length -ne 1 -or $diagSupply.Length -ne 4 -or $diagRat.Length -ne 1){throw 'Unexpected radio-data length'}
    $diagSignalNote=if($diagSignal[0] -eq 99){' (unknown)'}elseif($diagSignal[0] -le 32){''}else{' (unrecognised code)'}
    $diagRatName=if($diagRat[0] -le 2){@('2G','3G','4G')[$diagRat[0]]}else{'unknown'}
    $diagMv=[BitConverter]::ToUInt32($diagSupply,0)
    Write-Host ('SIGNAL_RAW='+$diagSignal[0]+$diagSignalNote) -ForegroundColor Green
    Write-Host ('NETWORK='+$diagRatName+'; CODE='+$diagRat[0])
    Write-Host ('SUPPLY_MV='+$diagMv+'; VOLTS='+($diagMv/1000.0))
    Write-Host ('CHECKED_UTC='+[DateTime]::UtcNow.ToString('o'))
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($null -ne $diagKey){[Array]::Clear($diagKey,0,$diagKey.Length)}
    if($null -ne $diagSerial){
        if($diagSerial.IsOpen){$diagSerial.Close()}
        $diagSerial.Dispose()
    }
}
};
