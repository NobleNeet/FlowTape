"""Conservative, transient evidence for explicit username/password pairing."""

import re
from dataclasses import dataclass


@dataclass
class InputEvidence:
    operation: object
    target: str
    value: object


def username_candidate(steps, insertion, evidence, secret_operation):
    if insertion < 1: return None
    node = steps[insertion-1]
    if node.get('action') != 'input' or node.get('enabled',True) is False: return None
    prior = evidence.get(node.get('_meta',{}).get('id'))
    if prior is None or node.get('target') != prior.target or node.get('value') != prior.value: return None
    if isinstance(node.get('value'),str) and '${' in node['value']: return None
    op = prior.operation
    if not op.document_id or op.document_id != secret_operation.document_id: return None
    if op.url != secret_operation.url or op.handle != secret_operation.handle or op.context != secret_operation.context: return None
    snap = op.snapshot or {}
    text = ' '.join(str(v or '') for v in [snap.get('label'),snap.get('name'),prior.target,
                   snap.get('attributes',{}).get('name'),snap.get('attributes',{}).get('id')])
    if snap.get('type') == 'search' or re.search(r'search|query|検索',text,re.I): return None
    autocomplete = snap.get('attributes',{}).get('autocomplete','').split()
    if not (set(autocomplete) & {'username','email'} or re.search(r'username|user[_ -]?id|login|account|email|ユーザー|ログイン|アカウント|メール',text,re.I)):
        return None
    form = lambda snapshot: [r['anchor'] for r in snapshot.get('relations',[]) if r['relation']=='form']
    left,right = form(snap),form(secret_operation.snapshot or {})
    if left and right and left != right: return None
    return node
