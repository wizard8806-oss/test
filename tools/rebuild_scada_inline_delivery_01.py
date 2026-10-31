#!/usr/bin/env python3
"""Rebuild the small, self-contained delivery capsule from the returned seed.

The object format was corrected on 2026-10-29 using the official 2.6.15
Editor's load routines. Native GUI opening/F9 and layout acceptance are pending.
"""
from _runtime import SCADA_SEED
import base64
import hashlib
import io
import json
import shutil
import struct
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = SCADA_SEED
OUT = ROOT / 'artifacts/simple-scada-diagnostics-01'

def sha(data): return hashlib.sha256(data).hexdigest()
def num(n): return struct.pack('<I', n)
def ansi(s):
    b=s.encode('utf8');return num(len(b))+b
def wide(s):
    b=s.encode('utf-16le');return num(len(b)//2)+b

def main():
    original=(SOURCE/'Pages.spg').read_bytes()
    assert len(original)==579 and struct.unpack_from('<3I',original)==(1,0,1)
    assert struct.unpack_from('<4H',(SOURCE/'Project.spr').read_bytes(),8)==(2,6,15,0)
    assert (SOURCE/'Scripts/Scripts.ssc').read_bytes()==num(0)+num(0)+ansi('..\\')+num(0)+num(0)
    assert original[193:197]==num(2)
    prefix=original[12:193]
    fields=original[197:]
    assert fields[6:12]==b'Field1' and fields[197:203]==b'Field2'
    # Source Field1: two-byte class, UTF8 name, 141-byte shared control header.
    seed=fields[12:153]
    assert len(seed)==141 and struct.unpack_from('<I',seed,107)[0]==9164
    items=[]
    def text(page,name,caption,rect,scale=1):
        common=bytearray(seed)
        struct.pack_into('<I',common,4,0)
        struct.pack_into('<4f',common,8,*rect)
        common[24]=255;common[29:31]=b'\x01\x01';common[31]=4
        struct.pack_into('<f',common,32,scale);struct.pack_into('<f',common,36,0)
        struct.pack_into('<I',common,40,0xFFFFFF);common[44]=255
        struct.pack_into('<I',common,45,0x646464)
        layer=sum(x['page']==page for x in items)+(2 if page==0 else 0)
        # 49..52 are the empty hint's length, 53 is a flag, 54..57 is Z order.
        # The rejected delivery wrote Z order at 51, corrupting that length.
        struct.pack_into('<I',common,54,layer)
        uid=62100+4*len(items);struct.pack_into('<I',common,107,uid)
        # Variable identifiers are Int64; an unbound label must have all 8 FFs.
        struct.pack_into('<q',common,111,-1)
        body=struct.pack('<H',4)+ansi(name)+common+wide(caption)+bytes.fromhex('000000ffffff00ff06')
        items.append(dict(page=page,name=name,uid=uid,rect=rect))
        return body
    main_texts=[
        text(0,'MainDiagStatus','Ожидание достоверных данных от станции',(112,48,1200,52),1.35),
        text(0,'MainDiagDetail','Откройте вкладку «Диагностика» для проверки связи.',(112,110,1200,70),.85),
        text(0,'MainMapLabel','Версия карты ПЛК · ожидается 31',(392,420,352,52),.85),
        text(0,'MainCounterLabel','Счётчик отправок CL50S',(816,420,352,52),.85),
        text(0,'MainMapUnknown','Нет данных',(392,208,352,192),1.4),
        text(0,'MainCounterUnknown','Нет данных',(816,208,352,192),1.4),
    ]
    diagnostic=[
        text(1,'DiagTitle','ДИАГНОСТИКА СТАНЦИИ',(32,24,1376,54),1.4),
        text(1,'DiagStatus','Ожидание достоверных данных от станции',(32,94,1376,52),1.15),
        text(1,'DiagDetail','Требуется первое изменение счётчика после запуска.',(32,156,1376,80),.85),
        text(1,'DiagOPC','MasterOPC: качество данных пока не получено',(32,254,1376,46),.9),
        text(1,'DiagRoute','Общий маршрут до ПЛК: нет подтверждения обновления',(32,310,1376,46),.9),
        text(1,'DiagAge','Нет текущего подтверждения обновления',(32,366,1376,76),.85),
        text(1,'DiagRadioTitle','TELEOFIS · независимая диагностика модема',(32,466,1376,42)),
        text(1,'DiagRadio','Уровень сигнала: нет данных   |   Сеть: нет данных   |   Питание: нет данных',(32,518,1376,42),.85),
        text(1,'DiagRadioNote','Автоматический служебный опрос модема ещё не подключён.',(32,570,1376,42),.8),
        text(1,'DiagChecksTitle','При потере данных проверить по порядку:',(32,632,1376,42),.95),
        text(1,'DiagChecks','1. MasterOPC и Gateway на ПК.  2. Подключение ПК к интернету.\r\n3. Питание и подключение TELEOFIS.  4. Питание ПЛК, RUN и кабель RS485.',(32,684,1376,84),.8),
        text(1,'DiagScope','ПЧ, датчики и аварии станции к этой странице ещё не подключены.\r\nСчётчик CL50S не заменяет независимый контроль выполнения программы ПЛК.',(32,786,1376,84),.75),
    ]
    second=bytearray(prefix)
    # Root's next-page counter and each page ID are Int64, independent of UID.
    assert struct.unpack_from('<q',second,33)[0]==0
    struct.pack_into('<q',second,33,1)
    second=bytes(second)
    for before,after in [(ansi('Page1'),ansi('PageDiagnostics')),
                         (wide('Страница 1'),wide('Диагностика')),
                         (ansi('Subpage1'),ansi('SubpageDiagnostics')),
                         (wide('Подстраница 1'),wide('Диагностика')),
                         (num(9156),num(62000)),(num(9160),num(62004))]:
        assert second.count(before)==1;second=second.replace(before,after,1)
    pages=num(2)+num(0)+num(2)+prefix+num(8)+fields+b''.join(main_texts)
    pages+=second+num(12)+b''.join(diagnostic)
    assert pages[197:579]==original[197:]
    assert len(set(x['name'] for x in items))==18
    core=(OUT/'scripts/StationDiagnostics.txt').read_text()
    timer=(OUT/'scripts/StationDiagnosticsTimer.txt').read_text()
    g=bytearray.fromhex('0a1000000000010000cd540f0000000000')
    t=bytearray.fromhex('0105c00500000a00017d01feff00000000')
    g[2:6]=num(62008);t[2:6]=num(62012);t[6:8]=struct.pack('<H',1);t[8]=1
    g[9:17]=bytes(8);t[9:17]=bytes(8)
    def script(uid,name,meta,source):
        lines=source.splitlines()
        return num(uid)+num(0)+wide(name)+meta+num(len(lines))+b''.join(wide(l) for l in lines)
    ssc=num(2)+num(0)+ansi('..\\')+num(0)+num(2)
    ssc+=script(0,'StationDiagnostics',g,core)+script(1,'StationDiagnosticsTimer',t,timer)
    (OUT/'Pages.spg').write_bytes(pages);(OUT/'Scripts.ssc').write_bytes(ssc)
    patch={'Pages.spg':pages,'Scripts/Scripts.ssc':ssc}
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,body in patch.items():
            item=zipfile.ZipInfo(name,(2026,10,29,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(item,body)
    capsule=archive.getvalue();(OUT/'capsule.zip').write_bytes(capsule)
    template=(ROOT/'tools/scada_inline_template.ps1').read_text()
    encoded='\n'.join(textwrap.wrap(base64.b64encode(capsule).decode(),120))
    code=template.replace('__CAPSULE__',encoded).replace('__CAPSULE_SHA__',sha(capsule))
    names=['Pages.spg','Scripts/Scripts.ssc','Servers.ssr','Variables.svr']
    def table(mapping):return '\n'.join("        '"+k+"'='"+sha(v)+"'" for k,v in mapping.items())
    code=code.replace('__SOURCE_HASHES__',table({n:(SOURCE/n).read_bytes() for n in names}))
    code=code.replace('__OUTPUT_HASHES__',table(patch))
    target=OUT/'Save-Codex-Diag-01.ps1';target.write_text(code)
    report=dict(date='2026-10-29',input_sediment_id='file_00000000db30820bac3b9d16f2546759',
        input_archive_sha256='4b197189f43b18535d899801922c5c8501009298fefe83f493b754860888a39b',
        target='Simple-Scada2.6.15.0 with existing fullkey',files_only=list(patch),
        script_bytes=target.stat().st_size,capsule_bytes=len(capsule),capsule_sha256=sha(capsule),
        original_fields_byte_exact=True,new_text_objects=items,native_F9_passed=False,
        actual_radio_collection_implemented=False,download_UI_issue_fixed=False,
        previous_delivery_rejected_by_native_editor=True,
        repaired=['Text hint length/Z-order offset','64-bit unbound variable ID',
                 'unique page IDs and next-page counter'])
    (OUT/'delivery-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Inline packet ready:',len(code),'characters;',len(capsule),'capsule bytes')

if __name__=='__main__':main()
