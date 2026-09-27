# FlowTape YAML DSL

Status: initial specification before implementation

## 1. Design goals

The FlowTape scenario language serves two roles at once:

1. executable browser automation
2. a human-readable operation manual

The language therefore favors semantic browser operations over Selenium-specific implementation details.

FlowTape may also collect small amounts of structured data as part of a browser workflow. This is intentionally lightweight: DOM values are read through ordinary targets and explicitly appended to scenario result files rather than turning the DSL into a general scraping/programming language.

## 2. Vocabulary policy

Reserved keys and conventional browser-action names use English when the term is concise and widely understood.

Examples:

- `click`
- `double_click`
- `input`
- `select`
- `read`
- `append`
- `wait`
- `check`
- `if`
- `while`
- `repeat`
- `for_each`

User-facing values and free-form text may use Japanese.

Established execution-mode values:

```yaml
mode: 実行
mode: 確認
mode: デバッグ
```

Risk values:

```yaml
risk: 安全
risk: 更新
risk: 破壊的
```

## 3. Top-level structure

Initial scenario shape:

```yaml
version: 1
name: ログイン確認
mode: 実行

variables:
  search_word: RTX 5090

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

A scenario may optionally declare named result outputs:

```yaml
outputs:
  ticket_log:
    format: csv
    file: ticket_log.csv
    existing: new
    columns:
      - ticket_id
      - author
      - subject
```

The scenario-local `elements.yaml` is implicitly associated through the containing scenario directory and normally does not need to be referenced explicitly.

## 4. Execution modes

### 4.1 `実行`

Normal playback. FlowTape resolves, validates, and performs the requested operation.

### 4.2 `確認`

Validation without performing the actual mutating browser operation. The engine checks as applicable:

- target definition exists
- target resolves
- exactly one acceptable element remains for single-target operations
- the element is visible/enabled/editable where required
- expected kind/type is compatible with the action
- current page/window context is valid

Exact behavior of result-producing actions in each mode is defined in the runtime-semantics specification.

### 4.3 `デバッグ`

Provides confirmation behavior plus diagnostics such as locator candidates, match counts, rejection reasons, highlighted candidates, current page scope, and frame/shadow context.

Debug mode must not change matching semantics.

## 5. `enabled`

Step enablement is independent of execution mode.

```yaml
- action: click
  target: ログイン
  enabled: false
```

`enabled` is boolean and defaults to `true`.

A disabled step is skipped intentionally. A step in `確認` mode is not equivalent to a disabled step because validation still occurs.

## 6. Risk classification

Operations may carry independent risk metadata:

- `安全` — non-mutating or low-risk
- `更新` — changes application/server state
- `破壊的` — deletion, irreversible submission, or equivalent high-impact change

In v1, risk is metadata for UI warning/diagnostics/logging and does not itself block execution. Future config policy may add execution gating.

## 7. Target references and page scope

A scenario target is a human-readable logical name:

```yaml
- action: click
  target: 保存
```

The target is resolved inside the currently identified page scope in the scenario-local `elements.yaml`.

The same logical name may therefore exist on multiple pages without conflict.

Within one page, contextual namespacing remains available where needed:

```yaml
- action: click
  target: 配送先/編集
```

Raw CSS/XPath is not the normal scenario representation.

Unbound target names are allowed while authoring but prevent successful normal execution until bound.

## 8. Core browser actions

### 8.1 Navigation

```yaml
- action: open
  url: https://example.com

- action: back

- action: forward

- action: refresh
```

A normal click that causes navigation remains primarily the click step; FlowTape should not redundantly record an additional `open` for the resulting navigation.

A scenario is allowed to omit an initial `open` when it intentionally starts from the current live browser state. In that case FlowTape identifies the current page before the first target-dependent step and fails if the required starting state cannot be established deterministically.

### 8.2 Click

```yaml
- action: click
  target: ログイン
```

### 8.3 Double click

```yaml
- action: double_click
  target: 明細行
```

### 8.4 Input

```yaml
- action: input
  target: 検索欄
  value: ${search_word}
```

`input` expresses replacing/entering the value of an editable element.

### 8.5 Select

```yaml
- action: select
  target: 都道府県
  value: 埼玉県
```

### 8.6 Read

Supported v1 read sources are `text`, `value`, and an explicit attribute.

```yaml
- action: read
  target: 合計金額
  source: text
  into: total
```

```yaml
- action: read
  target: メールアドレス
  source: value
  into: email
```

```yaml
- action: read
  target: ダウンロードリンク
  source:
    attribute: href
  into: download_url
```

The resulting value becomes a runtime variable and may be used by later browser actions, conditions, or explicit output actions.

`read` does not itself write a result file. Data extraction and result persistence remain separate primitives.

### 8.7 Upload

DOM file inputs are supported without automating the native OS file chooser.

```yaml
- action: upload
  target: 添付ファイル
  path: ${upload_file}
```

The target must resolve to a compatible DOM file input. Native file-selection dialogs are outside ordinary DOM automation in v1.

### 8.8 Key operations

Keyboard operations apply to Selenium-controlled web content, not arbitrary OS applications.

```yaml
- action: key
  key: ENTER
```

```yaml
- action: key
  target: 検索欄
  key: ESCAPE
```

```yaml
- action: key
  target: 検索欄
  keys:
    - CTRL
    - A
```

### 8.9 Hover

```yaml
- action: hover
  target: 設定
```

Hover is a first-class v1 action because menus and controls may depend on pointer-over state.

### 8.10 Drag and drop

```yaml
- action: drag_drop
  from: 未処理
  to: 処理済み
```

v1 support is limited to cases that can be reproduced reliably through Selenium/ActionChains. FlowTape does not guarantee all custom HTML5/JavaScript drag implementations.

### 8.11 JavaScript dialogs

JavaScript `alert`, `confirm`, and `prompt` are browser context, not DOM targets.

```yaml
- action: alert_accept
```

```yaml
- action: alert_dismiss
```

```yaml
- action: alert_input
  value: ABC123
```

`alert_input` supplies the prompt value; an explicit accept may follow where required by the implementation semantics.

### 8.12 Append result data

`append` writes one explicit result record/line to a named scenario output.

For structured outputs such as CSV or JSON Lines:

```yaml
- action: append
  output: ticket_log
  values:
    ticket_id: ${ticket_id}
    author: ${author}
    subject: ${subject}
```

For text output:

```yaml
- action: append
  output: processing_log
  value: "${ticket_id}: ${author}"
```

`append` is deliberately separate from `read` so a collected value may be checked, transformed through ordinary scenario flow, reused in browser operations, or written to more than one result.

An `append` execution has observable external effect: when it succeeds, one record/line has been added. Re-executing the same step may therefore produce a duplicate record. v1 does not silently deduplicate or upsert output rows.

Credential references are forbidden in result values. For example, this is invalid:

```yaml
- action: append
  output: dump
  values:
    password: ${credential.example.password}
```

## 9. Wait and check

`wait` and `check` are distinct.

- `wait` waits until a condition becomes true or timeout expires.
- `check` evaluates immediately and fails if the condition is false.

Examples:

```yaml
- action: wait
  until:
    visible: ログイン完了
  timeout: 10s
```

```yaml
- action: wait
  until:
    not_exists: 読み込み中
```

```yaml
- action: check
  condition:
    page: dashboard
```

### 9.1 Download completion

Downloading itself is normally initiated by the relevant browser operation, often a click. Completion can be awaited explicitly:

```yaml
- action: wait
  until:
    download_complete: "*.csv"
  timeout: 60s
```

The check applies to the configured download directory and must not treat an in-progress temporary download file as complete.

## 10. Variables and credentials

### 10.1 Ordinary scenario variables

```yaml
variables:
  search_word: RTX 5090
```

Reference syntax:

```text
${search_word}
```

### 10.2 Credentials

IDs/passwords are stored in external `credentials.yaml` and use a dedicated namespace:

```text
${credential.社内システム.username}
${credential.社内システム.password}
```

Credential values must not be persisted into ordinary scenario steps, logs, diagnostics, exception text, or scenario result outputs after expansion. Recorder capture of password inputs must not serialize the entered plaintext password into `scenario.yaml`.

The expected corporate environment may reset environment variables at logoff, so OS environment variables are not a required credential mechanism in v1.

### 10.3 Runtime variables

`read` and similar runtime operations may create variables used by later steps.

No variable reference permits arbitrary Python/code evaluation.

## 11. Conditions

Conditions are explicit declarative structures. Initial condition vocabulary includes:

```yaml
exists: 次へ
not_exists: 次へ
visible: 次へ
hidden: 次へ
enabled: 次へ
disabled: 次へ
```

Value/text checks:

```yaml
text_equals:
  target: 状態
  value: 完了
```

```yaml
value_equals:
  target: 件数
  value: "10"
```

Page checks:

```yaml
page: order_confirm
```

Logical composition:

```yaml
all:
  - exists: 次へ
  - enabled: 次へ
```

```yaml
any:
  - exists: 完了
  - exists: 終了
```

```yaml
not:
  exists: エラー
```

Example `if`:

```yaml
- if:
    exists: 次へ
  then:
    - action: click
      target: 次へ
  else:
    - action: read
      target: メッセージ
      source: text
      into: result_message
```

Principles:

- no arbitrary Python expression evaluation
- condition result is explicit
- target lookup follows ordinary page/target resolver rules
- ambiguous target/page matching is an error, not truthiness

## 12. Loops

The DSL supports `repeat`, `for_each`, and `while`.

### 12.1 Repeat

```yaml
- repeat:
    count: 3
    steps:
      - action: click
        target: 次へ
```

### 12.2 For each

The primary v1 collection source is a page-scoped DOM target collection.

```yaml
- for_each:
    target: 注文一覧/行
    as: row
    steps:
      - action: click
        target: 編集
        within: ${row}
```

A `for_each` collection intentionally resolves multiple members and therefore does not use the ordinary single-target uniqueness rule.

Future array/value iteration may be added separately without changing this DOM-collection form.

### 12.3 While

```yaml
- while:
    exists: 次へ
    max_iterations: 100
    timeout: 5m
    steps:
      - action: click
        target: 次へ
```

Loop safety is mandatory. `while` and other potentially unbounded loop forms are constrained by iteration and elapsed-time limits. Defaults may come from `config.yaml` and may be overridden per loop.

## 13. Dynamic scope and `within`

Reusable stable DOM context belongs in the registry. Dynamic execution context belongs in the scenario.

Example:

```yaml
- for_each:
    target: 注文一覧/行
    as: row
    steps:
      - action: click
        target: 編集
        within: ${row}
```

`within` narrows target resolution to an execution-time context such as the current loop row. It is not a place for arbitrary raw CSS/XPath strings in normal scenario authoring.

## 14. Browser windows and tabs

Browser-context transitions are explicit when required for deterministic playback.

### 14.1 Switch to a newly opened window

```yaml
- action: switch_window
  to: newest
```

When an operation in window A causes window B to appear, FlowTape records the FlowTape-level parent relationship `B -> A` when deterministically observable.

### 14.2 Explicit parent switch

```yaml
- action: switch_window
  to: parent
```

### 14.3 Close current window

```yaml
- action: close_window
```

### 14.4 Automatic popup return

If the current popup closes by itself:

1. FlowTape detects that the current handle disappeared.
2. If its recorded parent still exists, FlowTape automatically returns to that parent.
3. FlowTape re-identifies the page in the parent window.
4. Execution continues.

The scenario therefore does not need an explicit `switch_window: parent` merely to model the normal consequence of a popup closing itself.

If the popup remains open, FlowTape stays there until an explicit context action changes it.

If the correct return target cannot be determined uniquely, execution fails instead of switching to an arbitrary remaining window.

## 15. Page transitions

Page identity is defined in `elements.yaml`; scenario steps normally reference logical targets without repeating page names.

A scenario may explicitly validate a transition:

```yaml
- action: wait
  until:
    page: dashboard
  timeout: 10s
```

or:

```yaml
- action: check
  condition:
    page: order_confirm
```

## 16. Action/type compatibility

The validator catches obvious incompatibilities before operation where possible.

Examples include:

- `input` against a button
- `upload` against a non-file element
- `select` against an incompatible target kind

## 17. Ambiguity behavior

Single-target operations:

- zero acceptable matches -> wait according to timeout policy where applicable, then fail
- exactly one acceptable match -> proceed
- more than one acceptable match -> ambiguity error

Collection sources intentionally have separate multi-member validation semantics.

Explicit positional matching is allowed only when deliberately encoded as a fragile fallback in the target registry.

## 18. Recorder metadata

Recorder-generated diagnostic metadata must not become required hand-written procedure content.

A reserved `_meta` area may be used sparingly for stable node identity or recorder/version bookkeeping when required by editor semantics. Candidate scores, raw DOM snapshots, event coordinates, rejected candidates, and other verbose capture internals should remain in diagnostics/logs rather than normal scenario YAML.

Visible step numbers are presentation-only and are not persistent identity.

## 19. Optional human-readable descriptions

Steps and structural blocks may carry semantically inert human-readable notes/descriptions for procedure-document readability. The standardized v1 key is `description`; the value has no execution meaning.

## 20. Scenario result outputs

Scenario outputs are explicit user-requested execution artifacts, distinct from FlowTape diagnostic/system logs.

### 20.1 Output declaration

Outputs are declared by logical name at the scenario top level:

```yaml
outputs:
  ticket_log:
    format: csv
    file: ticket_log.csv
    existing: new
    columns:
      - ticket_id
      - author
      - subject
```

Supported v1 formats are:

```text
csv
jsonl
text
```

CSV requires a fixed ordered `columns` list. `append.values` keys must match those declared columns so misspellings can be caught before execution.

JSON Lines writes one JSON object per `append` action. It does not require a fixed column list.

Text output writes one textual line per `append` action.

### 20.2 Existing-file policy

Supported `existing` values:

- `new` — default; do not overwrite a previous run's result
- `append` — append to the configured existing output
- `overwrite` — replace the output at run initialization

The normal recommended policy is `new`.

### 20.3 Output root and run isolation

Scenario YAML normally contains only a relative output filename such as:

```yaml
file: ticket_log.csv
```

Environment-specific root directories belong in `config.yaml`.

For `existing: new`, the runtime should place results in a run-specific location or otherwise generate a non-colliding result path. The exact naming convention is a runtime concern, but a previous run's file must not be silently overwritten.

### 20.4 Incremental durability

Result records should be committed as `append` actions execute rather than retained only in memory until the scenario finishes.

This allows a partially completed run to retain already collected rows if a later browser step fails or the run is stopped.

Runtime buffering is allowed for efficiency only if it preserves equivalent practical durability and flush behavior.

### 20.5 Retry and duplicate semantics

`append` means append. Re-running an already completed `append` step may produce another row/line.

FlowTape v1 does not silently infer a primary key, deduplicate records, or perform an upsert. UI/runtime diagnostics should warn where re-executing an output-producing step may create duplicates.

### 20.6 Diagnostics separation

Collected business/user data belongs in declared outputs, not automatically in FlowTape's diagnostic log.

Normal diagnostics may report that a `read` or `append` succeeded without logging the extracted value itself.

Credential values must never be written to declared outputs.

## 21. Authoring read/output steps

Ordinary human browsing does not reveal an intent to collect data. Therefore Recorder must not infer a `read` or `append` step merely because the user looked at an element.

The Scenario Editor should provide explicit authoring flows such as:

```text
値を取得
  -> browser picker
  -> select target
  -> choose source (text/value/attribute)
  -> choose runtime variable name
```

and:

```text
結果へ記録
  -> choose/create output
  -> map runtime values to fields
```

These flows reuse the same Element Picker / Element Capture Engine used by target binding. The picker click itself is not a scenario browser-operation step.

## 22. Playback control is not scenario mode

Playback pacing remains runtime/editor state rather than scenario semantics.

Examples:

- normal playback
- slow observation delay
- single-step playback
- pause/resume/stop
- execute until selected position
- play to current end and continue recording

These controls do not redefine `mode: 実行/確認/デバッグ`.

## 23. Explicit exclusions

Initial DSL design excludes:

- embedded Python
- arbitrary code/eval expressions
- unrestricted `goto`
- silent implicit fallback to the first DOM/page/window match
- mandatory raw CSS/XPath authoring in scenario steps
- native OS-dialog automation as ordinary DOM actions
- general-purpose scraping transforms/query languages
- automatic statistical aggregation as part of the v1 DSL

Output files are intended to be processed by normal external tools such as spreadsheet software or scripts after the run when aggregation is needed.

## 24. Example scenario

```yaml
version: 1
name: Redmineチケット処理
mode: 実行

outputs:
  tickets:
    format: csv
    file: tickets.csv
    existing: new
    columns:
      - id
      - author
      - assignee
      - status

steps:
  - for_each:
      target: チケット一覧/行
      as: row
      steps:
        - action: click
          target: チケットを開く
          within: ${row}

        - action: read
          target: チケット番号
          source: text
          into: id

        - action: read
          target: 起票者
          source: text
          into: author

        - action: read
          target: 担当者
          source: text
          into: assignee

        - action: read
          target: ステータス
          source: text
          into: status

        - action: append
          output: tickets
          values:
            id: ${id}
            author: ${author}
            assignee: ${assignee}
            status: ${status}

        - action: click
          target: 所定の処理
```

DOM mechanics remain in the scenario-local page-scoped target registry.