#!/usr/bin/env python3
"""Revision04 regression for the native AUTH5/FFFF rejection observed on COM18."""
import hashlib,json
from pathlib import Path
import validate_teleofis_radio_usb_probe_01 as peer

def main():
 peer.SCRIPT=peer.OUT/'Read-Teleofis-Radio-Usb-04.ps1'
 cases=['normal','native_auth_denied','native_read_denied','long_password','empty_password',
        'unknown_signal','unknown_rat','escaped_payload','noise_fragmented',
        'auth_denied','bad_crc','bad_version','bad_escape','wrong_payload_length','timeout']
 results=[]
 for case in cases:results.append(peer.run(case));print('PASS04',case,flush=True)
 report=dict(date='2026-10-29',sha256=hashlib.sha256(peer.SCRIPT.read_bytes()).hexdigest(),
  cases=results,regression='AUTH5/CMD65535/native error payload4e0001 must emit AUTH_REJECTED before mismatched-command filtering, never timeout.',
  password_length='0..32 ASCII, prompt before COM open; native ServiceFactory78 range.',
  test_transport='Actual PowerShell7.6.9/.NET/Linux PTYs with independent Python CRC/framing',
  limitations='DTR/RTS disabled only for PTYs; actual Windows/device success pending; revision04 not delivered yet.')
 (peer.OUT/'validation-revision04-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
