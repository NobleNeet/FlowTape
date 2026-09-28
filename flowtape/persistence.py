"""Recoverable two-file saves. Interrupted transactions require explicit recovery."""

import base64
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from .schema import save_yaml
from .errors import FlowTapeError


class PendingSaveRecovery(FlowTapeError):
    pass


class PackageBusy(FlowTapeError):
    pass


@contextmanager
def writer_lock(scenario_path):
    """Kernel-managed lock is released even if a writer process terminates."""
    lock=Path(scenario_path).with_name('.flowtape-save.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as handle:
        if not lock.stat().st_size:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise PackageBusy('another process is saving or recovering this package; retry after it completes') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def journal_path(scenario_path):
    return Path(scenario_path).with_name('.flowtape-save.json')


def check_recovery(scenario_path):
    if journal_path(scenario_path).exists():
        raise PendingSaveRecovery('package save transaction pending; wait for an active writer or explicitly recover an interrupted save')


def _durable_bytes(path, data):
    with Path(path).open('wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _sync_directory(directory):
    if os.name=='nt': return
    descriptor=os.open(directory,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def save_package(scenario_path, scenario, registry):
    with writer_lock(scenario_path):
        _save_package(scenario_path,scenario,registry)


def _save_package(scenario_path, scenario, registry):
    paths = [Path(scenario_path), Path(scenario_path).with_name("elements.yaml")]
    check_recovery(paths[0])
    token = uuid.uuid4().hex
    temporary = [path.with_name(path.name + "." + token + ".tmp") for path in paths]
    originals = [path.read_bytes() if path.exists() else None for path in paths]
    journal=journal_path(paths[0])
    journal_temp=journal.with_name(journal.name+'.'+token+'.tmp')
    replaced = []
    discard_journal=False
    try:
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        for path, data in zip(temporary, (scenario, registry)):
            save_yaml(path, data)
            _durable_bytes(path,path.read_bytes())
        encoded=lambda value: None if value is None else base64.b64encode(value).decode('ascii')
        record={'version':1,'scenario_file':paths[0].name,
                'originals':[encoded(value) for value in originals],
                'staged':[encoded(path.read_bytes()) for path in temporary]}
        _durable_bytes(journal_temp,json.dumps(record).encode('utf-8'))
        os.replace(journal_temp,journal)
        _sync_directory(paths[0].parent)
        for i, (source, destination) in enumerate(zip(temporary, paths)):
            os.replace(source, destination)
            replaced.append(i)
        _sync_directory(paths[0].parent)
        discard_journal=True
    except OSError:
        for i in replaced:
            if originals[i] is None:
                paths[i].unlink(missing_ok=True)
            else:
                _durable_bytes(temporary[i],originals[i])
                os.replace(temporary[i], paths[i])
        _sync_directory(paths[0].parent)
        discard_journal=True
        raise
    finally:
        for path in temporary+[journal_temp]:
            path.unlink(missing_ok=True)
        if discard_journal:
            journal.unlink(missing_ok=True)
            _sync_directory(paths[0].parent)


def recover_package(scenario_path, choice):
    """User-selected rollback/complete; never silently replace authority files."""
    with writer_lock(scenario_path):
        _recover_package(scenario_path,choice)


def _recover_package(scenario_path, choice):
    scenario_path=Path(scenario_path)
    journal=journal_path(scenario_path)
    if choice not in {'rollback','complete'}:
        raise PendingSaveRecovery('recovery choice must be rollback or complete')
    try:
        record=json.loads(journal.read_text(encoding='utf-8'))
        if not isinstance(record,dict) or record.get('version')!=1 or record.get('scenario_file')!=scenario_path.name:
            raise ValueError('journal package mismatch')
        payload=record['originals' if choice=='rollback' else 'staged']
        if not isinstance(payload,list) or len(payload)!=2: raise ValueError('journal payload')
        data=[None if item is None else base64.b64decode(item,validate=True) for item in payload]
        if choice=='complete' and any(item is None for item in data): raise ValueError('missing staged document')
    except (ValueError,KeyError,TypeError,OSError):
        raise PendingSaveRecovery('save journal is unavailable or invalid; authoritative files were not changed') from None
    paths=[scenario_path,scenario_path.with_name('elements.yaml')]
    token=uuid.uuid4().hex
    temporary=[path.with_name(path.name+'.'+token+'.tmp') for path in paths]
    try:
        for path,value in zip(temporary,data):
            if value is not None: _durable_bytes(path,value)
        for source,destination,value in zip(temporary,paths,data):
            if value is None: destination.unlink(missing_ok=True)
            else: os.replace(source,destination)
        _sync_directory(scenario_path.parent)
        journal.unlink()
        _sync_directory(scenario_path.parent)
    except OSError:
        raise PendingSaveRecovery('recovery I/O failure; keep the journal and retry explicit recovery') from None
    finally:
        for path in temporary:path.unlink(missing_ok=True)
