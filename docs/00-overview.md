# FlowTape Overview

Status: initial specification before implementation

## 1. Purpose

FlowTape is a browser-operation recording and playback tool whose primary artifact is a human-readable YAML scenario.

It is intended for users who want to automate browser work without writing Selenium/Python code directly, while still keeping the resulting automation inspectable and editable as a procedure document.

The product is not designed around exposing raw Selenium commands. Its main abstraction is:

```text
human operation
    -> semantic operation step
    -> logical target name
    -> DOM registry resolution
    -> browser execution
```

## 2. Core goals

FlowTape should satisfy all of the following:

1. A user can demonstrate a normal browser workflow and record it.
2. Recorded steps remain readable as a procedure after recording.
3. A scenario can also be written or edited manually.
4. DOM details are separated from scenario logic.
5. Missing DOM bindings can be created interactively instead of requiring hand-written selectors.
6. Conditions and loops can be added after recording by wrapping ranges of existing steps.
7. Playback is conservative: ambiguous target resolution must not silently click the first match.
8. Browser/DOM logic should work similarly across Linux development and Windows 11 + Edge deployment.

## 3. Main artifacts

### 3.1 Scenario YAML

Scenario YAML describes:

- operation order
- action type
- values to enter
- variables
- checks
- conditions
- loops
- logical target names

Example:

```yaml
version: 1

steps:
  - action: open
    url: https://example.com/login

  - action: input
    target: メールアドレス
    value: test@example.com

  - action: input
    target: パスワード
    value: ${PASSWORD}

  - action: click
    target: ログイン
```

The scenario must not normally contain raw CSS/XPath for each step.

### 3.2 DOM registry (`elements.yaml`)

`elements.yaml` maps logical names such as `ログイン` or `プロフィール/保存` to DOM-resolution definitions.

It stores:

- candidate locators
- expected element characteristics
- iframe/shadow context where needed
- limited diagnostic/fingerprint information where useful

It is primarily generated and maintained through Recorder/Picker/Bind operations rather than written from scratch by the user.

### 3.3 Configuration

Environment-specific configuration is external to the packaged executable. It may include browser/driver paths, runtime settings, output locations, timeouts, and similar deployment settings.

The exact config schema is not yet fixed.

## 4. Product components

FlowTape is organized conceptually into:

- Recorder
- Scenario Editor
- Element Capture Engine
- DOM Registry
- Target Resolver
- Player
- YAML parser/validator
- Runtime configuration layer

See `01-architecture.md` for boundaries.

## 5. User workflow

### 5.1 Recorder-first workflow

```text
Start Recorder
    -> open controlled browser
    -> user performs normal workflow
    -> operations are recorded as a linear list
    -> DOM targets are captured and named
    -> scenario + elements registry are generated
    -> user optionally adds conditions/loops
    -> validate
    -> play back
```

### 5.2 Hand-written scenario workflow

A user may write:

```yaml
- action: click
  target: 注文を確定
```

before `注文を確定` exists in the DOM registry.

This is an allowed intermediate state. Bind mode then asks the user to select the corresponding element in the real browser and generates the DOM definition automatically.

The intended workflow is:

```text
write scenario
    -> detect unbound targets
    -> bind missing targets in browser
    -> validate
    -> execute
```

### 5.3 Picker workflow

A user may open a page, enter element-picking mode, click a DOM element, assign a logical name, and register it independently of full scenario recording.

Recorder, Picker, and Bind all reuse the same Element Capture Engine.

## 6. Readability principle

The following is preferred:

```yaml
- action: click
  target: 注文を確定
```

rather than:

```yaml
- action: click
  target:
    css: "#app > div:nth-child(3) > form > button:nth-child(2)"
```

The complicated DOM representation belongs in `elements.yaml`.

## 7. Japanese user-facing DSL

The DSL uses English for conventional reserved words and browser actions where that improves clarity and interoperability, while allowing Japanese values and free text.

Examples:

```yaml
mode: 実行
risk: 更新
```

and:

```yaml
- action: click
  target: 保存
```

The exact language rules are documented in `02-yaml-dsl.md`.

## 8. Safety and determinism

FlowTape must not silently guess when target resolution remains ambiguous.

Fundamental rules:

- zero matches: wait according to timeout policy, then fail with diagnostics
- multiple acceptable matches: fail as ambiguous
- one match: validate expected type/state before executing
- explicit positional targeting is allowed only as a deliberately fragile fallback

`first match wins` is not the default resolution strategy.

## 9. Recording and control-flow philosophy

The Recorder should optimize for demonstrating a normal successful workflow.

A user should not need to declare an `if`, loop, pagination rule, or alternate path while physically performing the first recording.

Instead:

1. record a normal linear sequence
2. select a contiguous range of recorded steps
3. wrap the range with `if`, `for_each`, `repeat`, or `while`
4. configure the condition using the Scenario Editor

This keeps recording intuitive while still allowing expressive scenarios.

## 10. Non-goals for the initial design

The initial DSL should avoid becoming a general-purpose programming language.

In particular, the current direction excludes or discourages:

- arbitrary Python embedded in YAML
- arbitrary expression evaluation
- unrestricted `goto`
- implicit selection of an arbitrary match
- mandatory hand-writing of CSS/XPath definitions
- storing full DOM snapshots inside normal scenario YAML

These constraints can be revisited only through an explicit specification change.
