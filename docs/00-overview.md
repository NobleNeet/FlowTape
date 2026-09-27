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
    -> current page scope
    -> DOM registry resolution
    -> browser execution
```

FlowTape may also collect small amounts of structured/textual data during browser workflows through explicit `read` and `append` actions. This is a lightweight result-output capability, not a general-purpose scraping/programming environment.

## 2. Core goals

FlowTape should satisfy all of the following:

1. A user can demonstrate a normal browser workflow and record it.
2. Recorded steps remain readable as a procedure after recording.
3. A scenario can also be written or edited manually.
4. DOM details are separated from scenario logic.
5. Missing DOM bindings can be created interactively instead of requiring hand-written selectors.
6. Conditions and loops can be added after recording by wrapping ranges of existing steps.
7. Playback is conservative: ambiguous target, page, or window resolution must not silently choose an arbitrary candidate.
8. Browser/DOM logic should work similarly across Linux development and Windows 11 + Edge deployment.
9. Scenario files, DOM knowledge, runtime configuration, credentials, browser profile state, WebDriver placement, and generated outputs remain external to the packaged executable where appropriate.
10. Simple values read from pages may be explicitly accumulated into CSV, JSON Lines, or text outputs for later user processing/aggregation.

## 3. Scenario package

A scenario is normally managed as a directory/package rather than as one isolated YAML file.

Recommended layout:

```text
scenarios/
  注文処理/
    scenario.yaml
    elements.yaml

  顧客検索/
    scenario.yaml
    elements.yaml
```

`scenario.yaml` and `elements.yaml` in the same scenario directory are implicitly associated. The scenario does not need to repeat the registry path in normal use.

Each scenario owns its own DOM registry in the initial design. A global registry shared by unrelated scenarios is not assumed.

## 4. Main artifacts

### 4.1 Scenario YAML

Scenario YAML describes procedure semantics:

- operation order
- action type
- ordinary values and variables
- checks and waits
- conditions and loops
- logical target names
- browser/window context operations
- named result-output definitions
- explicit `append` steps that persist collected values

Example:

```yaml
version: 1
name: ログイン確認
mode: 実行

steps:
  - action: open
    url: https://example.com/login

  - action: input
    target: ユーザーID
    value: ${credential.社内システム.username}

  - action: input
    target: パスワード
    value: ${credential.社内システム.password}

  - action: click
    target: ログイン
```

Result-output example:

```yaml
outputs:
  ticket_log:
    format: csv
    file: ticket_log.csv
    existing: new
    columns:
      - ticket_id
      - author
```

Raw CSS/XPath is not the normal scenario representation.

### 4.2 Scenario-local DOM registry (`elements.yaml`)

`elements.yaml` stores page-scoped DOM-resolution knowledge for one scenario.

Conceptually:

```text
scenario
    -> current page identification
    -> page-scoped logical target
    -> locator candidates
    -> current DOM element
```

The registry stores:

- page definitions and page-identification rules
- logical targets inside each page scope
- candidate locators
- expected element characteristics
- iframe/shadow traversal context where needed
- limited diagnostic fingerprint information
- collection definitions used by `for_each`

A target name is required to be unique within the current page scope, not globally across every page or every scenario. Contextual names such as `配送先/編集` remain useful for collisions inside one page.

### 4.3 Configuration (`config.yaml`)

Runtime/environment-specific values belong in external configuration rather than scenario logic.

The initial configuration is expected to cover at least:

- Edge/browser settings
- required WebDriver absolute path
- timeout defaults
- log/output/download locations
- credentials file path
- optional persistent FlowTape browser-profile path
- Recorder/browser window-placement preferences
- playback preferences and loop safety defaults

### 4.4 Credentials (`credentials.yaml`)

IDs and passwords are stored separately from scenario YAML in an external plaintext YAML file because the expected managed corporate environment may reset environment variables and user-profile data at logoff.

Example:

```yaml
version: 1

credentials:
  社内システム:
    username: user001
    password: password123
```

Scenarios refer to them through a dedicated namespace such as:

```text
${credential.社内システム.username}
${credential.社内システム.password}
```

Credential values must not be written to normal logs, debug output, or scenario result outputs. `credentials.yaml` must not be committed to source control; a placeholder/example file may be committed instead.

### 4.5 Generated outputs

Scenario outputs are user-requested execution artifacts, distinct from FlowTape system logs and browser downloads.

v1 supports:

- CSV for spreadsheet/manual aggregation workflows
- JSON Lines for simple machine processing
- text for line-oriented result logging

Scenario files declare logical outputs using relative file names. The environment-specific root directory is provided by `config.yaml` through `paths.outputs`.

## 5. Product components

FlowTape is organized conceptually into:

- Recorder
- Scenario Editor
- Element Capture Engine
- Page Identifier
- DOM Registry
- Target Resolver
- Player
- Window/Browser Context Manager
- Result Output Writer
- YAML parser/validator
- Runtime configuration layer
- Credential provider

See `01-architecture.md` for boundaries.

## 6. User workflows

### 6.1 Recorder-first workflow

```text
Start Recorder
    -> open controlled browser
    -> user performs normal workflow
    -> operations are recorded as a linear list
    -> pages and DOM targets are captured/named
    -> scenario + scenario-local elements registry are generated
    -> user optionally adds conditions/loops
    -> user may explicitly add read/append steps for result collection
    -> validate
    -> play back
```

### 6.2 Hand-written scenario workflow

A user may write a target reference before it exists in the current page scope of the registry.

```yaml
- action: click
  target: 注文を確定
```

This is an allowed authoring state. Bind mode then asks the user to select the corresponding element in the real browser and generates the DOM definition automatically.

### 6.3 Picker workflow

A user may open a page, enter element-picking mode, click a DOM element, assign a logical name, and register it independently of full scenario recording.

Recorder, Picker, Bind, and Rebind reuse the same Element Capture Engine.

### 6.4 Lightweight data-collection workflow

A scenario may read a DOM value into a runtime variable and then explicitly append it to a named output while continuing normal browser automation.

Example:

```yaml
- action: read
  target: 起票者
  source: text
  into: author

- action: append
  output: ticket_log
  values:
    author: ${author}
```

`read` and `append` remain separate so collected data may also be checked, reused in later browser operations, or written to multiple outputs.

## 7. Readability principle

Prefer:

```yaml
- action: click
  target: 注文を確定
```

rather than embedding raw selector mechanics in each procedure step.

Complicated DOM representation belongs in the scenario-local `elements.yaml`.

## 8. Japanese user-facing DSL

Reserved keys and conventional browser actions use concise English terms. User-facing values and free text may use Japanese.

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

The detailed language rules are documented in `02-yaml-dsl.md`.

## 9. Safety and determinism

FlowTape must not silently guess when resolution remains ambiguous.

Fundamental rules:

- target zero matches: wait according to policy, then fail with diagnostics
- target multiple acceptable matches: fail as ambiguous
- exactly one acceptable target: validate expected type/state before executing
- positional targeting is allowed only as an explicitly fragile last resort
- page zero matches: `UnknownPage`
- page multiple matches: `AmbiguousPage`
- a closed popup returns to its recorded parent window only when that relationship is known and the parent still exists
- uncertain window recovery must fail rather than selecting an arbitrary remaining window
- result output never bypasses credential/secret protection

`first match wins` is not a default strategy.

## 10. Recording and control-flow philosophy

The Recorder optimizes for demonstrating a normal successful workflow.

The user should not need to declare an `if`, loop, pagination rule, or alternate path while physically performing the first recording.

Instead:

1. record a normal linear sequence
2. select a contiguous range of recorded steps
3. wrap it with `if`, `for_each`, `repeat`, or `while`
4. configure the structure in the Scenario Editor

Data collection is similarly explicit: normal browsing does not cause arbitrary visible text to be scraped automatically. `read`/`append` steps are deliberately added where the user wants result data.

## 11. Browser context philosophy

A scenario may move through substantially different URLs/DOMs and may open additional tabs/windows.

- page identity is represented in `elements.yaml` using URL and/or DOM-identification evidence
- normal target lookup occurs in the currently identified page scope
- newly opened tabs/windows are explicit browser-context transitions
- FlowTape records the parent relationship when a new window appears as a result of an operation
- if the current popup closes automatically, FlowTape automatically returns to the known parent and re-identifies the page
- if the popup remains open, FlowTape remains there until the scenario explicitly switches or closes it

## 12. Initial non-goals

The initial DSL should not become a general-purpose programming language or full scraping framework.

The current direction excludes or discourages:

- arbitrary Python embedded in YAML
- arbitrary expression evaluation
- unrestricted `goto`
- implicit selection of an arbitrary DOM/page/window match
- mandatory hand-writing of CSS/XPath definitions
- storing full DOM snapshots in normal scenario files
- native OS-dialog automation as if it were ordinary DOM automation
- general-purpose data transformation/query languages inside scenario YAML
- implicit bulk scraping of arbitrary page content

These constraints should be revisited only through an explicit specification change.
