#!/usr/bin/env python3
import base64,gzip,hashlib,io,json,textwrap,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/teleofis-radio-display-01'
def sha(b):return hashlib.sha256(b).hexdigest()
def bootstrap(code):
 raw=code.encode();b=gzip.compress(raw,mtime=0)
 data='\n'.join(textwrap.wrap(base64.b64encode(b).decode(),120))
 return """& {
$ErrorActionPreference='Stop'
$radioPacked=@'
"""+data+"""
'@
try{
 $radioInput=[IO.MemoryStream]::new([Convert]::FromBase64String($radioPacked))
 $radioGzip=[IO.Compression.GZipStream]::new($radioInput,[IO.Compression.CompressionMode]::Decompress)
 $radioOutput=[IO.MemoryStream]::new()
 try{$radioGzip.CopyTo($radioOutput);[byte[]]$radioCode=$radioOutput.ToArray()}
 finally{$radioGzip.Dispose();$radioInput.Dispose();$radioOutput.Dispose()}
 $radioSha=[Security.Cryptography.SHA256]::Create()
 try{$radioHash=([BitConverter]::ToString($radioSha.ComputeHash($radioCode))).Replace('-','').ToLowerInvariant()}
 finally{$radioSha.Dispose()}
 if($radioHash -ne '"""+sha(raw)+"""'){throw 'Transfer checksum mismatch. Copy the complete block again.'}
 & ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($radioCode)))
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
};
"""

def main():
 prefix=(ROOT/'artifacts/teleofis-radio-usb-probe-01/Read-Teleofis-Radio-Usb-04.ps1').read_text().split('$diagSerial=$null')[0]
 collector=prefix+(ROOT/'tools/radio_usb_collector_template.ps1').read_text()
 (OUT/'Run-Radio-Usb-Collector-01.ps1').write_text(collector)
 items={'RadioModule.txt':(OUT/'scripts/StationRadioDiagnostics.txt').read_bytes(),'RadioCollector.ps1':collector.encode()}
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
  for name,body in items.items():
   info=zipfile.ZipInfo(name,(2026,10,29,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,body)
 packed=buf.getvalue();(OUT/'bundle.zip').write_bytes(packed)
 code=(ROOT/'tools/radio_display_install_template.ps1').read_text()
 code=code.replace('__BUNDLE__','\n'.join(textwrap.wrap(base64.b64encode(packed).decode(),120))).replace('__BUNDLE_SHA__',sha(packed))
 for key,name in [('CORE','StationDiagnostics'),('TIMER','StationDiagnosticsTimer')]:
  raw=(ROOT/'artifacts/simple-scada-diagnostics-01/scripts'/(name+'.txt')).read_text().strip().encode()
  code=code.replace('__'+key+'_SHA__',sha(raw))
 (OUT/'Install-Radio-Display-01.ps1').write_text(code)
 delivery=bootstrap(code);(OUT/'Paste-Radio-Display-01.ps1').write_text(delivery)
 report=dict(date='2026-10-29',radio_read_verified_on_actual_modem=True,
  confirmed_sample=dict(signal=26,RAT='4G',supply_mV=11794),
  transport='USB COM18 bench source; not remote service collection',
  polling_ms=5000,display_sample_age_limit_s=15,publisher_age_limit_s=20,
  source_project='codex_diag_01, two original script sources checked; source preserved',
  target_project='Desktop/codex_diag_02',changes=['Add global Radio module','Call it from1s timer','Write collector under Tools'],
  data_file='C:\\ProgramData\\Automatika\\Station50008\\radio.txt',
  protocol='Only AUTH78 and READ123/131/148; no Main50008 connection, PLC/config writes or new external OPC tags',
  secrets='Prompt once into SecureString, held in memory, no stored password',
  bundle_sha256=sha(packed),installer_sha256=sha(code.encode()),
  collector_sha256=sha(collector.encode()),inline_characters=len(delivery),
  native_new_F9_passed=None,native_radio_UI_passed=False,actual_continuous_USB_collector_passed=False)
 observation=OUT/'native-observation-2026-10-29.json'
 if observation.exists():
  native=json.loads(observation.read_text())
  report.update(native_radio_UI_passed=native['native_radio_UI_passed'],
   actual_continuous_USB_collector_passed=native['actual_continuous_USB_collector_passed'],
   native_radio_module_execution_observed=native['native_radio_module_execution_observed'],
   native_stale_radio_test_passed=native['actual_stale_radio_test_passed'],
   native_F9_note='Explicit F9 command not reported; successful execution of the corrected module is observed on the native client.',
   native_observation=observation.name)
 (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('Built radio display:',len(delivery),'inline characters,',len(packed),'bundle bytes')

if __name__=='__main__':main()
