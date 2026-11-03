"""Readonly overview components for the saved one-station native console."""
import importlib.util
import re
import struct
from pathlib import Path

_spec=importlib.util.spec_from_file_location('_overview_builder',Path(__file__).with_name('build_native_operator_console_01.py'))
_builder=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_builder)
U32, parse_pages = _builder.U32, _builder.parse_pages


def overview_pages(raw):
    pages=parse_pages(raw)
    page=next((p for p in pages if p['name']=='PageUiOverview'),None)
    if len(pages)!=6 or page is None or sum(len(p['objects']) for p in pages)!=102:
        raise ValueError('Expected saved six-page native-navigation console')
    by_name={o['name']:o for o in page['objects']}
    if any(n.startswith('UiOverviewMetric') for n in by_name):
        raise ValueError('Overview panel already exists; review before replacing')
    required={'UiOverview0Background','UiOverview0Sidebar','UiOverview0Brand','UiOverview0Heading',
              'UiOverviewCount0','UiRow0Name','UiRow0Mode','UiRow0Pressure','UiRow0Setpoint','UiRow0Status','UiRow0Open'}
    if not required <= set(by_name):raise ValueError('Unexpected overview controls')
    if struct.unpack_from('<4f',by_name['UiOverview0Background']['body'],8)!=(0.,64.,1920.,1016.):
        raise ValueError('Verify measured canvas and native tab clearance first')
    uid=max(struct.unpack_from('<I',o['body'],107)[0] for p in pages for o in p['objects'])
    proto=by_name['UiOverview0Heading']['body']
    back,front=[],[]
    def text(name,caption,rect,scale=1.,bg=_builder.PANEL,fg=_builder.TEXT,layer=front):
        nonlocal uid
        uid+=4;b=bytearray(proto)
        struct.pack_into('<4f',b,8,*rect);b[31]=_builder.FONT_REGULAR18
        struct.pack_into('<f',b,32,scale);struct.pack_into('<I',b,40,fg);struct.pack_into('<I',b,45,bg)
        struct.pack_into('<q',b,75,-1);struct.pack_into('<I',b,107,uid)
        record=struct.pack('<H',4)+_builder.string(name)+b+_builder.string(caption,True)+bytes.fromhex('000000ffffff00ff06')
        layer.append(record)
    for i,label in enumerate(['СТАНЦИЙ В ОБЗОРЕ','ДАННЫЕ ПЛК СВЕЖИЕ','СТАНЦИИ С ОШИБКОЙ ПЧ 1','БЕЗ СВЕЖИХ ДАННЫХ']):
        x=280+i*404
        text(f'UiOverviewMetric{i}Border','',(x,188,388,164),bg=0x2A3B4E,layer=back)
        text(f'UiOverviewMetric{i}Panel','',(x+1,189,386,162),layer=back)
        text(f'UiOverviewMetric{i}Label',label,(x+20,204,348,30),.8,fg=_builder.MUTED)
        text(f'UiOverviewMetric{i}Value','Нет данных',(x+20,238,348,66),2.5)
        note=['Подключённый каталог','По изменению счётчика ПЛК','По доступному коду ПЧ 1','Ожидается обновление ПЛК'][i]
        text(f'UiOverviewMetric{i}Note',note,(x+20,312,348,30),.75,fg=_builder.MUTED)
    text('UiOverviewTableBorder','',(280,390,1600,316),bg=0x2A3B4E,layer=back)
    text('UiOverviewTablePanel','',(281,391,1598,314),layer=back)
    text('UiOverviewTableHeaderBand','',(281,474,1598,46),bg=0x1A293A,layer=back)
    text('UiOverviewTableTitle','Станции',(300,412,600,44),1.2)
    text('UiOverviewPumpHeader','НАСОСЫ',(1140,482,150,32),.8,bg=0x1A293A,fg=_builder.MUTED)
    text('UiOverviewUpdatedHeader','ОБНОВЛЕНИЕ',(1610,482,160,32),.8,bg=0x1A293A,fg=_builder.MUTED)
    text('UiOverviewRowMeta','Стенд · station-001',(300,582,310,28),.72,fg=_builder.MUTED)
    for i in range(4):
        text(f'UiOverviewPumpMarker{i}',str(i+1),(1140+i*34,538,26,32),.85,bg=0x1A293A,fg=_builder.MUTED)
    text('UiOverviewPumpInfo','Нет данных',(1140,580,150,36),.7,fg=_builder.MUTED)
    text('UiOverviewUpdated','Нет обновлений',(1610,538,160,70),.85,fg=_builder.MUTED)
    text('UiOverviewFooter','Показана 1 станция · рабочие данные',(300,650,1560,36),.8,fg=_builder.MUTED)
    text('UiOverviewHelp','Подробные показания — на вкладке «Станция». Обновление относится к счётчику ПЛК.\r\nДля насосов 2–4 индивидуальные показания пока не получены.',(280,730,1600,88),.85,fg=_builder.MUTED)
    rects={'UiOverview0Heading':(280,80,1600,58),'UiOverviewCount0':(280,144,1600,34),
           'UiOverview0Sidebar':(0,64,248,972)}
    columns=[('Name','252',300,310),('Mode','540',620,130),('Pressure','678',760,180),
             ('Setpoint','846',950,180),('Status','1004',1300,300),('Open',None,1780,90)]
    for suffix,header,x,width in columns:
        rects['UiRow0'+suffix]=(x,530,width,80 if suffix!='Name' else 48)
        if header:rects['UiOverviewHeader0'+header]=(x,482,width,32)
    rewritten=[]
    for o in page['objects']:
        b=bytearray(o['body']);name=o['name']
        if name in rects:struct.pack_into('<4f',b,8,*rects[name])
        scale=1.75 if name=='UiOverview0Heading' else .85 if 'Header' in name else 1.35 if name in ('UiRow0Pressure','UiRow0Setpoint') else None
        if scale is not None:struct.pack_into('<f',b,32,scale)
        start=6+len(name.encode());rewritten.append(o['record'][:start]+b+o['record'][start+141:])
    # Container backgrounds must precede the data controls; never cover clicks.
    count=3
    if [o['name'] for o in page['objects'][:count]]!=['UiOverview0Background','UiOverview0Sidebar','UiOverview0Brand']:
        raise ValueError('Unexpected background/sidebar stacking')
    records=rewritten[:count]+back+rewritten[count:]+front
    normalized=[]
    for z,record in enumerate(records):
        b=bytearray(record);start=6+struct.unpack_from('<I',b,2)[0]
        struct.pack_into('<I',b,start+54,z);normalized.append(bytes(b))
    result=[raw[:12]]
    for p in pages:
        result.append(p['header'])
        rows=normalized if p is page else [o['record'] for o in p['objects']]
        result += [U32(len(rows)),b''.join(rows)]
    return b''.join(result)


def overview_module(text):
    if 'UiDashboardFresh' in text:raise ValueError('Overview module already changed')
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Unexpected saved OperatorConsole; original preserved')
        text=text.replace(old,new,1)
    replace('  UiHasSample, UiHasProgress: array[0..15] of Boolean;',
            '  UiHasSample, UiHasProgress: array[0..15] of Boolean;\n  UiDashboardFresh, UiDashboardFaultKnown, UiDashboardFault: array[0..15] of Boolean;')
    replace("  Counter := 0;\n  UiModeText[Index]", "  Counter := 0;\n  UiDashboardFresh[Index] := False;\n  UiDashboardFaultKnown[Index] := False;\n  UiDashboardFault[Index] := False;\n  UiModeText[Index]")
    replace("  UiStatusText[Index] := 'Обновление ПЛК подтверждено';",
            "  UiDashboardFresh[Index] := True;\n  UiStatusText[Index] := 'Обновление ПЛК подтверждено';")
    replace("  if UiWord(Index, 'Vfd1FaultCode', Fault) then\n    if Fault <> 0 then UiStatusText[Index] := 'Насос 1: ошибка ПЧ, код ' + IntToStr(Fault);",
            "  if UiWord(Index, 'Vfd1FaultCode', Fault) then\n  begin\n    UiDashboardFaultKnown[Index] := True;\n    UiDashboardFault[Index] := Fault <> 0;\n    if Fault <> 0 then UiStatusText[Index] := 'Насос 1: ошибка ПЧ, код ' + IntToStr(Fault);\n  end;")
    replace('procedure OperatorUiUpdate;\nvar Index: Integer;',
            'procedure OperatorUiUpdate;\nvar Index, FreshCount, FaultCount, KnownCount: Integer;')
    replace('  for Index := 0 to UiStationCount - 1 do UiSample(Index);', '''  for Index := 0 to UiStationCount - 1 do UiSample(Index);
  FreshCount := 0; FaultCount := 0; KnownCount := 0;
  for Index := 0 to UiStationCount - 1 do
  begin
    if UiDashboardFresh[Index] then FreshCount := FreshCount + 1;
    if UiDashboardFaultKnown[Index] then KnownCount := KnownCount + 1;
    if UiDashboardFault[Index] then FaultCount := FaultCount + 1;
  end;
  UiOverviewMetric0Value.Text := IntToStr(UiStationCount);
  UiOverviewMetric1Value.Text := IntToStr(FreshCount);
  UiOverviewMetric3Value.Text := IntToStr(UiStationCount - FreshCount);
  if KnownCount = 0 then UiOverviewMetric2Value.Text := 'Нет данных'
  else UiOverviewMetric2Value.Text := IntToStr(FaultCount);
  UiOverviewMetric2Note.Text := 'Подтверждено тегов ПЧ 1: ' + IntToStr(KnownCount);
  if UiStationCount = 0 then
    UiOverviewMetric3Note.Text := 'Нет станций в обзоре'
  else if FreshCount = 0 then
    UiOverviewMetric3Note.Text := 'Нет свежего подтверждения ПЛК'
  else if FreshCount = UiStationCount then
    UiOverviewMetric3Note.Text := 'У всех станций есть свежее обновление'
  else
    UiOverviewMetric3Note.Text := 'Есть станции без свежих данных';
  UiOverviewUpdated.Text := 'Нет обновлений';
  UiOverviewPumpInfo.Text := 'Нет данных';
  if UiDashboardFresh[0] then
    UiOverviewUpdated.Text := 'Счётчик: ' + IntToStr(Round(Now * 86400.0 - UiLastProgress[0])) + ' с';
  if UiDashboardFaultKnown[0] then
  begin
    if UiDashboardFault[0] then UiOverviewPumpInfo.Text := '1: ошибка; 2-4: н/д'
    else UiOverviewPumpInfo.Text := '1: код 0; 2-4: н/д';
  end;''')
    if re.search(r'\.Value\s*:=|SetVariableValue|AddActionMessage',text):
        raise ValueError('Overview module must remain read-only')
    return text


def station_card_module(text):
    """Extend the saved read-only overview module with card status summaries."""
    if 'UiCardEventText' in text or 'UiCardConnectionText' in text:
        raise ValueError('Station card module already changed')
    if 'UiDashboardFresh' not in text or 'UiOverviewPumpInfo' not in text:
        raise ValueError('Expected saved overview-panel OperatorConsole')

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Unexpected saved OperatorConsole; original preserved')
        text = text.replace(old, new, 1)

    replace("  UiDashboardFresh, UiDashboardFaultKnown, UiDashboardFault: array[0..15] of Boolean;",
            "  UiDashboardFresh, UiDashboardFaultKnown, UiDashboardFault: array[0..15] of Boolean;\n"
            "  UiDashboardFaultCode: array[0..15] of Integer;")
    replace("  UiDashboardFault[Index] := False;\n  UiModeText[Index]",
            "  UiDashboardFault[Index] := False;\n  UiDashboardFaultCode[Index] := -1;\n  UiModeText[Index]")
    replace("    UiDashboardFaultKnown[Index] := True;\n    UiDashboardFault[Index] := Fault <> 0;",
            "    UiDashboardFaultKnown[Index] := True;\n    UiDashboardFaultCode[Index] := Fault;\n    UiDashboardFault[Index] := Fault <> 0;")
    replace("  UiOverviewPumpInfo.Text := 'Нет данных';",
            "  UiOverviewPumpInfo.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus0.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus1.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus2.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus3.Text := 'Нет данных';\n"
            "  UiCardEventText.Text := 'Текущий код ПЧ 1: нет данных. История — вкладка «Аварии».';\n"
            "  UiCardConnectionText.Text := 'Нет свежего подтверждения ПЛК. Подробности — вкладка «Диагностика».';")
    if "UiOverviewMetric3Note.Text := 'У всех станций есть свежее обновление'" not in text:
        replace("  UiOverviewMetric3Value.Text := IntToStr(UiStationCount - FreshCount);",
                "  UiOverviewMetric3Value.Text := IntToStr(UiStationCount - FreshCount);\n"
                "  if UiStationCount = 0 then UiOverviewMetric3Note.Text := 'Нет станций в обзоре'\n"
                "  else if FreshCount = 0 then UiOverviewMetric3Note.Text := 'Нет свежего подтверждения ПЛК'\n"
                "  else if FreshCount = UiStationCount then UiOverviewMetric3Note.Text := 'У всех станций есть свежее обновление'\n"
                "  else UiOverviewMetric3Note.Text := 'Есть станции без свежих данных';")
    replace("  if UiDashboardFresh[0] then\n    UiOverviewUpdated.Text := 'Счётчик: ' + IntToStr(Round(Now * 86400.0 - UiLastProgress[0])) + ' с';",
            "  if UiDashboardFresh[0] then\n  begin\n"
            "    UiOverviewUpdated.Text := 'Счётчик: ' + IntToStr(Round(Now * 86400.0 - UiLastProgress[0])) + ' с';\n"
            "    UiCardConnectionText.Text := 'Счётчик ПЛК обновлялся ' + IntToStr(Round(Now * 86400.0 - UiLastProgress[0])) + ' с назад. Подробности — вкладка «Диагностика».';\n"
            "  end;")
    replace("    if UiDashboardFault[0] then UiOverviewPumpInfo.Text := '1: ошибка; 2-4: н/д'\n"
            "    else UiOverviewPumpInfo.Text := '1: код 0; 2-4: н/д';\n  end;",
            "    if UiDashboardFault[0] then UiOverviewPumpInfo.Text := '1: ошибка; 2-4: н/д'\n"
            "    else UiOverviewPumpInfo.Text := '1: код 0; 2-4: н/д';\n"
            "    if UiDashboardFault[0] then UiOverviewPumpStatus0.Text := 'Ошибка ПЧ: ' + IntToStr(UiDashboardFaultCode[0])\n"
            "    else UiOverviewPumpStatus0.Text := 'Код ПЧ: 0';\n"
            "    UiCardEventText.Text := 'Текущий код ПЧ 1: ' + IntToStr(UiDashboardFaultCode[0]) + '. История — вкладка «Аварии».';\n"
            "  end;\n"
            "  UiOverviewPumpStatus1.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus2.Text := 'Нет данных';\n"
            "  UiOverviewPumpStatus3.Text := 'Нет данных';\n"
            "  UiPumpState0.Text := 'Рабочий статус: нет данных';\n"
            "  UiPumpState1.Text := 'Рабочий статус: нет данных';\n"
            "  UiPumpState2.Text := 'Рабочий статус: нет данных';\n"
            "  UiPumpState3.Text := 'Рабочий статус: нет данных';")
    if re.search(r'\.Value\s*:=|SetVariableValue|AddActionMessage', text):
        raise ValueError('Station card module must remain read-only')
    return text
