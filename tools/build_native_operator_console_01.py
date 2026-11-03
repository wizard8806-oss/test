#!/usr/bin/env python3
"""Build SCADA11 UI assets and a file-only, source-preserving copy installer.

Only stdlib is needed. No vendor process, database, OPC or equipment is opened.
Native object layouts derive from the independently reviewed 2.6.15 fixtures.
"""
import argparse
import base64
import hashlib
import json
import math
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'source/scada-native-08/Pages.spg'
OUT = ROOT/'artifacts/operator-console-native-01'
UI = ROOT/'ui/native-console'
PAGES_SHA = '7ac3a4647f7a49b0d5c50d88dd024ab38e92ee427e59101dd929c3ebcc1e631b'
SCRIPTS_SHA = '51cc9561bb7a2b3ad3b7068db28b860d70ef9587a4586ea27a0d0eb683e7a858'
BG, PANEL, MUTED, TEXT, ACCENT = 0x0D1520, 0x152131, 0xA4B6C8, 0xEDF4FB, 0x51C8B2
# Native2.6.15 RTTI order differs from the documentation's display order.
FONT_REGULAR18 = 16
SHA = lambda b: hashlib.sha256(b).hexdigest()
U32 = lambda n: struct.pack('<I',n)
I64 = lambda n: struct.pack('<q',n)


def pressure_display_changes(name):
    # Presentation masks only. The command journal keeps its exact/raw values.
    pairs = {
        'StationDiagnostics': [
            ("Caption := 'Подтверждено ПЛК: ПЧ ' + IntToStr(Drive) + ', ' + ", 'Pressure'),
            ("SpControlText := 'Черновик: ' + ", 'SpDraftRaw'),
            ("SpControlText := 'Отправлена уставка ' + ", 'SpControlTarget'),
            ("SpControlText := 'ПЛК принял ' + ", 'SpControlTarget'),
            ("SpControlFinish(4, 'Уставка ' + ", 'SpControlTarget'),
            ("SpControlFinish(7, 'ПЛК принял ' + ", 'SpControlTarget'),
            ('ProcessSetpoint.Text := ', 'SP'),
            ('ProcessPressure.Text := ', 'PV'),
        ],
        'OperatorConsole': [('UiSetpointText[Index] := ', 'SP'), ('UiPressureText[Index] := ', 'PV')],
    }
    return [dict(old=prefix+"FormatFloat('0.00', "+value+' / 100.0)',
                 new=prefix+"FormatFloat('0.0', "+value+' / 100.0)') for prefix,value in pairs[name]]


def pressure_display_module(text, name):
    for edit in pressure_display_changes(name):
        old, new = text.count(edit['old']), text.count(edit['new'])
        if old == 1 and new == 0:
            text = text.replace(edit['old'], edit['new'], 1)
        elif old != 0 or new != 1:
            raise ValueError('Unexpected pressure display expression; source preserved')
    return text


def string(s, wide=False):
    b=s.encode('utf-16le' if wide else 'utf8')
    return U32(len(b)//2 if wide else len(b))+b


def catalog(path):
    data=json.loads(path.read_text(encoding='utf8'))
    if set(data)!={'schemaVersion','stations'} or data['schemaVersion']!=1:
        raise ValueError('Expected native catalog schema1')
    if not 1<=len(data['stations'])<=16: raise ValueError('Supported station count:1..16')
    fields={'id','name','group','itemPrefix','computer','server','pumpCount','staleSeconds','commandEnabled'}
    ids=set();bindings=set()
    for i,s in enumerate(data['stations']):
        if set(s)!=fields: raise ValueError('Unexpected catalog fields; no passwords or keys')
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,47}',s['id']) or s['id'] in ids: raise ValueError('Duplicate/invalid station ID')
        ids.add(s['id'])
        for field in ['name','group']:
            if not isinstance(s[field],str) or not s[field].strip() or len(s[field])>100 or any(ord(c)<32 for c in s[field]): raise ValueError('Invalid station label')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\.',s['itemPrefix']): raise ValueError('Expected OPC prefix including trailing dot')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',s['computer']) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.\w+)+',s['server']): raise ValueError('Expected host/ProgID without credentials')
        key=tuple(s[k].lower() for k in ['computer','server','itemPrefix'])
        if key in bindings: raise ValueError('Duplicate physical binding')
        bindings.add(key)
        if type(s['pumpCount']) is not int or not 1<=s['pumpCount']<=4 or type(s['staleSeconds']) is not int or not 5<=s['staleSeconds']<=300: raise ValueError('Invalid pump count/freshness limit')
        if type(s['commandEnabled']) is not bool: raise ValueError('Expected boolean commandEnabled')
        if i and s['commandEnabled']: raise ValueError('Additional stations are monitoring-only until their command contract is verified')
    first=data['stations'][0]
    if (first['id'],first['itemPrefix'],first['computer'],first['server'],first['pumpCount'],first['staleSeconds'],first['commandEnabled'])!=('station-001','codex.Device1.','localhost','InSAT.ModbusOPCServer.DA',4,15,True):
        raise ValueError('Keep the verified SCADA10 command station as first entry')
    return data


def parse_pages(raw):
    """Strict portable reader for the reviewed Text-only page container."""
    pos=0
    def read(fmt):
        nonlocal pos
        v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=struct.calcsize('<'+fmt);return v
    def text(wide=False):
        nonlocal pos
        n=read('I');size=n*(2 if wide else 1)
        if size>100000 or pos+size>len(raw): raise ValueError('Bad page string')
        b=raw[pos:pos+size];pos+=size;return b.decode('utf-16le' if wide else 'utf8')
    next_id,count=read('q'),read('I');pages=[]
    for _ in range(count):
        start=pos;name,caption,id_=text(),text(True),read('q');read('I');read('q');read('q');read('q')
        read('I');read('I');read('B');read('I')
        if read('I')!=1: raise ValueError('Expected one subpage')
        text();text(True);read('q');read('I');read('I');text();read('I');read('q');read('q');read('I');read('I');read('B');read('I')
        header=raw[start:pos];objects=[]
        for _ in range(read('I')):
            record_start=pos
            if read('H')!=4: raise ValueError('Only verified native Text objects supported')
            object_name=text();body=pos
            if raw[body+49:body+54]!=bytes(5): raise ValueError('Unexpected hint/flag layout')
            pos+=141;caption_=text(True);pos+=9
            if pos>len(raw): raise ValueError('Truncated text record')
            objects.append(dict(name=object_name,body=bytearray(raw[body:body+141]),caption=caption_,record=raw[record_start:pos]))
        pages.append(dict(name=name,caption=caption,id=id_,header=header,objects=objects))
    if pos!=len(raw) or next_id<=max(p['id'] for p in pages): raise ValueError('Page framing mismatch')
    return pages


def visual_layout_pages(raw, project_width, project_height, client_width=1366,
                        client_height=768, header_pixels=64, footer_pixels=24):
    """Presentation-only reflow of the reviewed saved11 Text pages.

    Project dimensions must be read in native Editor; they are not inferred from
    a photograph. Client dimensions are a reference, not a measured runtime.
    All page/control identities, event links and non-presentation bytes survive.
    Native RTTI confirms enum16=ftRegular18; enum11 is ftAsOwner and enum4
    is ftMedium15. Documentation row order is not a serialized enum mapping.
    """
    for value, low, high in [(project_width,640,7680),(project_height,480,4320),
                              (client_width,640,7680),(client_height,480,4320),
                              (header_pixels,0,160),(footer_pixels,16,80)]:
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Invalid measured layout dimensions')
    fit = min(client_width/project_width, client_height/project_height)
    top, bottom = header_pixels/fit, footer_pixels/fit
    content_height = project_height-top-bottom
    if content_height*fit < 360:
        raise ValueError('Insufficient operator area')
    parsed = parse_pages(raw)
    if len(parsed) != 6 or {p['name'] for p in parsed} != {
            'PageProcess','PageDiagnostics','PageUiOverview',
            'PageUiAlarms','PageUiCharts','PageUiSettings'}:
        raise ValueError('Expected the reviewed one-station six-page layout')
    result = [raw[:12]]
    for page in parsed:
        result += [page['header'], U32(len(page['objects']))]
        for obj in page['objects']:
            body = bytearray(obj['body'])
            x,y,w,h = struct.unpack_from('<4f',body,8)
            scale = struct.unpack_from('<f',body,32)[0]
            if (body[31] != 4 or not math.isfinite(scale) or not .4 <= scale <= 2
                    or min(x,y) < 0 or min(w,h) <= 0
                    or x+w > 1440.01 or y+h > 920.01):
                raise ValueError('Layout differs from reviewed design; source preserved')
            # Full-height backgrounds cover the project, not a hard-coded corner.
            backdrop = not obj['caption'] and y == 0 and h == 920
            rect = (x*project_width/1440,
                    0 if backdrop else top+y*content_height/920,
                    w*project_width/1440,
                    project_height if backdrop else h*content_height/920)
            struct.pack_into('<4f',body,8,*rect)
            body[31] = FONT_REGULAR18
            struct.pack_into('<f',body,32,scale/fit)
            old = obj['record']
            start = 6+len(obj['name'].encode('utf8'))
            result.append(old[:start]+body+old[start+141:])
    return b''.join(result)


def repair_visual_page_style(raw, native_navigation=False):
    """Fix the deployed font; optionally keep native tabs as primary navigation.

    The operator chose native tabs after manually exposing their hit area.
    Remove only the duplicate sidebar/diagnostics page-navigation controls;
    preserve all data, command controls, scripts and their existing identities.
    Subpage header[-5] is FShowPagesPanel:0 inherits,1 shows,2 hides; confirmed
    against native loader129bd75 and getter129c28c, not guessed from a flag.
    """
    parsed=parse_pages(raw)
    if len(parsed)!=6 or sum(len(p['objects']) for p in parsed) not in (102,131):
        raise ValueError('Expected the reviewed single-station layout')
    result=[raw[:12]]
    for page in parsed:
        header=bytearray(page['header'])
        if header[-5] not in (0,1,2):
            raise ValueError('Unexpected native page panel setting')
        if native_navigation:header[-5]=1
        objects=[o for o in page['objects'] if not native_navigation or not re.fullmatch(
            r'Ui(?:Main|Overview0|Alarms|Charts|Settings)Nav[0-4]|UiDiagNav[0-3]',o['name'])]
        result += [bytes(header), U32(len(objects))]
        for z,obj in enumerate(objects):
            body=bytearray(obj['body'])
            if body[31] not in (4,11,FONT_REGULAR18):
                raise ValueError('Unexpected custom font; review before changing')
            body[31]=FONT_REGULAR18
            if native_navigation:struct.pack_into('<I',body,54,z)
            start=6+len(obj['name'].encode('utf8'));record=obj['record']
            result.append(record[:start]+body+record[start+141:])
    return b''.join(result)


def native_navigation_grid_pages(raw, project_width=1920, project_height=1080):
    """Reflow the reviewed operator pages into the measured native canvas.

    The 1920x1080 design canvas and 1366x768 Client were measured in Editor and
    Client. Native page tabs reserve about 60 design units at the top; reserve
    46 units for the footer. This is a semantic grid, not a scale of the old
    1440x920 artwork: overview columns, process KPI cards, pump cards and
    command row have independent dimensions and positions.
    """
    if (project_width, project_height) != (1920, 1080):
        raise ValueError('Reflow requires the measured 1920x1080 project canvas')
    pages = parse_pages(raw)
    expected = {'PageProcess','PageDiagnostics','PageUiOverview','PageUiAlarms',
                'PageUiCharts','PageUiSettings'}
    if len(pages) != 6 or {p['name'] for p in pages} != expected:
        raise ValueError('Expected the reviewed six-page operator UI')
    main_x, main_w = 280.0, 1600.0
    rects = {}
    scales = {}
    def setr(name, x, y, w, h, scale=None):
        rects[name] = (float(x),float(y),float(w),float(h))
        if scale is not None: scales[name] = float(scale)
    for page in pages:
        for obj in page['objects']:
            name=obj['name']
            if name.endswith('Background'):
                # Native page tabs reserve the top 64 design units. The
                # operator confirmed a full-canvas Text background intercepts
                # those tabs in Client, so keep the background below them.
                setr(name,0,64,1920,1016)
            elif name.endswith('Sidebar'):
                setr(name,0,64,248,972)
            elif name.endswith('Brand'):
                setr(name,24,82,200,76,1.0)

    # Overview: fixed column grid uses the full width under native tabs.
    setr('UiOverview0Heading',main_x,80,main_w,58,1.45)
    setr('UiOverviewCount0',main_x,148,main_w,48,.95)
    columns=[('Station',300,350),('Mode',660,150),('Pressure',820,220),
             ('Setpoint',1050,220),('Status',1280,390),('Open',1680,190)]
    overview=next(p for p in pages if p['name']=='PageUiOverview')
    for suffix,x,w in columns:
        title=next((o['name'] for o in overview['objects'] if o['name'].startswith('UiOverviewHeader') and
                    ((suffix=='Station' and o['name'].endswith('252')) or
                     (suffix=='Mode' and o['name'].endswith('540')) or
                     (suffix=='Pressure' and o['name'].endswith('678')) or
                     (suffix=='Setpoint' and o['name'].endswith('846')) or
                     (suffix=='Status' and o['name'].endswith('1004')))),None)
        if title:
            setr(title,x,220,w,48,.92)
        row_name={'Station':'UiRow0Name','Mode':'UiRow0Mode','Pressure':'UiRow0Pressure',
                  'Setpoint':'UiRow0Setpoint','Status':'UiRow0Status','Open':'UiRow0Open'}[suffix]
        setr(row_name,x,278,w,76,1.0 if suffix in ('Pressure','Setpoint') else .95)

    # Station card: three KPI cards, four equal pump cards and one distinct
    # command block. Existing objects, IDs and handlers are kept in place.
    setr('UiMainHeading',main_x,72,main_w,60)
    setr('ProcessTitle',main_x,78,1190,58,1.45)
    setr('UiMainWindow',1510,82,340,50,.95)
    setr('ProcessStatus',main_x,142,main_w,42,1.0)
    setr('ProcessDetail',main_x,190,main_w,52,.95)
    cards=[(main_x,520),(main_x+540,520),(main_x+1080,520)]
    for i,(x,w) in enumerate(cards): setr(f'UiMainPanel{i}',x,252,w,172)
    for name,x in [('ProcessPressureLabel',cards[0][0]+20),('ProcessSetpointLabel',cards[1][0]+20),('UiStationModeLabel',cards[2][0]+20)]: setr(name,x,266,480,32,.95)
    for name,x in [('ProcessPressure',cards[0][0]+20),('ProcessSetpoint',cards[1][0]+20),('UiStationMode',cards[2][0]+20)]: setr(name,x,302,480,66,1.75)
    for name,x in [('ProcessPressureNote',cards[0][0]+20),('ProcessSetpointNote',cards[1][0]+20),('UiStationModeNote',cards[2][0]+20)]: setr(name,x,372,480,40,.82)
    pump_w=383.0; pump_gap=16.0; pump_y=442.0; pump_h=222.0
    pump_x=[main_x+i*(pump_w+pump_gap) for i in range(4)]
    for i,x in enumerate(pump_x): setr(f'UiPumpPanel{i}',x,pump_y,pump_w,pump_h)
    x=pump_x[0]
    setr('ProcessDriveTitle',x+18,456,pump_w-36,34,.95)
    setr('ProcessFrequencyLabel',x+18,496,158,28,.78)
    setr('ProcessCurrentLabel',x+194,496,171,28,.78)
    setr('ProcessFrequency',x+18,526,158,48,1.0)
    setr('ProcessCurrent',x+194,526,171,48,1.0)
    setr('ProcessFaultLabel',x+18,580,130,26,.78)
    setr('ProcessFault',x+154,578,211,32,.92)
    setr('ProcessFrequencyNote',x+18,614,158,38,.76)
    setr('ProcessCurrentNote',x+194,614,171,38,.76)
    for i in range(1,4): setr(f'UiPumpUnknown{i}',pump_x[i]+18,456,pump_w-36,190,.88)
    setr('ProcessFaultNote',main_x,672,main_w,40,.82)
    setr('UiCommandPanel',main_x,728,main_w,174)
    setr('ProcessSpTitle',main_x+20,746,300,48,1.0)
    setr('ProcessSpMinus',main_x+360,744,70,60,1.05)
    setr('ProcessSpDraft',main_x+446,744,190,60,1.35)
    setr('ProcessSpPlus',main_x+652,744,70,60,1.05)
    setr('ProcessSpApply',main_x+748,744,350,60,1.0)
    setr('ProcessSpCancel',main_x+1118,744,350,60,1.0)
    setr('ProcessMainScope',main_x+20,818,main_w-40,64,.86)

    # Diagnostics: one readable full-width column with clear vertical groups.
    diag={'ProcessDiagTitle':(80,78,1760,58,1.4),'ProcessOPC':(80,152,1760,50,1.0),
          'ProcessMap':(80,216,850,46,.9),'ProcessValidity':(960,216,880,46,.9),
          'ProcessFreshness':(80,276,1760,58,.9),'ProcessAlarmWords':(80,350,1760,46,.9),
          'ProcessAlarmNote':(80,408,1760,70,.86),'DiagRadioTitle':(80,500,1760,42,.95),
          'DiagRadio':(80,552,1760,50,.9),'DiagRadioNote':(80,614,1760,44,.84),
          'ProcessChecks':(80,680,1760,100,.82),'ProcessScope':(80,800,1760,64,.82)}
    for n,v in diag.items():setr(n,*v)

    # Alarms and trends use large action targets and explicit status areas.
    setr('UiAlarmsHeading',main_x,80,main_w,58,1.4)
    alarm_x=[main_x+20+i*395 for i in range(4)]
    for i,x in enumerate(alarm_x):setr(f'UiMessages{i}',x,160,375,64,.95)
    setr('UiAlarmNote',main_x+20,250,main_w-40,94,.86)
    setr('UiAlarmStation0',main_x+20,370,380,62,.92)
    setr('UiAlarmState0',main_x+420,370,main_w-440,62,.92)

    setr('UiChartsHeading',main_x,80,main_w,58,1.4)
    setr('UiChartDescription',main_x+20,154,main_w-40,88,.9)
    for i,name in enumerate(('UiTrendsAll1','UiTrendsAll6','UiTrendsAll24')):
        setr(name,main_x+20+i*520,270,500,66,.95)
    setr('UiChartQuality',main_x+20,370,main_w-40,126,.86)
    setr('UiStationTrends0',main_x+20,530,main_w-40,70,1.0)

    setr('UiSettingsHeading',main_x,80,main_w,58,1.4)
    setr('UiSettingsIntro',main_x+20,154,main_w-40,92,.9)
    setr('UiSettingsStation0',main_x+20,280,main_w-40,112,.95)
    setr('UiSettingsHelp',main_x+20,424,main_w-40,180,.84)

    required={o['name'] for p in pages for o in p['objects']}
    if required-set(rects): raise ValueError('Unmapped native controls: '+','.join(sorted(required-set(rects))))
    # Require every object to fit the measured canvas and prevent accidental
    # collisions among the visible controls; card/background containers are
    # intentionally allowed to contain their child Text objects.
    for page in pages:
        controls=[o for o in page['objects'] if o['name'] in rects and
                  not o['name'].endswith(('Background','Sidebar','Heading','Brand')) and
                  not re.search(r'Panel\d*$',o['name']) and
                  o['name'] not in ('UiCommandPanel',)]
        for o in controls:
            x,y,w,h=rects[o['name']]
            if x<0 or y<0 or w<=0 or h<=0 or x+w>1920 or y+h>1080:
                raise ValueError('Control outside measured canvas: '+o['name'])
        for i,left in enumerate(controls):
            ax,ay,aw,ah=rects[left['name']]
            for right in controls[i+1:]:
                bx,by,bw,bh=rects[right['name']]
                if min(ax+aw,bx+bw)-max(ax,bx)>1 and min(ay+ah,by+bh)-max(ay,by)>1:
                    raise ValueError('Overlapping content controls: '+left['name']+' / '+right['name'])
    out=[raw[:12]]
    for page in pages:
        out.extend([page['header'],U32(len(page['objects']))])
        for z,o in enumerate(page['objects']):
            body=bytearray(o['body']);struct.pack_into('<4f',body,8,*rects[o['name']])
            if o['name'] in scales:struct.pack_into('<f',body,32,scales[o['name']])
            struct.pack_into('<I',body,54,z)
            record=o['record'];start=6+len(o['name'].encode('utf8'))
            out.append(record[:start]+body+record[start+141:])
    return b''.join(out)


def native_tab_clearance_pages(raw, project_width=1920, project_height=1080,
                               tab_height=64):
    """Move only page backgrounds below the native tab hit area."""
    if (project_width, project_height, tab_height) != (1920, 1080, 64):
        raise ValueError('Tab clearance must match the measured native canvas')
    pages = parse_pages(raw)
    expected = {'PageProcess','PageDiagnostics','PageUiOverview','PageUiAlarms',
                'PageUiCharts','PageUiSettings'}
    if len(pages) != 6 or {p['name'] for p in pages} != expected:
        raise ValueError('Expected the reviewed six-page operator UI')
    out = [raw[:12]]
    changed = 0
    for page in pages:
        out.extend([page['header'], U32(len(page['objects']))])
        backgrounds = [o for o in page['objects'] if o['name'].endswith('Background')]
        if len(backgrounds) != 1:
            raise ValueError('Expected one background on '+page['name'])
        for obj in page['objects']:
            body = bytearray(obj['body'])
            if obj['name'].endswith('Background'):
                x,y,w,h = struct.unpack_from('<4f',body,8)
                if (x,w) != (0.0,1920.0) or (y,h) not in ((0.0,1080.0),(64.0,1016.0)):
                    raise ValueError('Unexpected background geometry on '+page['name'])
                if (y,h) != (64.0,1016.0):
                    struct.pack_into('<4f',body,8,0.0,64.0,1920.0,1016.0)
                    changed += 1
            start = 6+len(obj['name'].encode('utf8'))
            out.append(obj['record'][:start]+body+obj['record'][start+141:])
    if changed not in (0,4):
        raise ValueError('Expected four uncovered pages or an already corrected copy')
    return b''.join(out)


class Builder:
    def __init__(self,data):
        self.catalog=data;self.stations=data['stations'];self.events=[];self.objects=[];self.uid=100000
        raw=SOURCE.read_bytes()
        if SHA(raw)!=PAGES_SHA: raise ValueError('Reviewed page fixture changed')
        self.old=parse_pages(raw)
        self.common=bytes(self.old[0]['objects'][0]['body'])
        self.page_seed=(ROOT/'source/scada-seed-2.6.15/Pages.spg').read_bytes()[12:193]

    def event(self,name,code):
        id_=8+len(self.events);self.events.append(dict(id=id_,name=name+'_OnClick',body='begin\n  '+code+'\nend.'));return id_

    def text(self,name,caption,rect,scale=.85,bg=PANEL,fg=TEXT,event=-1):
        b=bytearray(self.common);self.uid+=4
        struct.pack_into('<I',b,4,0);struct.pack_into('<4f',b,8,*rect)
        b[24]=255;b[29:31]=b'\1\1';b[31]=4
        struct.pack_into('<ff',b,32,scale,0);struct.pack_into('<I',b,40,fg);b[44]=255;struct.pack_into('<I',b,45,bg)
        struct.pack_into('<I',b,54,len(self.objects));struct.pack_into('<q',b,75,event)
        struct.pack_into('<I',b,107,self.uid);struct.pack_into('<q',b,111,-1)
        self.objects.append(dict(name=name,caption=caption,rect=rect,uid=self.uid,event=event))
        return struct.pack('<H',4)+string(name)+b+string(caption,True)+bytes.fromhex('000000ffffff00ff06')

    def header(self,name,caption,id_):
        b=bytearray(self.page_seed);struct.pack_into('<q',b,33,id_);b=bytes(b)
        for a,c in [(string('Page1'),string(name)),(string('Страница 1',True),string(caption,True)),(string('Subpage1'),string('Sub'+name)),(string('Подстраница 1',True),string(caption,True)),(U32(9156),U32(90000+id_*8)),(U32(9160),U32(90004+id_*8))]:
            if b.count(a)!=1: raise ValueError('Page header mismatch')
            b=b.replace(a,c,1)
        return b

    def frame(self,key,title):
        out=[self.text(key+'Background','',(0,0,1440,920),bg=BG),self.text(key+'Sidebar','',(0,0,220,920),.95,bg=0x101A28),self.text(key+'Brand','НАСОСНЫЕ\r\nСТАНЦИИ',(18,30,188,82),1.05,bg=0x101A28,fg=ACCENT)]
        for i,(label,page) in enumerate([('Обзор станций','PageUiOverview'),('Аварии и события','PageUiAlarms'),('Графики','PageUiCharts'),('Настройки','PageUiSettings'),('Диагностика','PageDiagnostics')]):
            ev=self.event(key+'Nav'+str(i),'UiGoPage('+pascal(page)+', GetClientName);')
            out.append(self.text(key+'Nav'+str(i),label,(18,148+65*i,188,48),.82,bg=0x1A293A,event=ev))
        out.append(self.text(key+'Heading',title,(252,34,1156,56),1.35,bg=BG))
        return out

    def serialize_page(self,header,rows):
        normalized=[]
        for z,record in enumerate(rows):
            raw=bytearray(record);body=6+struct.unpack_from('<I',raw,2)[0]
            struct.pack_into('<I',raw,body+54,z);normalized.append(bytes(raw))
        return header+U32(len(rows))+b''.join(normalized)

    def page(self,name,caption,id_,rows):
        return self.serialize_page(self.header(name,caption,id_),rows)

    def build(self):
        pages=[]
        # Keep original page IDs0/1 and exact OnClick links3..6 for the verified command path.
        layouts={
          'ProcessTitle':(252,24,1150,52),'ProcessStatus':(252,92,1156,44),'ProcessDetail':(252,144,1156,52),
          'ProcessPressureLabel':(268,222,350,30),'ProcessPressure':(268,260,350,72),'ProcessPressureNote':(268,334,350,70),
          'ProcessSetpointLabel':(656,222,350,30),'ProcessSetpoint':(656,260,350,72),'ProcessSetpointNote':(656,334,350,70),
          'ProcessDriveTitle':(268,439,252,32),'ProcessFrequencyLabel':(268,482,124,28),'ProcessCurrentLabel':(398,482,122,28),
          'ProcessFrequency':(268,518,124,48),'ProcessCurrent':(398,518,122,48),'ProcessFaultLabel':(268,574,252,26),
          'ProcessFault':(268,606,252,42),'ProcessFrequencyNote':(252,654,560,38),'ProcessCurrentNote':(828,654,580,38),'ProcessFaultNote':(252,696,1156,34),
          'ProcessSpTitle':(268,754,250,36),'ProcessSpMinus':(548,754,58,42),'ProcessSpDraft':(618,754,140,42),
          'ProcessSpPlus':(770,754,58,42),'ProcessSpApply':(850,754,268,42),'ProcessSpCancel':(1138,754,240,42),'ProcessMainScope':(268,810,1110,72)}
        station_rows=self.frame('UiMain','')
        for j in range(3):station_rows.append(self.text('UiMainPanel'+str(j),'',(252+388*j,208,372 if j<2 else 380,204),bg=PANEL))
        for j in range(4):station_rows.append(self.text('UiPumpPanel'+str(j),'',(252+292*j,426,280,224),bg=PANEL))
        station_rows.append(self.text('UiCommandPanel','',(252,740,1156,154),bg=PANEL))
        for o in self.old[0]['objects']:
            b=bytearray(o['body']);struct.pack_into('<4f',b,8,*layouts[o['name']]);struct.pack_into('<I',b,54,len(station_rows))
            struct.pack_into('<I',b,40,TEXT);struct.pack_into('<I',b,45,PANEL)
            scale=1.7 if o['name'] in ['ProcessPressure','ProcessSetpoint'] else .7 if o['name'].endswith(('Note','Label')) else .9
            if o['name']=='ProcessTitle':scale=1.15;struct.pack_into('<I',b,45,BG)
            if o['name'] in ['ProcessSpMinus','ProcessSpPlus','ProcessSpCancel']:struct.pack_into('<I',b,45,0x266996)
            if o['name']=='ProcessSpApply':struct.pack_into('<I',b,45,ACCENT);struct.pack_into('<I',b,40,0x082B26)
            struct.pack_into('<f',b,32,scale)
            station_rows.append(struct.pack('<H',4)+string(o['name'])+b+string(o['caption'],True)+bytes.fromhex('000000ffffff00ff06'))
        station_rows += [self.text('UiStationModeLabel','РЕЖИМ СТАНЦИИ',(1044,222,340,32)),self.text('UiStationMode','Нет данных',(1044,268,340,52),1.4),self.text('UiStationModeNote','Состояние селектора передаёт ПЛК',(1044,334,340,64),.7)]
        for j in range(1,4):
            station_rows.append(self.text('UiPumpUnknown'+str(j),'НАСОС '+str(j+1)+'\r\n\r\nЧастота: нет данных\r\nТок: нет данных\r\nОшибка ПЧ: нет данных',(268+292*j,439,248,195),.82))
        popup=self.event('UiMainOpenWindow',"UiOpenWindow(0, GetClientName);")
        station_rows.append(self.text('UiMainWindow','Отдельное окно',(1150,166,258,32),.75,bg=0x1A293A,fg=ACCENT,event=popup))
        main_page=self.page('PageProcess','Станция',0,station_rows)
        # Diagnostics and all original bindings remain available.
        diag=self.old[1]
        diag_rows=[self.text('UiDiagBackground','',(0,0,1440,920),bg=BG)]+[o['record'] for o in diag['objects']]
        for i,label in enumerate(['Обзор','Аварии','Графики','Настройки']):
            pg=['PageUiOverview','PageUiAlarms','PageUiCharts','PageUiSettings'][i]
            ev=self.event('UiDiagNav'+str(i),'UiGoPage('+pascal(pg)+', GetClientName);')
            diag_rows.append(self.text('UiDiagNav'+str(i),label,(32+i*344,6,324,42),.8,bg=0x1A293A,event=ev))
        diag_page=self.serialize_page(diag['header'],diag_rows)
        overview_pages=[]
        for chunk in range((len(self.stations)+7)//8):
            rows=self.frame('UiOverview'+str(chunk),'Обзор насосных станций')
            rows.append(self.text('UiOverviewCount'+str(chunk),'Станций: '+str(len(self.stations))+' · реальные привязки · без демонстрационных данных',(252,110,1156,44),.85,bg=BG,fg=MUTED))
            for x,title,width in [(252,'СТАНЦИЯ',280),(540,'РЕЖИМ',130),(678,'ДАВЛЕНИЕ',160),(846,'УСТАВКА',150),(1004,'СОСТОЯНИЕ',250)]:rows.append(self.text('UiOverviewHeader'+str(chunk)+str(x),title,(x,180,width,36),.7,fg=MUTED))
            for i,s in enumerate(self.stations[chunk*8:chunk*8+8],chunk*8):
                y=230+(i%8)*74;pg='PageProcess' if i==0 else 'PageUiStation_'+s['id'].replace('-','_')
                ev=self.event('UiOpenStation'+str(i),'UiGoPage('+pascal(pg)+', GetClientName);')
                for suffix,caption,x,width in [('Name',s['name'],252,280),('Mode','Нет данных',540,130),('Pressure','Нет данных',678,160),('Setpoint','Нет данных',846,150),('Status','Ожидание ПЛК',1004,250)]:
                    rows.append(self.text('UiRow'+str(i)+suffix,caption,(x,y,width,62),.78,fg=ACCENT if suffix=='Name' else TEXT,event=ev if suffix=='Name' else -1))
                ev=self.event('UiPopup'+str(i),'UiOpenWindow('+str(i)+', GetClientName);')
                rows.append(self.text('UiRow'+str(i)+'Open','Окно',(1264,y,144,62),.8,bg=0x1A293A,fg=ACCENT,event=ev))
            if len(self.stations)>8:
                target='PageUiOverview1' if chunk==0 else 'PageUiOverview'
                ev=self.event('UiOverviewNext'+str(chunk),'UiGoPage('+pascal(target)+', GetClientName);')
                rows.append(self.text('UiOverviewNext'+str(chunk),'Другие станции',(1100,850,308,44),.85,event=ev))
            overview_pages.append(self.page('PageUiOverview'+(str(chunk) if chunk else ''),'Все станции'+(' · 2' if chunk else ''),2+chunk,rows))
        pages.extend(overview_pages);pages.extend([main_page,diag_page])
        alarm_rows=self.frame('UiAlarms','Аварии и события')
        for i,(caption,group) in enumerate([('Активные',-1001),('Неподтверждённые',-1000),('Все сообщения',-1),('Действия оператора',-4)]):
            ev=self.event('UiMessages'+str(i),f"if GetClientName <> '' then GoToMessagesGroupClient(GetClientName, {group});")
            alarm_rows.append(self.text('UiMessages'+str(i),caption,(252+i*292,120,280,48),.8,bg=0x1A293A,fg=ACCENT,event=ev))
        alarm_rows.append(self.text('UiAlarmNote','Подтверждение в штатном журнале не снимает причину аварии и не сбрасывает ПЧ.\r\nНиже — текущий статус; история и подтверждения открываются кнопками сверху.',(252,190,1156,75),.85,bg=BG,fg=MUTED))
        for i,s in enumerate(self.stations):
            alarm_rows.append(self.text('UiAlarmStation'+str(i),s['name'],(252,290+i*31,280,30),.72))
            alarm_rows.append(self.text('UiAlarmState'+str(i),'Нет подтверждённых данных',(540,290+i*31,868,30),.72))
        pages.append(self.page('PageUiAlarms','Аварии',4,alarm_rows))
        chart_rows=self.frame('UiCharts','Графики и архив')
        chart_rows.append(self.text('UiChartDescription','Архивные тренды открываются в штатной панели Simple-Scada.\r\nПериод, масштаб, курсор, выбор переменных и экспорт — средства этой панели.',(252,110,1156,80),.9,bg=BG,fg=MUTED))
        for j,hours in enumerate([1,6,24]):
            ev=self.event('UiTrendsAll'+str(hours),f"if GetClientName <> '' then GoToTrendsClient(GetClientName, Now - {hours}/24.0, Now);")
            chart_rows.append(self.text('UiTrendsAll'+str(hours),'Все станции · '+str(hours)+' ч',(252+j*388,222,372,56),.95,bg=0x1A293A,fg=ACCENT,event=ev))
        chart_rows.append(self.text('UiChartQuality','Отсутствующие и недостоверные точки не заменяются нулём.\r\nГрафик давления доступен после проверки достоверности источника и архива.\r\nДавление/уставку, частоту и ток размещать в отдельных группах/шкалах.',(252,310,1156,120),.9,bg=PANEL))
        for i,s in enumerate(self.stations):
            ev=self.event('UiTrendsStation'+str(i),f'UiOpenTrends({i}, GetClientName);')
            chart_rows.append(self.text('UiStationTrends'+str(i),s['name']+' · архив',(252,450+i*26,1156,25),.72,fg=ACCENT,event=ev))
        pages.append(self.page('PageUiCharts','Графики',5,chart_rows))
        settings=self.frame('UiSettings','Настройки и каталог станций')
        settings.append(self.text('UiSettingsIntro','Параметры подключения и состав станций. Добавление выполняется наладчиком через каталог.\r\nРабочая уставка остаётся общей для HMI и SCADA; это не отдельная уставка интерфейса.',(252,112,1156,76),.84,bg=BG,fg=MUTED))
        for i,s in enumerate(self.stations):
            text=s['id']+' · '+s['name']+' · '+s['group']+'\r\n'+s['computer']+' / '+s['server']+' / '+s['itemPrefix']+' · '+str(s['pumpCount'])+' насосов'
            settings.append(self.text('UiSettingsStation'+str(i),text,(252,214+i*34,1156,33),.65))
        settings.append(self.text('UiSettingsHelp','Новая станция: ui/native-console/catalog.json → сборка → новая копия → проверка тегов.\r\nДля дополнительных станций управление отключено до проверки их контракта.\r\nПароли, лицензии и ключи M2M24 в каталог не включаются.\r\nУправление пользователями и архивом — штатные настройки Simple-Scada.',(252,790,1156,112),.75,bg=BG,fg=MUTED))
        pages.append(self.page('PageUiSettings','Настройки',6,settings))
        # Extra stations reuse one renderer; only independently verified station001 has commands.
        for i,s in enumerate(self.stations[1:],1):
            rows=self.frame('UiDetail'+str(i),s['name'])
            for j,suffix in enumerate(['Mode','Pressure','Setpoint','Status']):rows.append(self.text('UiDetail'+str(i)+suffix,'Нет данных',(252,150+110*j,1156,90),1.25))
            rows.append(self.text('UiDetail'+str(i)+'Pumps',str(s['pumpCount'])+' насосов · индивидуальные теги ещё не подтверждены\r\nКоманды этой станции не подключены.',(252,630,1156,120),.95))
            pages.append(self.page('PageUiStation_'+s['id'].replace('-','_'),s['name'],7+i,rows))
        next_id=max([p['id'] for p in self.old]+[8+len(self.stations),7])+1
        self.pages=I64(next_id)+U32(len(pages))+b''.join(pages)
        self.windows=self.build_windows()
        self.module=self.build_module()
        return self

    def build_windows(self):
        # Minimal window frame from official2.6.15 Demo wndActive; no demo objects,
        # variables, actions or messages are copied. All three window events=-1.
        prefix=bytes.fromhex('00000000000000000000d4430000344300008f4400000544ff000000000101040000803f00000000000000ffff000000ff0000000000000000000000000000')
        tail=bytes.fromhex('0000000002f8300000ffffffffffffffffffffffffffffffffffffffffffffffff010101000000000000')
        windows=[]
        for i,s in enumerate(self.stations):
            frame=bytearray(prefix);struct.pack_into('<4f',frame,8,80,90,1100,640)
            struct.pack_into('<I',frame,45,BG)
            end=bytearray(tail);struct.pack_into('<I',end,5,95000+4*i)
            rows=[self.text('UiWindow'+str(i)+'Title',s['name'],(100,138,1060,64),1.3)]
            for j,suffix in enumerate(['Mode','Pressure','Setpoint','Status']):rows.append(self.text('UiWindow'+str(i)+suffix,'Нет данных',(100,220+88*j,1060,64),1.1))
            rows.append(self.text('UiWindow'+str(i)+'Note','Наблюдение. Изменение уставки — в основной карточке станции.',(100,596,1060,68),.8,fg=MUTED))
            windows.append(b'\xfe'+I64(i+1)+string('UiWindow_'+s['id'].replace('-','_'))+frame+string(s['name'],True)+end+U32(len(rows))+b''.join(rows))
        return string('..\\')+U32(0)+U32(0)+string('..\\')+U32(0)+U32(len(windows))+b''.join(windows)

    def build_module(self):
        source=(UI/'OperatorConsole.txt').read_text(encoding='utf8')
        functions=[]
        for fn,field in [('UiKey','id'),('UiName','name'),('UiPrefix','itemPrefix'),('UiHost','computer'),('UiServer','server')]:
            cases='\n'.join('    '+str(i)+': Result := '+pascal(s[field].replace('-','_') if fn=='UiKey' else s[field])+';' for i,s in enumerate(self.stations))
            functions.append(f"function {fn}(Index: Integer): string;\nbegin\n  Result := '';\n  case Index of\n{cases}\n  end;\nend;")
        cases='\n'.join(f"    {i}: Result := {s['staleSeconds']};" for i,s in enumerate(self.stations))
        functions.append(f'function UiStale(Index: Integer): Integer;\nbegin\n  Result := 15;\n  case Index of\n{cases}\n  end;\nend;')
        paint=[]
        for i,s in enumerate(self.stations):
            for name,var in [('Mode','ModeText'),('Pressure','PressureText'),('Setpoint','SetpointText'),('Status','StatusText')]:
                paint.append(f'  UiRow{i}{name}.Text := Ui{var}[{i}];')
                paint.append(f'  UiWindow{i}{name}.Text := '+pascal({'Mode':'Режим: ','Pressure':'Давление: ','Setpoint':'Общая уставка ПЛК: ','Status':'Состояние: '}[name])+f' + Ui{var}[{i}];')
                if i:paint.append(f'  UiDetail{i}{name}.Text := Ui{var}[{i}];')
            paint.append(f'  UiAlarmState{i}.Text := UiStatusText[{i}];')
        paint+=["  ProcessTitle.Text := UiName(0) + ' | РЕЖИМ: ' + UiModeText[0];",'  UiStationMode.Text := UiModeText[0];']
        source=source.replace('__STATION_COUNT__',str(len(self.stations))).replace('__STATION_FUNCTIONS__','\n'.join(functions)).replace('__PAINT__','\n'.join(paint))
        if '__' in source:raise ValueError('Unresolved module slot')
        return source


def pascal(s):return "'"+s.replace("'","''")+"'"


def build(path=UI/'catalog.json',out=OUT):
    out=Path(out).resolve()
    if out==ROOT or any(out.is_relative_to(p.resolve()) for p in [ROOT/'source',ROOT/'ui']):
        raise ValueError('Build output must be outside source/ui directories')
    data=catalog(path);b=Builder(data).build();out.mkdir(parents=True,exist_ok=True)
    (out/'Pages.spg').write_bytes(b.pages);(out/'Windows.swn').write_bytes(b.windows)
    (out/'OperatorConsole.txt').write_text(b.module,encoding='utf8',newline='\n')
    packet=dict(schemaVersion=1,pages=base64.b64encode(b.pages).decode(),windows=base64.b64encode(b.windows).decode(),module=b.module,events=b.events,
                pressureDisplayChanges=pressure_display_changes('StationDiagnostics'))
    plan=[]
    for s in data['stations']:
        key=s['id'].replace('-','_')
        plan.append(dict(stationId=s['id'],nativeGroupName='UiTrend_'+key,
            pressureItems=[s['itemPrefix']+'PressurePV_x100',s['itemPrefix']+'PressureSP_x100'],
            rawPressureDivisor=100,pressureDisplayRequiresVerifiedSourceMask=True,validityItem=s['itemPrefix']+'PressureSourceOK',freshnessItem=s['itemPrefix']+'PlcAliveCounter',frequencyItem=s['itemPrefix']+'Vfd1FreqRaw',currentItem=s['itemPrefix']+'Vfd1CurrentRaw',
            rawFrequencyAndCurrentDivisor=10,archiveQualityRequired=True,configureInNativeEditor=True))
    (out/'archive-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    raw=json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode()
    installer=(ROOT/'tools/native_operator_console_install_template.ps1').read_text().replace('__PACKET__',base64.b64encode(raw).decode()).replace('__PACKET_SHA__',SHA(raw))
    (out/'Install-Operator-Console-01.ps1').write_text(installer,encoding='utf8',newline='\n')
    result=dict(schemaVersion=1,targetProject='codex_diag_11',baseProject='codex_diag_10',basePagesSHA256=PAGES_SHA,baseScriptsSHA256=SCRIPTS_SHA,stationCount=len(b.stations),pageCount=len(parse_pages(b.pages)),textObjectCount=len(b.objects),events=len(b.events),pagesSHA256=SHA(b.pages),windowsSHA256=SHA(b.windows),moduleSHA256=SHA(b.module.encode()),installerSHA256=SHA(installer.encode()),nativeGUICompileObserved=False,nativeArchiveSetupRequired=True,hardwareCommandsSent=0,objects=b.objects)
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--catalog',type=Path,default=UI/'catalog.json');parser.add_argument('--out',type=Path,default=OUT)
    a=parser.parse_args();r=build(a.catalog,a.out);print('Built native SCADA11:',r['pageCount'],'pages,',r['events'],'events;',r['stationCount'],'real station(s)')
