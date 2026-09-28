"""FlowTape command line entry point for validation and playback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import schema
from .browser import open_edge
from .errors import FlowTapeError
from .player import Player
from .persistence import check_recovery, recover_package


def package(path: str):
    scenario_path = Path(path)
    if scenario_path.is_dir():
        scenario_path = scenario_path / "scenario.yaml"
    check_recovery(scenario_path)
    files=[scenario_path,scenario_path.with_name('elements.yaml')]
    def state():
        return tuple((p.stat().st_mtime_ns,p.stat().st_size,p.stat().st_ino) if p.exists() else None for p in files)
    before=state()
    scenario = schema.scenario(schema.load_yaml(scenario_path))
    registry = schema.elements(schema.load_yaml(scenario_path.with_name("elements.yaml")))
    check_recovery(scenario_path)
    if before!=state():raise FlowTapeError('package changed while loading; reload a stable scenario/registry pair')
    schema.validate_package(scenario, registry)
    return scenario, registry


def main(argv=None):
    parser = argparse.ArgumentParser(prog="flowtape")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate scenario and registry YAML")
    validate.add_argument("scenario")
    run = sub.add_parser("run", help="Run scenario in Microsoft Edge")
    run.add_argument("scenario")
    run.add_argument("--config", required=True)
    run.add_argument("--headless", action="store_true")
    ui = sub.add_parser("ui", help="Open the PySide6 Recorder and Scenario Editor")
    ui.add_argument("scenario")
    ui.add_argument("--config", required=True)
    recover=sub.add_parser('recover',help='Explicitly recover an interrupted scenario/registry save')
    recover.add_argument('scenario')
    recover.add_argument('--choice',choices=['rollback','complete'],required=True)
    doctor=sub.add_parser('doctor',help='Verify the configured Edge driver and Recorder capture without accessing external sites')
    doctor.add_argument('--config',required=True)
    doctor.add_argument('--headless',action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command=='doctor':
            from .browser import Resolver
            from .recorder import RecorderTransport, propose_target
            config=schema.config(schema.load_yaml(args.config),args.config)
            driver=open_edge(config,headless=args.headless)
            transport=RecorderTransport(driver)
            try:
                transport.inject('observe')
                driver.get('data:text/html,<button id="flowtape-test">FlowTape diagnostic</button>')
                transport.inject('pick')
                driver.find_element('id','flowtape-test').click()
                operations=transport.stop()
                operation=next((item for item in operations if item.action=='pick'),None)
                if operation is None:raise FlowTapeError('Recorder did not return the diagnostic selection')
                definition=propose_target(operation.snapshot,resolver=Resolver(driver,{'version':1,'pages':{}}),
                                          context=operation.context,document_id=operation.document_id,element_ref=operation.element_ref)
                if not definition['locate']:raise FlowTapeError('Recorder could not reproduce its captured diagnostic target')
                print(json.dumps({'browser':driver.capabilities.get('browserVersion'),'protocol':1,'capture_verified':True},ensure_ascii=False))
            finally:
                transport.close()
                driver.quit()
            return 0
        if args.command=='recover':
            source=Path(args.scenario)
            if source.is_dir():source/='scenario.yaml'
            recover_package(source,args.choice)
            print('recovered')
            return 0
        if args.command == 'ui':
            from .ui import launch
            return launch(args.scenario,args.config)
        scenario, registry = package(args.scenario)
        if args.command == "validate":
            print("valid")
            return 0
        config = schema.config(schema.load_yaml(args.config), args.config)
        credentials_path = Path(config["credentials"]["path"])
        credentials = schema.credentials(schema.load_yaml(credentials_path)) if credentials_path.exists() else None
        driver = open_edge(config, headless=args.headless)
        try:
            player=Player(driver, scenario, registry, config, credentials)
            player.run()
            if player.log.error:print(player.log.error,file=sys.stderr)
        finally:
            driver.quit()
        print("completed")
        return 0
    except FlowTapeError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
