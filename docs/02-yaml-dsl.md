# FlowTape YAML DSL

Status: initial specification before implementation

## 1. Design goals

The FlowTape scenario language must satisfy two roles at the same time:

1. an executable browser-automation definition
2. a human-readable operation manual

The language therefore favors semantic operation descriptions over Selenium-specific implementation details.

## 2. Vocabulary policy

Reserved keys and common browser-action names use English when the term is conventional and concise.

Examples:

- `click`
- `double_click`
- `input`
- `select`
- `if`
- `while`
- `repeat`
- `for_each`

User-facing values and free-form text may use Japanese.

Established values:

```yaml
mode: 実行
```

or:

```yaml
mode: 確認
```

or:

```yaml
mode: デバッグ
```

Risk classification uses:

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

steps:
  - action: open
    url: https://example.com/login

  - action: input
    target: メールアドレス
    value: test@example.com

  - action: click
    target: ログイン
```

Exact optional top-level metadata may expand later, but existing keys must not be silently repurposed.

## 4. Execution modes

### 4.1 `実行`

Normal playback.

FlowTape resolves the target, validates it, and performs the requested browser operation.

### 4.2 `確認`

Validation without performing the actual mutating browser operation.

The engine should check, as applicable:

- target definition exists
- target resolves
- one acceptable element remains
- element is visible
- element is enabled/operable
- expected UI kind/type matches the requested action

The purpose is to answer "could this step be executed against the current page?" without carrying out the operation itself.

### 4.3 `デバッグ`

Provides the validation behavior plus additional diagnostics, such as:

- candidate locator information
- match counts
- reason a locator was accepted or rejected
- highlighted candidate element(s)
- contextual information useful for repairing the target definition

Debug mode must not redefine the meaning of target matching.

## 5. `enabled` and `mode`

Whether a step is enabled and how it executes are separate concepts.

A disabled step is skipped intentionally. A step in `確認` mode is not equivalent to a disabled step because validation still occurs.

The final exact syntax for per-step `enabled` is not yet frozen, but implementations must preserve this conceptual separation.

## 6. Risk classification

Operations may be classified by risk independently from execution mode.

Values:

- `安全` — non-mutating or low-risk operations
- `更新` — changes server/application state
- `破壊的` — deletion, irreversible submission, or equivalent high-impact change

Risk is metadata/control information, not a replacement for the action itself.

A future UI may use it for warnings or execution gating.

## 7. Target references

A scenario target is a logical name:

```yaml
- action: click
  target: ログイン
```

or, when namespacing is useful:

```yaml
- action: click
  target: プロフィール/保存
```

Raw CSS/XPath is not the normal scenario representation.

The logical name is resolved through the DOM registry (`elements.yaml`).

Unbound target names are allowed while authoring. They must be bound before successful normal execution.

## 8. Core browser actions

The initial language should be capable of representing at least the following operation families.

### Navigation

```yaml
- action: open
  url: https://example.com
```

Potential navigation operations include page open, back, forward, and refresh. Exact names beyond `open` should remain conventional English terms when introduced.

A navigation that merely results from clicking a normal link/button is not normally persisted as an additional redundant `open` step. Explicit navigation operations and browser-context changes remain distinct operations.

### Click

```yaml
- action: click
  target: ログイン
```

### Double click

```yaml
- action: double_click
  target: 明細行
```

### Input text

```yaml
- action: input
  target: メールアドレス
  value: test@example.com
```

`input` expresses replacing/entering a value into an editable element. More specialized typing behavior may be added separately if needed.

### Select

```yaml
- action: select
  target: 都道府県
  value: 埼玉県
```

### Read

A step may read information from a target and store it in a variable.

Conceptual example:

```yaml
- action: read
  target: 合計金額
  into: total
```

The exact supported read sources (text/value/attribute/etc.) will be specified before implementation of this action family.

### Wait/check operations

The DSL must support waiting/checking for browser state without requiring arbitrary Python expressions.

The exact action names and option schema for generic waits remain to be finalized.

### Window/tab context

The DSL must leave room for explicit browser-context transitions such as switching to a newly opened tab/window and returning to a previous one.

Exact reserved action names remain to be finalized, but these are semantic browser-context operations and should be represented explicitly when needed for deterministic playback.

## 9. Variables

Values may reference variables.

Example:

```yaml
- action: input
  target: パスワード
  value: ${PASSWORD}
```

Variables may originate from configuration, inputs, or `read` steps.

The DSL must not permit arbitrary Python evaluation simply because a value contains an expression-like string.

## 10. Conditions

Conditions are explicit structural blocks.

Conceptual example:

```yaml
- if:
    exists: 次へ
  then:
    - action: click
      target: 次へ
```

An `else` branch may be attached where needed.

The condition vocabulary should be domain-oriented, for example element existence/state/value checks, rather than arbitrary code execution.

Exact condition-schema details remain subject to further specification, but the following principles are fixed:

- no arbitrary Python expression evaluation
- condition result is explicit
- target lookup follows the same resolver rules as normal actions
- ambiguous target matching is not converted into truthiness

## 11. Loops

The DSL needs to represent at least:

- `repeat`
- `for_each`
- `while`

The intended authoring flow is to record a normal linear range first and then wrap that range in the chosen loop block.

### Repeat

Conceptual example:

```yaml
- repeat:
    count: 3
    steps:
      - action: click
        target: 次へ
```

### For each

Conceptual example:

```yaml
- for_each:
    source: 対象行
    as: row
    steps:
      - action: click
        target: 編集
```

The final collection/source schema is not yet fixed. A `for_each` source denotes a collection and therefore is not subject to the ordinary single-target requirement that exactly one element resolve.

### While

Conceptual example:

```yaml
- while:
    exists: 次へ
    steps:
      - action: click
        target: 次へ
```

Loop implementations must include safeguards against accidental unbounded execution. The exact limit/timeout schema will be fixed later.

## 12. Scope and `within`

Earlier selector design used explicit narrowing such as dialog/row/current context. With the introduction of the DOM registry, reusable DOM scope normally belongs in the target definition rather than being repeated in every scenario step.

A scenario-level `within` concept may still be useful for dynamic contexts such as a current loop row. The exact syntax remains open.

The design rule is:

- stable reusable DOM context -> `elements.yaml`
- dynamic execution context -> scenario/control-flow context

## 13. Action/type compatibility

A target definition may declare a semantic `kind`, such as `button` or `input`.

The validator should catch obvious incompatibilities before operation where possible.

Example invalid combination:

```yaml
- action: input
  target: ログイン
```

when `ログイン` is registered as a button.

## 14. Ambiguity behavior

Scenario execution must never interpret a target as "the first matching element" unless an explicitly positional target definition deliberately requests that behavior.

Rules:

- zero matches -> wait according to timeout policy, then fail
- one acceptable match -> proceed
- more than one acceptable match -> ambiguity error

This applies to actions and condition checks. Collection sources used by `for_each` follow their own collection-validation semantics.

## 15. Recorder metadata

Recorder-generated diagnostic metadata may be associated with recorded steps internally or through a reserved metadata area such as `_meta`.

Such metadata must not become required hand-written scenario content and must not alter the visible semantic meaning of the procedure.

The final persisted `_meta` schema is not yet fixed.

Stable node identifiers may be persisted in metadata or another reserved field where needed by the editor. Visible step numbers are not persisted identity.

## 16. Explicit exclusions

Initial DSL design excludes:

- embedded Python
- arbitrary code/eval expressions
- unrestricted `goto`
- silent implicit fallback to the first DOM match
- requiring CSS-only or XPath-only target definitions

## 17. Example scenario

The following example demonstrates the intended style. Some advanced collection/read syntax is illustrative until those sub-schemas are finalized.

```yaml
version: 1
name: 商品検索と明細処理
mode: 実行

steps:
  - action: open
    url: https://example.com

  - action: input
    target: 検索欄
    value: RTX 5090

  - action: click
    target: 検索

  - if:
      exists: 検索結果/商品一覧
    then:
      - action: click
        target: 検索結果/RTX 5090
    else:
      - action: read
        target: 検索結果/メッセージ
        into: result_message

  - while:
      exists: 次へ
    steps:
      - action: click
        target: 次へ

  - action: click
    target: 商品詳細/カートに入れる
    risk: 更新

  - action: click
    target: 注文確認/注文を確定
    risk: 破壊的
```

This example is deliberately semantic: DOM mechanics remain in the target registry.

## 18. Playback control is not scenario mode

Playback pacing is intentionally not represented by `mode`.

`実行` / `確認` / `デバッグ` describe what the engine does with a step. UI/runtime choices such as normal playback, slow playback, single-step playback, pause, execute-until-position, or play-to-end-and-record describe how execution is scheduled interactively.

Those controls should normally remain runtime/editor state rather than procedure semantics in scenario YAML.

## 19. Optional human-readable descriptions

Steps and structural blocks may carry an optional description/note intended for procedure-document readability.

The exact key name is not yet frozen, but the field must remain semantically inert unless a future specification explicitly assigns execution meaning to it.
