#!/usr/bin/env python3
"""Check the offline pressure candidate and execute its small native subset.

The isolated component interpreter checks compiled words and the existing
four RUN-output networks. It is NOT a PLC simulator, native F8 or equipment
acceptance. The vendor formatter is separately hash checked and isolated.
"""
import argparse
import json
from pathlib import Path
import struct

from build_high_pressure_pdw_candidate import (
    ANCHOR, MARKER, ORIGINAL, SOURCE_SHA, build_candidate, model_fields, sha, write_new)
from build_setpoint_feedback_pdw_01 import layout
from check_native_drive_edit_02 import unpack


def signed(v):
    v &= 65535
    return v - 65536 if v & 32768 else v


class Component:
    def __init__(self, configured=True):
        self.r = {2868: 200, 2869: 200, 2871: 0, 2874: MARKER if configured else 0}
        self.bits = {}

    def contact(self, v):
        if v >= 0x810:
            return ('M', v - 0x810)
        if v >= 0x100:
            return ('Y', v - 0x100)
        return ('X', v)

    def register(self, address):
        if address < 0x0a00 or address >= 0x2800 or address % 2:
            raise ValueError('Unexpected component register')
        return (address - 0x0a00) // 2

    def execute(self, code):
        w = list(struct.unpack('>' + 'H' * (len(code)//2), code))
        stack = []
        temporary = {}
        i = 0
        while i < len(w):
            op = w[i]
            if op in (0xf47f, 0xf67f):
                descriptor, a, b = w[i+1:i+4]
                a = signed(self.r.get(self.register(a), 0))
                b = signed(b if op == 0xf67f else self.r.get(self.register(b), 0))
                if 0x15 <= descriptor <= 0x18:
                    mode, relation = 'ORG', descriptor - 0x15
                elif 0x21 <= descriptor <= 0x24:
                    mode, relation = 'AND', descriptor - 0x21
                else:
                    raise ValueError('Unsupported comparison branch')
                value = (a == b, a > b, a < b, a != b)[relation]
                if mode == 'ORG':
                    stack = [value]
                else:
                    stack[-1] = stack[-1] and value
                i += 4
            elif op in (0xf4ac, 0xf5ac):
                source, destination = w[i+1:i+3]
                if stack[-1]:
                    self.r[self.register(destination)] = (source if op == 0xf5ac else self.r.get(self.register(source), 0)) & 65535
                i += 3
            elif op == 0xf462:
                a, b, destination = w[i+1:i+4]
                carry = stack.pop()
                assert carry is False, 'Only reviewed OPEN carry supported'
                if stack[-1]:
                    self.r[self.register(destination)] = (self.r.get(self.register(a),0) + self.r.get(self.register(b),0)) & 65535
                i += 4
            elif op == 0x4fe8:
                stack = [True]; i += 1
            elif op == 0x7fe8:
                stack.append(False); i += 1
            elif op == 0xc400:
                temporary[0] = bool(stack[-1]); i += 1
            elif op == 0x6400:
                stack.append(temporary[0]); i += 1
            elif op == 0x9fe7:
                stack[-1] = False; i += 1
            elif op in (0x8fe7, 0x8fe8, 0x8fe9, 0x8feb):
                stack[-1] = bool(stack[-1]); i += 1
            elif op == 0xe200 or op & 0xff00 == 0xe400:
                right, left = stack.pop(), stack.pop()
                stack.append(left and right if op == 0xe200 else left or right)
                i += 1
            elif op & 0xf000 in (0x4000, 0x5000, 0x6000, 0x8000, 0x9000, 0xa000, 0xc000):
                mode, address = op & 0xf000, op & 0x0fff
                key = self.contact(address)
                value = bool(self.bits.get(key, False))
                if mode in (0x5000, 0x9000): value = not value
                if mode in (0x4000,0x5000): stack = [value]
                elif mode == 0x6000: stack.append(value)
                elif mode in (0x8000,0x9000): stack[-1] = stack[-1] and value
                elif mode == 0xa000: stack[-1] = stack[-1] or value
                else: self.bits[key] = bool(stack[-1])
                i += 1
            else:
                raise ValueError(f'Unsupported compiled component opcode {op:04x}')

    def cycle(self, codes, pressure, setpoint=500, valid=True, boot=False, auto=True, outputs_on=()):
        self.r[101], self.r[110] = pressure, setpoint
        self.bits[('M',102)] = valid
        self.bits[('M',1924)] = boot
        self.bits[('X',8)], self.bits[('X',9)] = auto, False
        for n in range(1,5): self.bits[('Y',n)] = n in outputs_on
        for code in codes: self.execute(code)
        return self.r[2871], self.r[2878]


def validate(source, candidate, vendor_dll=None):
    original_raw = Path(source).read_bytes()
    assert sha(original_raw) == SOURCE_SHA
    expected, report, plan = build_candidate(source)
    actual_raw = Path(candidate).read_bytes()
    assert actual_raw == expected
    a, b = layout(original_raw), layout(actual_raw)
    old, new = unpack(Path(source)), unpack(Path(candidate))
    assert model_fields(original_raw)[0] == 'FBs-32MC'
    assert model_fields(actual_raw)[0] == 'FBs-24MC'
    assert old['tables'] == new['tables'] and len(new['tables']) == 9
    assert a['payload'] == b['payload']
    pc, delta = report['insertionPC'], report['insertedProgramBytes']
    normalized = bytearray(b['image'][:pc] + b['image'][pc+delta:] + b'\xff'*delta)
    normalized[pc:pc+len(ORIGINAL)] = ORIGINAL
    assert normalized[512:] == a['image'][512:]
    added_labels = {r['label'] for r in plan}
    preserved = [(p-(delta if p>=pc else 0),label) for p,label in new['rungs'] if label not in added_labels]
    assert preserved == old['rungs']
    assert len(new['rungs']) == len(old['rungs']) + len(plan)
    codes = [bytes.fromhex(r['expectedCodeHex']) for r in plan] + [bytes.fromhex(report['replacementCodeHex'])]

    formatted, graphs, rejected_regressions = [], [], []
    if vendor_dll:
        from render_fatek_network_01 import render
        from check_fatek_network_graph import GraphChecker
        graph = GraphChecker(vendor_dll)
        # These exact malformed r1 patterns passed mnemonic/behavior tests.
        # Structural regression checks must reject them before release.
        bad = {
            'r1_unrepresentable_arithmetic_carry': bytes.fromhex('4fe87fe8f4620adc2068206c'),
            'r1_unrepresentable_long_condition': bytes.fromhex(
                '48769f94f67f00220adc0009f67f00230adc04b0f67f0021207469e9'
                'f67f002220680009f67f0023206801f5f47f00230aca0adcf5ac0000206e'),
        }
        for label, code in bad.items():
            diagnosis = graph.inspect(code)
            assert diagnosis['nodeError'] or diagnosis['errorFlag'],label
            rejected_regressions.append({'label':label,'error':diagnosis['nodeError']})
        for code in (bytes.fromhex('4fe8f5ac00012044'),bytes.fromhex('f67f00170aca04b0c8ed')):
            graph.require(code)
        for row, code in zip(plan,codes):
            text = render(code,Path(vendor_dll))
            assert 'FUN' in text and ('MOV' in text or '_.(+)' in text)
            formatted.append({'label':row['label'],'mnemonics':text})
            graphs.append({'label':row['label'],**graph.require(code)})
        anchor = render(codes[-1],Path(vendor_dll))
        assert 'R2878' in anchor and 'M221' in anchor
        graphs.append({'label':ANCHOR,**graph.require(codes[-1])})

    cases = []
    def check(name, observed, expected_value):
        assert observed == expected_value,(name,observed,expected_value)
        cases.append(name)
    state = Component()
    check('below threshold, initially clear',state.cycle(codes,500),(0,1))
    check('equality with SP+delta does not trip',state.cycle(codes,700),(0,1))
    check('strictly above SP+delta trips',state.cycle(codes,701),(1,0))
    check('deadband holds trip',state.cycle(codes,650),(1,0))
    check('one unit above SP holds trip',state.cycle(codes,501),(1,0))
    check('equality with SP automatically resets',state.cycle(codes,500),(0,1))
    check('new excursion trips again',state.cycle(codes,701),(1,0))
    check('invalid measurement never clears trip',state.cycle(codes,450,valid=False),(1,0))
    check('fresh measurement below SP resets',state.cycle(codes,450),(0,1))
    check('legacy absolute12bar ceiling retained',state.cycle(codes,1200,setpoint=1190),(1,0))
    check('absolute trip also resets at SP',state.cycle(codes,1190,setpoint=1190),(0,1))

    state = Component(configured=False)
    state.r[2877] = 1
    check('boot cannot permit output',state.cycle(codes,450,boot=True,valid=False),(0,0))
    check('first use default2bar and command dropped',(state.r[2868],state.r[2877]),(200,0))
    state.r[2869],state.r[2877] = 100,1
    state.cycle(codes,450,auto=False)
    check('STOP explicitly applies draft',(state.r[2868],state.r[2875],state.r[2876],state.r[2877]),(100,2,1,0))
    check('changed margin used for threshold',state.cycle(codes,601),(1,0))
    for draft in (0,9,501,65535):
        state.r[2869],state.r[2877] = draft,1
        state.cycle(codes,450,auto=False)
        check('invalid draft rejected '+str(draft),(state.r[2868],state.r[2875],state.r[2877]),(100,4,0))
    state.r[2869],state.r[2877] = 200,1
    state.cycle(codes,450,auto=True)
    check('AUTO rejects settings application',(state.r[2868],state.r[2875],state.r[2877]),(100,3,0))
    state.r[2877] = 1
    state.cycle(codes,450,auto=False,outputs_on=(1,))
    check('RUN output rejects settings application',(state.r[2868],state.r[2875]),(100,3))
    state.r[2877] = 2
    state.cycle(codes,450,auto=False)
    check('unknown command rejected and consumed',(state.r[2875],state.r[2877]),(5,0))
    state.r[2868] = 0
    check('corrupt confirmed margin inhibits output',state.cycle(codes,450),(0,0))

    # Existing native RUN rungs remain byte-for-byte unchanged. Execute
    # their boolean subset with both demand branches, testing the common gate.
    output_codes=[]
    for n in range(1,5):
        prefix=f'90.0{n+1} | PUMP{n}_RUN_OUTPUT'
        found=[(i,p) for i,(p,label) in enumerate(new['rungs']) if label==prefix]
        i,p=next((i,p) for i,p in found if b['image'][p:p+2] != bytes.fromhex('5feb'))
        end=new['rungs'][i+1][0]
        output_codes.append(b['image'][p:end])
    for auto in (False,True):
        for permit in (False,True):
            s=Component();s.bits[('M',221)]=permit;s.bits[('M',320)]=auto;s.bits[('M',321)]=not auto
            s.bits[('M',740)]=True;s.r.update({2499:27110,2329:27110})
            for n in range(4):
                for group in (200,360,1630,1200,610):s.bits[('M',group+n)]=True
            for code in output_codes:s.execute(code)
            check(f'all4 native RUN outputs gated, AUTO={auto},permit={permit}',
                  [s.bits[('Y',n)] for n in range(1,5)],[permit]*4)
    assert Path(source).read_bytes() == original_raw
    return dict(candidateSHA256=sha(actual_raw), checks=cases, passed=len(cases),
                originalNetworksPreservedExceptSafetyPermit=True, tablesPreserved=9,
                decodedDataFramePreserved=True, sourceUnchanged=True,
                vendorFormattedNetworks=len(formatted), componentInterpreter=True,
                vendorGraphNetworks=len(graphs), vendorGraphRoundTrips=all(g['roundTrip'] for g in graphs) if graphs else False,
                rejectedR1Regressions=rejected_regressions, graphEvidence=graphs,
                nativeF8=False, nativePLCExecution=False, equipmentActions=0,
                pumpCountImplemented=False, HMIFileModified=False,
                formatterEvidence=formatted)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--candidate',required=True,type=Path)
    p.add_argument('--vendor-dll',type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    if a.out.exists() or a.out.is_symlink() or a.out.resolve() in (a.source.resolve(),a.candidate.resolve()):
        raise ValueError('Report must be a new distinct file')
    result=validate(a.source,a.candidate,a.vendor_dll)
    write_new(a.out,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print('PASS:',result['passed'],'component cases;',result['vendorFormattedNetworks'],'vendor-formatted networks;',result['vendorGraphNetworks'],'graph round trips; original tables/data preserved.')
    print('Not native F8, full PLC simulation or hardware validation.')


if __name__=='__main__':main()
