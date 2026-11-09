"""Recompute saved checkpoint verdicts from visible dialogue and readback only."""
import argparse
import json
from pathlib import Path
from selective_verify.core import verdict

def audit(trace):
    events=trace.get('events',[])
    users=[];tool_index=0;mismatches=[]
    for message in trace.get('messages',[]):
        if message.get('role')=='user' and message.get('content'):
            users.append(message['content'])
        if message.get('role')=='tool':
            if tool_index>=len(events):break
            event=events[tool_index];tool_index+=1
            old=event.get('verification')
            if old:
                intent=('\n'.join(m['content'] for m in trace.get('messages',[]) if m.get('role')=='user' and m.get('content')) if old.get('timing')=='final-only' else '\n'.join(users))
                current,reason=verdict(event['tool'],event['arguments'],old.get('evidence'),intent,event.get('error',False))
                if current!=old['verdict']:
                    mismatches.append({'tool_index':tool_index-1,'tool':event['tool'],
                                       'saved':old['verdict'],'recomputed':current,'reason':reason})
    return mismatches

def main():
    p=argparse.ArgumentParser();p.add_argument('paths',nargs='+',type=Path);a=p.parse_args()
    for path in a.paths:
        trace=json.loads(path.read_text());issues=audit(trace)
        print(path, 'MISMATCH' if issues else 'consistent',issues)
if __name__=='__main__':main()
