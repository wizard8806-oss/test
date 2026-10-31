#!/usr/bin/env python3
"""Index a user-supplied MBP without running scripts or dropping duplicate
node/tag/group members. The report excludes credentials and script bodies.
"""
import argparse,hashlib,json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

SAFE=('Address','Region','Type','TypeInDevice','Access','Enabled','TegCalculation','KoffA','KoffB','UBSDevice')

def preserve_members(pairs):
 grouped=defaultdict(list)
 for key,value in pairs:grouped[key].append(value)
 return {key:values[0] if len(values)==1 else values for key,values in grouped.items()}

def review(path):
 source=Path(path);raw=source.read_bytes()
 with ZipFile(source) as archive:
  configs=[i for i in archive.infolist() if i.filename.lower().endswith('.mbc')]
  if len(configs)!=1 or configs[0].file_size>4*1024*1024:raise ValueError('Expected one bounded MBC configuration')
  body=archive.read(configs[0])
 try:text=body.decode('utf-8-sig')
 except UnicodeDecodeError:text=body.decode('cp1251')
 root=json.loads(text,object_pairs_hook=preserve_members);tags=[]
 def walk(node,path):
  if isinstance(node,list):
   for child in node:walk(child,path)
  elif isinstance(node,dict):
   name=node.get('NameInTree','');current=path+([name] if name else [])
   if node.get('Category')=='Teg':tags.append(dict(path='.'.join(current),**{k:node[k] for k in SAFE if k in node}))
   for value in node.values():
    if isinstance(value,(dict,list)):walk(value,current)
 walk(root,[])
 return dict(source_name=source.name,source_sha256=hashlib.sha256(raw).hexdigest(),
  scope='Configuration only; no live values, PLC map verification or device model inferred.',
  total_tags=len(tags),pressure_tags=[t for t in tags if t['path'].endswith('.Давление')],
  fault_tags=[t for t in tags if t['path'].endswith('.Авария')],
  codex_tags=[t for t in tags if '.codex.' in t['path']],
  warnings=['Old object addresses are not a verified FATEK/codex export map.','Coefficients are copied as configuration fields; engineering units and active scaling require verification.','All repeated node/tag/group members preserved; no scripts executed.'])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--out',required=True);args=parser.parse_args()
 report=review(args.source);Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('Indexed',report['total_tags'],'tags;',len(report['pressure_tags']),'pressure,',len(report['fault_tags']),'fault;',len(report['codex_tags']),'codex tags.')

if __name__=='__main__':main()
