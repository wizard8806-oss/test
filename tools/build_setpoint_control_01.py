#!/usr/bin/env python3
"""Build operator-triggered setpoint controls; never connect to field equipment."""
import base64
import gzip
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path

from build_radio_display_01 import bootstrap
from build_process_display_01 import build_pages

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/station-setpoint-display-01/scripts/StationDiagnostics.txt'
OUT = ROOT / 'artifacts/station-setpoint-control-01'
EVENTS = [
    ('ProcessSpMinus', 'StationSpAdjust(-10);'),
    ('ProcessSpPlus', 'StationSpAdjust(10);'),
    ('ProcessSpApply', 'StationSpApply;'),
    ('ProcessSpCancel', 'StationSpCancel;'),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module():
    text = BASE.read_text()

    def once(old, new):
        nonlocal text
        assert text.count(old) == 1, old[:60]
        text = text.replace(old, new)

    once('interface\nprocedure StationProcessUpdate;', '''interface
procedure StationSpAdjust(Delta: Integer);
procedure StationSpApply;
procedure StationSpCancel;
procedure StationProcessUpdate;''')
    once('var\n  SpFeedbackHasSample:', '''var
  SpDraftActive, SpEchoSeen, SpControlLogLost: Boolean;
  SpDraftClient, SpDraftUserLabel, SpControlText: string;
  SpDraftUser, SpDraftBase, SpDraftRaw: Int64;
  SpControlTarget, SpControlCounter, SpEchoCounter, SpControlSerial: Int64;
  SpDraftTick, SpControlTick: Double;
  SpControlStage: Integer;
  SpFeedbackHasSample:''')
    once('Now * 86400.0', 'SpControlSeconds')
    once('procedure StationProcessUpdate;\nvar\n', (OUT/'control-core.txt').read_text().rstrip() + '\n\nprocedure StationProcessUpdate;\nvar\n')
    once("  ProcessMainScope.Text := 'Мониторинг: изменение уставки из SCADA пока недоступно.';", '')
    once("  ProcessMap.Text := ProcessMap.Text + ' | Режим: ' + ModeText;", "  ProcessMap.Text := ProcessMap.Text + ' | Режим: ' + ModeText;\n  SpControlUpdate(SpState, SpCaption, SpNote);")
    return text


def page_packet():
    before, objects = build_pages()
    data = bytearray(before)

    def locate(name):
        raw = name.encode()
        marker = struct.pack('<HI', 4, len(raw)) + raw
        assert before.count(marker) == 1
        start = before.index(marker)
        body = start + len(marker)
        assert before[body+49:body+54] == bytes(5)
        size = struct.unpack_from('<I', before, body+141)[0]
        end = body+141+4+size*2+9
        return start, body, end

    first, _, _ = locate('ProcessTitle')
    count_offset = first-4
    assert struct.unpack_from('<I', data, count_offset)[0] == 20
    _, footer, page_end = locate('ProcessMainScope')
    struct.pack_into('<4f', data, footer+8, 32, 850, 1376, 34)
    struct.pack_into('<f', data, footer+32, .66)
    _, seed_pos, _ = locate('ProcessSetpointLabel')
    seed = bytes(data[seed_pos:seed_pos+141])
    layouts = [
        ('ProcessSpTitle', 'НОВАЯ УСТАВКА, бар', (32,798,280,44), .8, -1),
        ('ProcessSpMinus', '-', (330,798,64,44), 1.3, 3),
        ('ProcessSpDraft', '--', (408,798,180,44), 1.4, -1),
        ('ProcessSpPlus', '+', (602,798,64,44), 1.3, 4),
        ('ProcessSpApply', 'Применить', (684,798,300,44), .95, 5),
        ('ProcessSpCancel', 'Отмена', (1002,798,220,44), .95, 6),
    ]
    added = []
    for index, (name, caption, rect, scale, event_id) in enumerate(layouts):
        common = bytearray(seed)
        struct.pack_into('<4f', common, 8, *rect)
        struct.pack_into('<f', common, 32, scale)
        struct.pack_into('<I', common, 54, 20+index)
        uid = 65000 + 4*index
        struct.pack_into('<I', common, 107, uid)
        struct.pack_into('<q', common, 111, -1)
        # Common TM_Object OnClick link, verified against official2.6.15 Demo.
        struct.pack_into('<q', common, 75, event_id)
        if event_id >= 0:
            struct.pack_into('<I', common, 45, 0x266996)
        raw_name, raw_caption = name.encode(), caption.encode('utf-16le')
        record = struct.pack('<HI',4,len(raw_name)) + raw_name + common
        record += struct.pack('<I',len(raw_caption)//2) + raw_caption + bytes.fromhex('000000ffffff00ff06')
        added.append(record)
        objects.append(dict(page=0,name=name,uid=uid,rect=rect,scale=scale,caption=caption,onClickScriptID=event_id))
    struct.pack_into('<I',data,count_offset,26)
    after = bytes(data[:page_end]) + b''.join(added) + bytes(data[page_end:])
    return before, after, objects


def main():
    (OUT/'scripts').mkdir(parents=True,exist_ok=True)
    code = module()
    assert len(code.encode()) < 65536
    (OUT/'scripts/StationDiagnostics.txt').write_text(code)
    for name, call in EVENTS:
        (OUT/'scripts'/(name+'_OnClick.txt')).write_text('begin\n  '+call+'\nend.\n')
    old_pages, pages, objects = page_packet()
    (OUT/'Pages.spg').write_bytes(pages)
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for name, body in [('Pages.spg',pages),('Module.txt',code.encode())] + [
            (name+'_OnClick.txt',(OUT/'scripts'/(name+'_OnClick.txt')).read_bytes()) for name,_ in EVENTS]:
            item=zipfile.ZipInfo(name,(2026,10,31,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;z.writestr(item,body)
    raw_bundle=bundle.getvalue();(OUT/'bundle.zip').write_bytes(raw_bundle)
    template=(ROOT/'tools/setpoint_control_install_template.ps1').read_text()
    installer=template.replace('__BUNDLE__',base64.b64encode(raw_bundle).decode()).replace('__BUNDLE_SHA__',sha(raw_bundle))
    installer=installer.replace('__OLD_CORE_SHA__',sha(BASE.read_text().strip().encode())).replace('__OLD_PAGES_SHA__',sha(old_pages)).replace('__PAGES_SHA__',sha(pages)).replace('__MODULE_SHA__',sha(code.encode()))
    (OUT/'Install-Setpoint-Control-01.ps1').write_text(installer)
    paste=bootstrap(installer).replace('$radio','$control');(OUT/'Paste-Setpoint-Control-01.ps1').write_text(paste)
    profile=[dict(name='PressureSP_Command',pduAddress=2100,region='HOLDING_REGISTERS',deviceType='uint16',serverType='uint32',access='ReadWrite',scalingEnabled=False,SCADADecimalOffset=0)]
    (OUT/'masteropc-command-tag.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    report=dict(date='2026-10-31',sourceProject='codex_diag_07',targetProject='codex_diag_08',
                oldCoreSHA256=sha(BASE.read_text().strip().encode()),moduleSHA256=sha(code.encode()),
                sourcePagesSHA256=sha(old_pages),pagesSHA256=sha(pages),objects=objects,
                installerSHA256=sha(installer.encode()),inlineCharacters=len(paste),
                commandTag=profile[0],nativeNewF9Observed=False,nativeOperatorWriteObserved=False,
                sourcePLCOrHMIChanged=False,automaticWriteOnStartupOrReconnect=False,
                scalarValueContract='Observed PLC value and leading-drive cache, not an exclusive PLC request-ID acknowledgment',
                authorization='Native client action with GetUserID>=0 and nonempty GetClientName; per-client/user draft ownership; project-wide production role configuration not independently verified')
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Built setpoint control copy:',len(paste),'inline characters;',len(code.encode()),'module bytes')


if __name__=='__main__':main()
