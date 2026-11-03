#!/usr/bin/env python3
"""Read-only SCADA11 page/event audit. Stdlib only; safe with Python -I -B.

Reads Pages.spg and Scripts/Scripts.ssc, not profiles, credentials or Variables.
Exports identifiers, geometry, metadata and code hashes; never script bodies.
Static binding agreement does not establish actual Client event execution.
"""
import argparse
import datetime
import hashlib
import json
import math
import re
import struct
from pathlib import Path


class Reader:
    def __init__(self, raw):
        self.raw, self.pos = raw, 0

    def take(self, count):
        if count < 0 or self.pos + count > len(self.raw):
            raise ValueError('Truncated native file')
        result = self.raw[self.pos:self.pos + count]
        self.pos += count
        return result

    def number(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def count(self, limit):
        count = self.number('I')
        if count > limit:
            raise ValueError('Native collection exceeds audit limit')
        return count

    def text(self, wide=False):
        count = self.count(131072)
        return self.take(count * (2 if wide else 1)).decode('utf-16le' if wide else 'utf8')

    def done(self):
        if self.pos != len(self.raw):
            raise ValueError('Unsupported trailing native data')


def pages(raw):
    r = Reader(raw)
    next_id, count = r.number('q'), r.count(128)
    result, names, page_ids = [], set(), set()
    for _ in range(count):
        page = r.text()
        r.text(True)
        page_id = r.number('q')
        if page_id in page_ids:
            raise ValueError('Duplicate page ID')
        page_ids.add(page_id)
        for fmt in ['I', 'q', 'q', 'q', 'I', 'I', 'B', 'I']:
            r.number(fmt)
        for _ in range(r.count(128)):
            r.text(); r.text(True)
            for fmt in ['q', 'I', 'I']:
                r.number(fmt)
            r.text()
            for fmt in ['I', 'q', 'q', 'I', 'I', 'B', 'I']:
                r.number(fmt)
            for _ in range(r.count(10000)):
                if r.number('H') != 4:
                    raise ValueError('Audit supports the reviewed Text-only SCADA11 pages')
                name = r.text()
                if name in names:
                    raise ValueError('Duplicate control name')
                names.add(name)
                body = r.take(141)
                if body[49:54] != bytes(5):
                    raise ValueError('Nonempty hint/unknown object layout requires a native review')
                rect = struct.unpack_from('<4f', body, 8)
                if not all(math.isfinite(v) for v in rect) or min(rect[2:]) <= 0:
                    raise ValueError('Invalid control geometry')
                r.text(True); r.take(9)
                result.append(dict(page=page, name=name, uid=struct.unpack_from('<I', body, 107)[0],
                                   rect=list(rect), z=struct.unpack_from('<I', body, 54)[0],
                                   fontType=body[31],fontScale=struct.unpack_from('<f',body,32)[0],
                                   onClick=struct.unpack_from('<q', body, 75)[0],
                                   rawControlFlags=body[24:32].hex()))
    r.done()
    if not page_ids or next_id <= max(page_ids):
        raise ValueError('Invalid next-page counter')
    return result, page_ids


def scripts(raw):
    r = Reader(raw)
    next_id = r.number('q')
    r.take(r.count(1024))
    if r.number('I') != 0:
        raise ValueError('Nested script folders require an extended audit')
    rows, names = {}, set()
    for _ in range(r.count(2048)):
        id_, name, meta = r.number('q'), r.text(True), r.take(17)
        if id_ in rows or name in names:
            raise ValueError('Duplicate script name/ID')
        names.add(name)
        body = '\n'.join(r.text(True) for _ in range(r.count(8192))).strip()
        body = re.sub(r'\Aunit\s+' + re.escape(name) + r'\s*;\s*', '', body, flags=re.I).strip()
        rows[id_] = dict(name=name, meta=meta, body=body)
    r.done()
    if not rows or next_id <= max(rows):
        raise ValueError('Invalid next-script counter')
    return rows


def expected_script(name):
    if name in ['ProcessSpMinus', 'ProcessSpPlus', 'ProcessSpApply', 'ProcessSpCancel']:
        return name + '_OnClick'
    if name == 'UiMainWindow':
        return 'UiMainOpenWindow_OnClick'
    m = re.fullmatch(r'UiRow(\d+)(Name|Open)', name)
    if m:
        return ('UiOpenStation' if m[2] == 'Name' else 'UiPopup') + m[1] + '_OnClick'
    m = re.fullmatch(r'UiStationTrends(\d+)', name)
    if m:
        return 'UiTrendsStation' + m[1] + '_OnClick'
    if re.fullmatch(r'Ui\w*(?:Nav\d+|Messages\d+|TrendsAll\d+|OverviewNext\d+)', name):
        return name + '_OnClick'
    return None


def public_name(name):
    if re.fullmatch(r'(?:Ui|PageUi|PageProcess|PageDiagnostics|Process|OperatorConsole|StationDiagnostics)\w*', name):
        return name
    return 'other:' + hashlib.sha256(name.encode()).hexdigest()[:12]


def audit(project):
    project = Path(project).resolve()
    raw = {}
    for name in ['Pages.spg', 'Scripts/Scripts.ssc']:
        p = project / name
        if not p.is_file() or p.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Expected a bounded native project file: ' + name)
        raw[name] = p.read_bytes()
    controls, page_ids = pages(raw['Pages.spg'])
    rows = scripts(raw['Scripts/Scripts.ssc'])
    prototype = next((r['meta'] for r in rows.values() if r['name'] == 'ProcessSpPlus_OnClick'), None)
    if prototype is None:
        raise ValueError('Reviewed working OnClick prototype is absent')
    page_names = {c['page'] for c in controls}
    findings, bindings = [], []
    for c in controls:
        expected = expected_script(c['name'])
        if not expected:
            continue
        actual = rows.get(c['onClick'])
        entry = {k: c[k] for k in ['uid', 'rect', 'z', 'onClick', 'rawControlFlags']}
        entry.update(control=public_name(c['name']), page=public_name(c['page']), expectedScript=expected,
                     linkedScript=public_name(actual['name']) if actual else None)
        reasons = []
        if actual is None:
            reasons.append('missing-script')
        else:
            if actual['name'] != expected:
                reasons.append('wrong-script')
            meta, body = actual['meta'], actual['body']
            entry.update(scriptTypeBytes=meta[:2].hex(), enabledByte=meta[6], autoStartByte=meta[8],
                         codeSHA256=hashlib.sha256(body.encode()).hexdigest(),
                         callerGetterCount=len(re.findall(r'\bGetClientName\b', body)))
            if meta[:2] != prototype[:2] or meta[6:9] != prototype[6:9]:
                reasons.append('metadata-differs-from-working-prototype')
            target = re.search(r"UiGoPage\('((?:PageUi|PageProcess|PageDiagnostics)\w*)'", body)
            if target:
                entry['targetPage'] = target[1]
                entry['targetPageExists'] = target[1] in page_names
                if not entry['targetPageExists']:
                    reasons.append('missing-target-page')
            entry['knownNavigationCalls'] = sorted(set(re.findall(
                r'\b(?:UiGoPage|UiOpenWindow|UiOpenTrends|GoToMessagesGroupClient|GoToTrendsClient)\b', body)))
        x, y, w, h = c['rect']; cx, cy = x + w/2, y + h/2
        entry['potentialCoverersAtCenter'] = [public_name(o['name']) for o in controls
            if o['page'] == c['page'] and o['z'] > c['z'] and
            o['rect'][0] <= cx <= o['rect'][0]+o['rect'][2] and
            o['rect'][1] <= cy <= o['rect'][1]+o['rect'][3]]
        entry['staticBindingMatches'] = not reasons
        if reasons:
            findings.append(dict(control=public_name(c['name']), reasons=reasons))
        bindings.append(entry)
    after = {n: hashlib.sha256((project/n).read_bytes()).hexdigest() for n in raw}
    before = {n: hashlib.sha256(b).hexdigest() for n,b in raw.items()}
    if after != before:
        raise ValueError('Project changed during audit; retry from a stable preserved copy')
    return dict(schemaVersion=1, measuredAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                scope='Static native file bindings only; no Client invocation or permissions test',
                fileSHA256=before, pageCount=len(page_ids), textObjects=len(controls),
                scripts=len(rows), buttons=len(bindings), findings=findings, bindings=bindings,
                layoutControls=[dict(control=public_name(c['name']),page=public_name(c['page']),
                    rect=c['rect'],fontType=c['fontType'],fontScale=c['fontScale'])
                    for c in controls if c['name'].endswith(('Background','Brand','Heading')) or
                    c['name'] in ('ProcessTitle','ProcessPressure','ProcessSetpoint')],
                topMarginCandidates=[public_name(c['name']) for c in controls
                    if (c['name'].endswith(('Heading','Brand')) or c['name']=='ProcessTitle') and c['rect'][1]<64],
                sourceUnchanged=True, hardwareCommands=0, runtimeNavigationVerified=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();dest=args.out.resolve();root=args.project.resolve()
    if dest.suffix.lower()!='.json' or dest.is_relative_to(root):
        raise ValueError('Use a new JSON output outside the native project')
    result=audit(root)
    with dest.open('x',encoding='utf8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(dict(buttons=result['buttons'],findings=len(result['findings']),sourceUnchanged=True,runtimeNavigationVerified=False)))
