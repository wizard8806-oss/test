#!/usr/bin/env python3
"""Package the already loopback-verified Service collector for inline delivery."""
import base64, hashlib, io, json, textwrap, zipfile
from pathlib import Path
from build_radio_display_01 import bootstrap

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/teleofis-radio-service-01'

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    items={name:(OUT/name).read_bytes() for name in ['Run-Radio-Service-Collector-01.ps1','stations.json']}
    config=json.loads(items['stations.json'])
    assert config['Stations'][0]['RadioDataDirectory']==r'C:\ProgramData\Automatika\Station50008'
    assert config['Stations'][0]['GroupId']==config['Groups'][0]['Id']
    assert config['Groups'][0]['Login']==7058
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in items.items():
            info=zipfile.ZipInfo(name,(2026,10,30,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    bundle=buf.getvalue();(OUT/'delivery-bundle.zip').write_bytes(bundle)
    template=(ROOT/'tools/radio_service_install_template.ps1').read_text()
    code=template.replace('__BUNDLE__','\n'.join(textwrap.wrap(base64.b64encode(bundle).decode(),120))).replace('__BUNDLE_SHA__',sha(bundle))
    (OUT/'Install-And-Run-Radio-Service-01.ps1').write_text(code)
    paste=bootstrap(code).replace('$radio','$service')
    (OUT/'Paste-Radio-Service-01.ps1').write_text(paste)
    manifest=json.loads((OUT/'manifest.json').read_text())
    manifest.update(date='2026-10-30',status='Inline Service pilot prepared; user confirms modem disconnected from USB and configurator closed',
        collector_sha256=sha(items['Run-Radio-Service-Collector-01.ps1']),configuration_sha256=sha(items['stations.json']),
        installer_sha256=sha(code.encode()),bundle_sha256=sha(bundle),inline_characters=len(paste),
        inline_delivery='Paste-Radio-Service-01.ps1',install_directory=r'C:\ProgramData\Automatika\RadioServicePilot01',
        existing_SCADA_consumer='Unchanged; same ARADIO1 contract and Station50008/radio.txt, SOURCE=SERVICE',
        USB_required=False,Main50008_used=False,native_windows_pilot_test_pending=True)
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Service inline ready:',len(paste),'characters;',len(bundle),'bundle bytes')

if __name__=='__main__':main()
