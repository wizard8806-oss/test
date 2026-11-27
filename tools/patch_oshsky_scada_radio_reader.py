"""Update only the r4 radio status reader in an offline native Scripts.ssc."""
import struct
from validate_radio_install_01 import parse_scripts


def pack(lines):
    chunks=[struct.pack('<I',len(lines))]
    for line in lines:
        encoded=line.encode('utf-16-le')
        chunks.extend([struct.pack('<I',len(encoded)//2),encoded])
    return b''.join(chunks)


def patch(source):
    before=parse_scripts(source)
    row,=[row for row in before if row[1]=='StationRadioDiagnostics']
    old=row[3]
    begin=old.index('  try')
    assert "RadioLines.LoadFromFile(" in old[begin+1] and old[begin+5]=='  end;'
    folder='C:\\ProgramData\\Automatika\\Station50008\\'
    new=old[:begin]+[
        "  if not DirectoryExists(GetUserFilesPath) then",
        "    if not ForceDirectories(GetUserFilesPath) then",
        "    begin RadioUnknown('Не удалось открыть каталог радиодиагностики.'); Exit; end;",
        "  if not CopyFile('"+folder+"radio.txt', GetUserFilesPath + 'radio-snapshot.txt', True) then",
        '  begin',
        "    RadioUnknown('Нет обновления от сборщика радиодиагностики.');",
        '    Exit;',
        '  end;',
        "  if not TextFileOpen('radio-snapshot.txt', '', fomReset, fcpUTF8) then",
        '  begin',
        "    RadioUnknown('Нет обновления от сборщика радиодиагностики.');",
        '    Exit;',
        '  end;',
        '  try',
        '    RadioLines.Clear;',
        '    while (not TextFileEof) and (RadioLines.Count < 11) do',
        '      RadioLines.Add(TextFileReadLn);',
        '  finally',
        '    TextFileClose;',
        '  end;'
    ]+old[begin+6:]
    body=pack(old);assert source.count(body)==1
    target=source.replace(body,pack(new))
    after=parse_scripts(target)
    assert len(before)==len(after) and [(r[0],r[1],r[2]) for r in before]==[(r[0],r[1],r[2]) for r in after]
    assert [(a[1],b[3]) for a,b in zip(before,after) if a!=b]==[(row[1],new)]
    return target
