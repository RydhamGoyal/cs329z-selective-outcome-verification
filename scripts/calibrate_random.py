"""Derive the random checkpoint probability from development risk traces only."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('traces',nargs='+',type=Path)
a=p.parse_args()
writes=checks=0
for path in a.traces:
    d=json.loads(path.read_text())
    if d.get('suite')!='dev' or d.get('policy')!='risk':
        raise SystemExit(f'{path}: calibration requires development risk traces')
    for e in d['events']:
        if e['mutating']:
            writes+=1; checks+=bool(e.get('checkpoint'))
if not writes: raise SystemExit('No state-changing actions in calibration traces')
print(f'{checks/writes:.6f}')
