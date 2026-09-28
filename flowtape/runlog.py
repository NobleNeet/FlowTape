"""Per-run diagnostic logs. Never serialize expanded input or read values."""

import json
from datetime import datetime, timezone
from pathlib import Path


LEVELS={'DEBUG':10,'INFO':20,'WARNING':30,'ERROR':40,'CRITICAL':50}


class RunLog:
    def __init__(self,config,output_manager,credentials):
        self.minimum=LEVELS[config['logging']['level']]
        self.path=Path(config['paths']['logs'])/output_manager.run_dir.parent.name/output_manager.run_dir.name/'run.jsonl'
        self.secrets=sorted({value for group in credentials.values() for value in group.values() if value},key=len,reverse=True)
        self.error=None

    def redact(self,value):
        if isinstance(value,str):
            for secret in self.secrets:value=value.replace(secret,'[REDACTED]')
            return value
        if isinstance(value,dict):return {key:self.redact(item) for key,item in value.items()}
        if isinstance(value,list):return [self.redact(item) for item in value]
        return value

    def write(self,level,event,**data):
        if LEVELS[level]<self.minimum:return
        record={'timestamp':datetime.now(timezone.utc).isoformat(),'level':level,'event':event,**data}
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(self.redact(record),ensure_ascii=False)+'\n')
        except OSError as exc:
            self.error=f'diagnostic log unavailable ({type(exc).__name__})'
