#!/usr/bin/env python3
"""Fill existing native7 message vectors, retaining native headers/settings.

Do not replace alarm groups, their names, catalog, IDs or opaque metadata.
Use the operator-reopened seven-group project as the authoritative base.
The optional messages-only mode isolates text filling from UI changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_native_merge_r16 import ui_edits,macro_mirrors,widget,properties,NEW_BUTTONS,LOGO_TARGET
from prepare_alarm_open_differential import replace_blocks
from skm_alarm_catalog import Reader,validate_alarm_catalog,validate_alarm_identities,word_bit_semantics
from skm_page_storage import read_page_storage
from repair_skm_section_index import read_directory

SOURCE_SHA='1c48a69e9c63e1f2787d78fb286d04ea3ae04a7b75f304504d75609c28367b8b'
DONOR_SHA='2fe47083c0fbbb2fc9d31342c1ab76d3b220c81afa0f60c61d1ea4eed2c9676e'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def messages_span(raw,group):
    reader=Reader(raw,group['keyboardEnd'])
    for _ in range(2):reader.take(reader.count())
    start=reader.position;languages=reader.count(32)
    for _ in range(languages):
        count=reader.count()
        if count!=group['size']:raise ValueError('Message count differs from native group size')
        for _ in range(count):reader.string()
    return start,reader.position


def prepare(source,donor,messages_only=False,logo_target=LOGO_TARGET):
    source,donor=Path(source),Path(donor);raw=source.read_bytes();full=donor.read_bytes()
    if len(raw)!=1463855 or sha(raw)!=SOURCE_SHA:raise ValueError('Use exact operator-saved/reopened C_native_7groups.skm')
    if len(full)!=1480015 or sha(full)!=DONOR_SHA:raise ValueError('Use exact r15f only as prepared-message donor')
    if not logo_target.lower().endswith(('.jpg','.jpeg','.png')) or '\0' in logo_target:raise ValueError('Invalid logo reference')
    logo_target=logo_target.replace('\\','/')
    read_page_storage(raw);native=validate_alarm_catalog(raw);target=validate_alarm_catalog(full)
    if native['groupCount']!=7 or target['groupCount']!=7:raise ValueError('Seven existing native groups required')
    validate_alarm_identities(raw);edits=[]
    expected=[('R2550',25),('R3056',80),('R3071',1),('R3061',80),('R3072',1),('R3066',80),('R3073',1)]
    for index,(a,b) in enumerate(zip(native['definitions']['groups'],target['definitions']['groups'])):
        if (a['address'],a['size'])!=expected[index]:raise ValueError('Native group address/size differs')
        for key in ('address','size','offset','flags','protocol','number','prefix','wordType','vectors','keys'):
            if a[key]!=b[key]:raise ValueError('Native/donor group schema differs: '+key)
        if index==0:
            if raw[a['start']:a['end']]!=full[b['start']:b['end']]:raise ValueError('Original station group differs')
            continue
        start,end=messages_span(raw,a);first,last=messages_span(full,b)
        edits.append((start,raw[start:end],full[first:last]))
    if not messages_only:edits.extend(ui_edits(raw,logo_target))
    result=replace_blocks(raw,edits);after=validate_alarm_catalog(result)
    if after['names']!=native['names'] or validate_alarm_identities(result)!=list(range(7)):
        raise ValueError('Native group names/identities changed')
    for a,b in zip(native['definitions']['groups'],after['definitions']['groups']):
        first,last=messages_span(raw,a);start,end=messages_span(result,b)
        if raw[a['start']:first]!=result[b['start']:start] or raw[last:a['end']]!=result[end:b['end']]:
            raise ValueError('Native alarm fields outside messages changed')
    a,b=native['directory'],after['directory']
    if raw[a['start']:a['end']]!=result[b['start']:b['end']]:raise ValueError('Native catalog changed')
    a,b=target['definitions'],after['definitions']
    if word_bit_semantics(full[a['start']:a['end']])!=word_bit_semantics(result[b['start']:b['end']]):
        raise ValueError('Prepared word/bit/messages changed')
    before_dir,after_dir=read_directory(raw),read_directory(result)
    for i in range(22):
        if raw[before_dir['entries'][i]:before_dir['entries'][i+1]]!=result[after_dir['entries'][i]:after_dir['entries'][i+1]]:
            raise ValueError('Native opaque settings changed: '+str(i))
    if macro_mirrors(result)!=macro_mirrors(raw):raise ValueError('Native C changed')
    read_page_storage(result)
    if not messages_only:
        for identity in ('SB6010','SB24002')+NEW_BUTTONS:
            _,block=widget(result,identity);v=properties(block,identity)[2]
            if any(v[i]!=str(int(v[56][6:])-1) for i in (48,49,57,60)):
                raise ValueError('Navigation fields differ')
    if source.read_bytes()!=raw or donor.read_bytes()!=full:raise ValueError('Input changed')
    return result,dict(kind='MESSAGES-ONLY DIAGNOSTIC' if messages_only else 'FULL native7 r17 candidate',
        sourceBytes=len(raw),sourceSHA256=sha(raw),messageDonorSHA256=sha(full),candidateBytes=len(result),candidateSHA256=sha(result),
        existingNativeGroups=7,messageVectorsUpdated=6,alarmBitMappings=268,nativeNamesCatalogHeadersAndFlagsPreserved=True,
        allNativeOpaqueSettingsPreserved=True,opaqueSection16FromNative7=True,nativeLayoutAndCPreserved=True,
        completeInversePreservation=True,allNavigationMirrorsUpdated=not messages_only,
        logoReference='native source preserved' if messages_only else logo_target,
        nativeLoadingSaverSettingsConfigured=False,PLCChanged=False,nativeOpenObserved=False,nativeCompileObserved=False,hardwareActions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--messages-only',action='store_true')
    parser.add_argument('--logo-target',default=LOGO_TARGET)
    target=parser.add_mutually_exclusive_group(required=True);target.add_argument('--out',type=Path);target.add_argument('--check',type=Path)
    args=parser.parse_args();candidate=args.out or args.check;paths=(args.source,args.donor,candidate,args.report)
    if (len({p.resolve() for p in paths})!=4 or any(p.is_symlink() for p in paths)
            or args.report.exists() or (args.out and candidate.exists())):
        raise ValueError('Distinct regular paths and NEW output/report required')
    raw,report=prepare(args.source,args.donor,args.messages_only,args.logo_target)
    if args.check:
        if candidate.read_bytes()!=raw:raise ValueError('Candidate differs from native7 message-only-field merge')
    else:
        with candidate.open('xb') as stream:stream.write(raw)
    with args.report.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('PASS' if args.check else 'Created',candidate.resolve(),len(raw),sha(raw),'Native acceptance pending')


if __name__=='__main__':main()
