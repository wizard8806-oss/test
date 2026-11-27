"""Read-only acceptance of the physically uploaded TEST_ONLY historian group."""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sqlite3


def review(file):
    with sqlite3.connect(Path(file).resolve().as_uri()+'?mode=ro',uri=True) as db:
        assert db.execute('pragma integrity_check').fetchone()==('ok',)
        rows=[(datetime.fromisoformat(v[0]),*map(int,v[1:])) for v in db.execute('select * from hisdata1 order by logtime')]
    assert len(rows)>100 and max(v[25] for v in rows)!=min(v[25] for v in rows)
    # Source and four display words are read through a sample group. At a
    # stimulus transition the native macro's input batch lags by one tick.
    # Test the stable interval; the first incomplete segment is skipped.
    cases=defaultdict(list)
    previous=None
    for row in rows:
        case=row[26]
        if case!=previous:
            entered=row[0]
            previous=case
        if (row[0]-entered).total_seconds()>1.4:
            cases[case].append(row)
    for i in range(4):
        select=cases[i]
        assert {v[i+1] for v in select}=={1,2,3,4}
        assert all(v[j+1]==0 for v in select for j in range(4) if j!=i)
    assert all({v[j+1] for v in cases[4]}=={1,2,3,4} for j in range(4))
    assert all(v[4]==0 and v[30]==0 for v in cases[5])
    assert all({v[j+1] for v in cases[5]}=={1,2,3,4} for j in range(3))
    for case in (6,7,8):
        assert all(not any(v[1:5]) for v in cases[case])
    assert all({v[j+1] for v in cases[9]}=={1,2,3,4} for j in range(4))
    assert all(v[4]==0 and not (v[17] or v[18]) for v in cases[10])
    assert any(not any(v[1:5]) for v in cases[11])
    assert any(v[20:24]==(123,236,349,462) for v in cases[4])
    complete=set();seq=[]
    for v in rows:
        action,target=v[6],v[7]
        good=v[17]==target and v[18]==v[8] and v[18]>0 and v[11]==12 and v[12]==0
        if not good or action not in (1,2):
            seq=[]
            continue
        token=(action,target,v[18])
        if not seq or token!=seq[-1]:
            if not seq or token[:2]!=seq[-1][:2] or token[2]!=seq[-1][2]-1:
                seq=[]
            seq.append(token)
            if len(seq)==12 and seq[0][2]==12:
                complete.add((action,target))
    assert complete=={(a,i) for a in (1,2) for i in range(1,5)},complete
    assert any(v[6]==0 and (v[17],v[18])==(0,0) for v in rows)
    return dict(rows=len(rows),start=rows[0][0].isoformat(),end=rows[-1][0].isoformat(),
                heartbeatRange=[min(v[25] for v in rows),max(v[25] for v in rows)],
                stableSamples={i:len(v) for i,v in sorted(cases.items())},
                consecutiveCountdowns=sorted(complete),
                singlePumpFrames=[[sorted({r[j+1] for r in cases[i]}) for j in range(4)] for i in range(4)])


if __name__=='__main__':
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upload',type=Path)
    print(json.dumps(review(parser.parse_args().upload),indent=2))
