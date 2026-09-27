# FlowTape Data Schema

Status: initial specification before implementation

## 1. Purpose

This document defines the persisted data schema for FlowTape v1.

It covers:

- `scenario.yaml`
- scenario-local `elements.yaml`
- `config.yaml`
- `credentials.yaml`

The intent is to make these formats precise enough that the Python parser, validator, serializer, editor model, recorder, and player do not need to invent missing schema rules independently.

Runtime execution semantics such as exact action behavior in `実行` / `確認` / `デバッグ`, target fallback behavior, page-resolution behavior, and waits are defined separately in the runtime-semantics specification.

Recorder browser-event transport and browser-side capture models are defined separately in the recorder-protocol specification.

## 2. General schema principles

### 2.1 Strict schemas

FlowTape v1 uses strict persisted schemas.

Unknown fields are validation errors unless a field is explicitly documented as an extension/free-form area.

For example, this is invalid:

```yaml
- action: click
  target: 保存
  timout: 10s
```

FlowTape must not silently ignore `timout` or reinterpret it as `timeout`.

The purpose of strict validation is to fail early on spelling mistakes, unsupported syntax, and accidental schema drift.

### 2.2 Schema version is not application version

Each persisted file has its own schema version.

```yaml
version: 1
```

means version 1 of that file format. It is not the FlowTape application version.

Schema versions may evolve independently. A future installation may therefore legitimately load, for example:

```text
scenario schema: 2
elements schema: 1
config schema: 1
credentials schema: 1
```

Compatibility and migration rules must be explicit when a schema version changes.

### 2.3 Enum values are exact

Enum values use exact spelling and case.

FlowTape does not silently normalize unsupported variants.

Examples:

```yaml
mode: 実行
risk: 更新
action: double_click
```

Values such as `Click`, `execute`, or misspelled Japanese mode values are invalid unless explicitly added to the schema.

### 2.4 Omission and `null`

For optional fields where no special `null` semantics are documented:

- omitted field = use default / not configured
- explicit `null` = not configured

They are semantically equivalent.

The serializer should normally omit optional `null` fields.

### 2.5 Ordered structures

The following lists are semantically ordered and must preserve their persisted order:

- scenario `steps`
- nested branch/loop `steps`
- target `locate` candidates
- frame/shadow `context`

A serializer must not reorder them automatically.

### 2.6 UTF-8 and Japanese text

Persisted YAML is UTF-8.

Japanese user-facing names and descriptions are first-class values and should be emitted directly, not escaped as Unicode code points.

## 3. Scalar values

### 3.1 Scalar types

Where this document permits a scalar, the supported YAML scalar types are:

- string
- integer
- float
- boolean
- null

Nested maps and lists are not scalars.

### 3.2 YAML implicit typing

Fields whose meaning requires strings must validate as strings after YAML parsing.

Values such as IDs, PINs, paths, target names, locator values, and credential values should be quoted when YAML implicit typing would otherwise alter their meaning.

Example:

```yaml
pin: "001234"
```

A parser/validator error should explain quoting requirements where practical.

## 4. Duration format

Persisted durations use strings with explicit units.

Supported v1 units:

- `ms`
- `s`
- `m`
- `h`

Examples:

```yaml
timeout: 500ms
timeout: 10s
timeout: 5m
timeout: 1h
```

Bare numbers are not accepted as durations in v1.

This rule applies consistently to scenario and configuration duration fields.

Internally, the application may normalize durations to a standard Python duration representation.

## 5. Variable references

FlowTape supports interpolation references using:

```text
${name}
```

Examples:

```yaml
value: ${search_word}
value: "商品名: ${search_word}"
url: "https://example.com/search?q=${search_word}"
```

Credential references use the reserved namespace:

```text
${credential.社内システム.username}
```

Runtime loop/context values may also be referenced:

```text
${row}
```

Variable-reference contents do not support arbitrary expressions, Python, function calls, or arithmetic.

Invalid examples include:

```text
${foo + 1}
${len(items)}
${python:...}
```

## 6. `scenario.yaml`

### 6.1 Top-level schema

A v1 scenario has this conceptual form:

```yaml
version: 1
name: 商品検索
description: 商品を検索するシナリオ
mode: 実行

variables:
  search_word: RTX 5090

steps:
  - action: open
    url: https://example.com
```

Fields:

| Field | Required | Type | Default |
|---|---|---|---|
| `version` | yes | integer literal `1` | none |
| `name` | yes | non-empty string | none |
| `description` | no | string | omitted |
| `mode` | no | enum | `実行` |
| `variables` | no | map<string, scalar> | empty |
| `steps` | yes | list<Node> | none |

Allowed `mode` values:

```text
実行
確認
デバッグ
```

Recorder/Editor-generated files may explicitly persist `mode: 実行` even though it is the default.

### 6.2 Scenario variables

Scenario-defined variables are limited to scalar values in v1.

Valid:

```yaml
variables:
  search_word: RTX 5090
  retry_count: 3
  enabled: true
```

Invalid in v1:

```yaml
variables:
  users:
    - A
    - B
```

```yaml
variables:
  account:
    name: A
    id: 1
```

Collection/value iteration may be added in a future schema without changing the v1 DOM-collection model.

## 7. Scenario nodes

### 7.1 Node union

Every item in a `steps` list is exactly one of:

```text
ActionNode
IfNode
RepeatNode
WhileNode
ForEachNode
```

A node may not declare multiple node kinds simultaneously.

Invalid:

```yaml
- action: click
  target: 保存
  while:
    exists: 次へ
```

### 7.2 Common node fields

All node types may contain:

```yaml
enabled: true
description: 任意の説明
_meta:
  id: 01K...
```

Common fields:

| Field | Required | Type | Default |
|---|---|---|---|
| `enabled` | no | boolean | `true` |
| `description` | no | string | omitted |
| `_meta` | no | NodeMeta | omitted for hand-written YAML |

`description` has no execution meaning in v1.

The serializer should normally omit `enabled: true`.

## 8. Stable node identity

### 8.1 `_meta.id`

Recorder/Editor-created nodes use a stable persisted identifier:

```yaml
_meta:
  id: 01K6QZX...
```

The identifier format is ULID.

Visible step numbers are presentation-only and must not be used as identity.

### 8.2 Hand-written scenarios

Hand-written YAML may omit `_meta.id`.

When FlowTape loads such a node:

1. create an in-memory ULID for editor/runtime tracking
2. do not require the user to manually add it
3. when the scenario is later saved through the FlowTape editor, persist the generated ID

### 8.3 `_meta` scope

`_meta` is reserved for FlowTape-maintained node bookkeeping.

In v1 its defined field is:

```text
id
```

Unknown `_meta` fields are not automatically accepted merely because they are under `_meta`; new fields must be specified deliberately.

Verbose recorder diagnostics, candidate scores, raw DOM snapshots, coordinates, and rejected candidates do not belong in `_meta`.

## 9. Action nodes

### 9.1 Action discriminator

Action nodes use `action` as a discriminator.

Supported v1 actions are:

```text
open
back
forward
refresh
click
double_click
input
select
read
upload
key
hover
drag_drop
alert_accept
alert_dismiss
alert_input
wait
check
switch_window
close_window
```

Each action accepts only the fields defined for that action plus common node fields.

### 9.2 Navigation actions

```yaml
- action: open
  url: https://example.com
```

`open` requires:

- `url`: non-empty interpolatable string

`back`, `forward`, and `refresh` have no action-specific required fields.

### 9.3 Click actions

```yaml
- action: click
  target: ログイン
```

```yaml
- action: double_click
  target: 明細行
```

Required:

- `target`: non-empty string

Optional:

- `within`: runtime context reference string

### 9.4 Input action

```yaml
- action: input
  target: 検索欄
  value: ${search_word}
```

Required:

- `target`: non-empty string
- `value`: interpolatable scalar/string value

Optional:

- `within`

### 9.5 Select action

```yaml
- action: select
  target: 都道府県
  value: 埼玉県
```

Required:

- `target`
- `value`

Optional:

- `within`

### 9.6 Read action

Supported source forms:

```yaml
source: text
```

```yaml
source: value
```

```yaml
source:
  attribute: href
```

Example:

```yaml
- action: read
  target: 合計金額
  source: text
  into: total
```

Required:

- `target`
- `source`
- `into`: non-empty runtime-variable name

Optional:

- `within`

`source` must be exactly one supported form.

### 9.7 Upload action

```yaml
- action: upload
  target: 添付ファイル
  path: ${upload_file}
```

Required:

- `target`
- `path`: interpolatable string

Optional:

- `within`

### 9.8 Key action

A key action must provide exactly one of:

```yaml
key: ENTER
```

or:

```yaml
keys:
  - CTRL
  - A
```

`target` is optional. If present, the key operation is target-scoped.

`within` is allowed only when `target` is present.

### 9.9 Hover action

```yaml
- action: hover
  target: 設定
```

Required:

- `target`

Optional:

- `within`

### 9.10 Drag-and-drop action

```yaml
- action: drag_drop
  from: 未処理
  to: 処理済み
```

Required:

- `from`: logical target name
- `to`: logical target name

The exact execution limitations remain part of runtime semantics.

### 9.11 JavaScript dialog actions

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

`alert_input` requires `value`.

`alert_accept` and `alert_dismiss` have no action-specific fields.

### 9.12 Wait action

```yaml
- action: wait
  until:
    visible: ログイン完了
  timeout: 10s
```

Required:

- `until`: WaitCondition

Optional:

- `timeout`: duration string

### 9.13 Check action

```yaml
- action: check
  condition:
    page: dashboard
```

Required:

- `condition`: Condition

### 9.14 Window actions

```yaml
- action: switch_window
  to: newest
```

```yaml
- action: switch_window
  to: parent
```

Allowed v1 values for `to`:

```text
newest
parent
```

`close_window` has no action-specific fields.

## 10. Risk metadata

Action nodes may optionally carry:

```yaml
risk: 安全
```

Allowed values:

```text
安全
更新
破壊的
```

`risk` is metadata in schema v1. Runtime policy based on risk is defined separately.

## 11. Conditions

### 11.1 Condition union

A Condition is exactly one operator.

Supported v1 operators:

```text
exists
not_exists
visible
hidden
enabled
disabled
text_equals
value_equals
page
all
any
not
```

Invalid:

```yaml
condition:
  exists: 次へ
  visible: 次へ
```

Equivalent explicit AND form:

```yaml
condition:
  all:
    - exists: 次へ
    - visible: 次へ
```

### 11.2 Target-state conditions

These operators contain one logical target name:

```yaml
exists: 次へ
not_exists: 次へ
visible: 次へ
hidden: 次へ
enabled: 次へ
disabled: 次へ
```

### 11.3 Value/text conditions

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

Required fields:

- `target`
- `value`

### 11.4 Page condition

```yaml
page: order_confirm
```

The value is a page ID defined in `elements.yaml`.

### 11.5 Logical composition

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

`all` and `any` require non-empty lists of Condition.

`not` contains exactly one Condition.

## 12. Wait conditions

`wait.until` accepts ordinary conditions plus wait-specific conditions.

The v1 wait-specific condition is:

```yaml
download_complete: "*.csv"
```

`download_complete` contains a non-empty string pattern.

The exact filesystem/browser completion semantics are defined in runtime semantics.

## 13. Structural nodes

### 13.1 IfNode

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

Required:

- `if`: Condition
- `then`: list<Node>

Optional:

- `else`: list<Node>

`else` is omitted when no else branch exists; an empty else branch is not generated automatically.

### 13.2 RepeatNode

```yaml
- repeat:
    count: 3
    steps:
      - action: click
        target: 次へ
```

Required inside `repeat`:

- `count`: positive integer
- `steps`: list<Node>

### 13.3 WhileNode

```yaml
- while:
    exists: 次へ
    max_iterations: 100
    timeout: 5m
    steps:
      - action: click
        target: 次へ
```

A WhileNode combines:

- exactly one Condition operator
- optional `max_iterations`: positive integer
- optional `timeout`: duration
- required `steps`: list<Node>

For serialization/readability, the condition operator is written directly inside `while`, as shown above, rather than nested under a separate `condition` key.

Loop limits omitted from the node use configuration defaults.

### 13.4 ForEachNode

```yaml
- for_each:
    target: 注文一覧/行
    as: row
    steps:
      - action: click
        target: 編集
        within: ${row}
```

Required inside `for_each`:

- `target`: collection name
- `as`: runtime variable name
- `steps`: list<Node>

The referenced target must resolve to a collection definition, not a normal single-element target.

## 14. `within`

`within` narrows resolution to a runtime context.

Example:

```yaml
within: ${row}
```

In v1 it is an interpolatable runtime-context reference string.

It is not a place for raw CSS/XPath selectors.

## 15. `elements.yaml`

### 15.1 Top-level schema

```yaml
version: 1

pages:
  login:
    identify:
      url:
        contains: /login
    elements:
      ログイン:
        kind: button
        locate:
          - by: role
            role: button
            name: ログイン
        expect:
          role: button
          enabled: true
```

Fields:

| Field | Required | Type |
|---|---|---|
| `version` | yes | integer literal `1` |
| `pages` | yes | map<PageId, PageDefinition> |

### 15.2 Page IDs

Page IDs are non-empty UTF-8 strings.

Japanese IDs are allowed.

Page IDs are identifiers only; characters such as `/` or `.` do not implicitly define hierarchy or namespaces.

## 16. PageDefinition

A page definition supports:

```yaml
identify: ...
elements: ...
collections: ...
```

Fields:

| Field | Required | Type | Default |
|---|---|---|---|
| `identify` | yes | PageCondition | none |
| `elements` | no | map<TargetName, ElementDefinition> | empty |
| `collections` | no | map<CollectionName, CollectionDefinition> | empty |

Single-element targets and collections are intentionally separate schema categories because their resolution cardinality differs.

## 17. Page identification schema

### 17.1 PageCondition union

Supported v1 page-identification operators:

```text
url
exists
all
any
not
```

A PageCondition uses exactly one operator.

### 17.2 URL condition

A URL condition uses exactly one of:

```yaml
url:
  equals: https://example.com/login
```

```yaml
url:
  contains: /login
```

```yaml
url:
  starts_with: https://example.com/orders/
```

Regular expressions are not part of v1.

### 17.3 DOM existence condition

Page identification may require semantic DOM evidence:

```yaml
exists:
  role: heading
  name: 注文確認
```

The v1 existence selector may contain semantic fields supported by the shared DOM-semantics implementation, including:

- `role`
- `name`
- `text`
- `label`
- `testid`
- `id`

At least one identifying field is required.

### 17.4 Logical composition

Page conditions support:

```yaml
all:
  - ...
```

```yaml
any:
  - ...
```

```yaml
not:
  ...
```

The exact page-match semantics are defined in runtime semantics.

## 18. ElementDefinition

Conceptual schema:

```yaml
kind: button
context:
  - frame:
      id: payment-frame
locate:
  - by: role
    role: button
    name: 保存
expect:
  role: button
  enabled: true
fingerprint:
  text: 保存
```

Fields:

| Field | Required | Type |
|---|---|---|
| `kind` | yes | TargetKind |
| `context` | no | ordered list<ContextStep> |
| `locate` | yes | non-empty ordered list<Locator> |
| `expect` | no | Expectation |
| `fingerprint` | no | Fingerprint |

Allowed v1 `kind` values:

```text
button
input
textarea
select
checkbox
radio
link
menu
tab
file
element
```

## 19. Locator union

### 19.1 Locator families

Supported `by` values:

```text
testid
id
name
role
label
text
placeholder
attribute
relative
css
xpath
```

`by` is the discriminator.

A locator accepts only fields valid for its `by` family plus common locator fields.

### 19.2 Common locator fields

Common optional fields:

```yaml
fragile: true
index: 3
```

If `index` is present, `fragile: true` is required.

The meaning of `index` is zero/one-based only after runtime semantics fixes the convention; implementations must not invent a convention independently before then.

### 19.3 Simple locators

Examples:

```yaml
- by: testid
  value: checkout-submit
```

```yaml
- by: id
  value: email
```

```yaml
- by: name
  value: username
```

```yaml
- by: label
  value: メールアドレス
```

```yaml
- by: placeholder
  value: メールアドレスを入力
```

Each requires a non-empty string `value`.

### 19.4 Role locator

```yaml
- by: role
  role: button
  name: 保存
```

Required:

- `role`

Optional:

- `name`

### 19.5 Text locator

```yaml
- by: text
  value: 注文を確定
  exact: true
```

Required:

- `value`

Optional:

- `exact`: boolean, default `true`

### 19.6 Attribute locator

```yaml
- by: attribute
  name: data-action
  value: submit-order
```

Required:

- `name`
- `value`

### 19.7 CSS locator

```yaml
- by: css
  value: 'button[data-action="save"]'
```

Required:

- `value`

### 19.8 XPath locator

```yaml
- by: xpath
  value: '//button[@type="submit"]'
```

Required:

- `value`

Fragile XPath forms are marked according to locator-generation rules.

### 19.9 Relative locator

Conceptual form:

```yaml
- by: relative
  anchor:
    role: heading
    name: プロフィール
  relation: section
  target:
    role: button
    name: 保存
```

Required:

- `anchor`: SemanticSelector
- `relation`: RelativeRelation
- `target`: SemanticSelector

Supported initial relation values include:

```text
descendant
row
dialog
form
section
nearby
```

Relative locator details remain semantic rather than raw DOM-path expressions.

## 20. SemanticSelector

A SemanticSelector is used inside relative locators and page-identification DOM checks.

Supported v1 fields include:

```text
role
name
text
label
testid
id
```

At least one field is required.

Unknown selector fields are invalid.

The exact accessible-name/role matching algorithm is defined by the shared DOM-semantics/runtime specification.

## 21. Expectation schema

Supported v1 fields:

```yaml
expect:
  tag: input
  role: textbox
  input_type: email
  visible: true
  enabled: true
  editable: true
  attributes:
    autocomplete: email
```

Allowed fields:

- `tag`: string
- `role`: string
- `input_type`: string
- `visible`: boolean
- `enabled`: boolean
- `editable`: boolean
- `attributes`: map<string, string>

Expectations should remain minimal and meaningful; generation policy is defined in locator-generation documentation.

## 22. Traversal context

`context` is an ordered list.

Example:

```yaml
context:
  - frame:
      id: payment-frame
  - shadow:
      css: app-shell
  - shadow:
      css: payment-panel
```

Each context step is exactly one of:

```text
FrameContext
ShadowContext
```

Mixed sequences such as frame -> shadow -> frame are valid where supported by the runtime.

A context step may use the specific locator fields defined for that traversal type. It must not contain both `frame` and `shadow` simultaneously.

## 23. CollectionDefinition

Collections are stored separately from `elements`.

Example:

```yaml
pages:
  orders:
    collections:
      注文一覧/行:
        locate:
          - by: role
            role: row
```

Conceptual fields:

| Field | Required | Type |
|---|---|---|
| `context` | no | ordered list<ContextStep> |
| `locate` | yes | non-empty ordered list<Locator> |
| `expect` | no | CollectionExpectation |
| `fingerprint` | no | Fingerprint |

Collection locators intentionally resolve multiple members.

A normal `elements` definition must not be used as a `for_each` collection merely because its locator happens to match multiple elements.

## 24. Fingerprint schema

Fingerprint is diagnostic metadata, not an alternate fuzzy locator.

Supported v1 shape:

```yaml
fingerprint:
  text: 保存
  nearby_text:
    - プロフィール
  attributes:
    type: submit
```

Fields:

- `text`: optional string
- `nearby_text`: optional list<string>
- `attributes`: optional map<string, string>

Full DOM HTML, full ancestor chains, event coordinates, and candidate score tables must not be persisted as fingerprints.

## 25. `config.yaml`

### 25.1 Top-level shape

Recommended v1 configuration:

```yaml
version: 1

browser:
  type: edge
  executable: null
  profile_path: null

driver:
  path: 'D:\CompanyTools\EdgeDriver\msedgedriver.exe'

credentials:
  path: ./credentials.yaml

timeouts:
  default: 10s
  page_load: 30s

paths:
  scenarios: ./scenarios
  logs: ./logs
  downloads: ./downloads

loops:
  max_iterations: 1000
  timeout: 10m

recorder:
  arrange_windows: true

playback:
  observation_delay: 0s

logging:
  level: INFO
```

### 25.2 Browser config

```yaml
browser:
  type: edge
  executable: null
  profile_path: null
```

`type` v1 supports only:

```text
edge
```

`executable` and `profile_path` are optional path strings.

### 25.3 Driver config

```yaml
driver:
  path: 'D:\CompanyTools\EdgeDriver\msedgedriver.exe'
```

`driver.path` is required and must be an absolute filesystem path.

Relative driver paths are invalid.

FlowTape does not fall back to Selenium Manager or PATH discovery.

### 25.4 Credentials config

```yaml
credentials:
  path: ./credentials.yaml
```

The path may be relative to the directory containing `config.yaml`.

### 25.5 Timeout config

```yaml
timeouts:
  default: 10s
  page_load: 30s
```

Both fields use the duration format defined in this document.

### 25.6 Runtime paths

```yaml
paths:
  scenarios: ./scenarios
  logs: ./logs
  downloads: ./downloads
```

Relative paths are resolved relative to the directory containing `config.yaml` unless another specification explicitly states otherwise.

### 25.7 Loop defaults

```yaml
loops:
  max_iterations: 1000
  timeout: 10m
```

`max_iterations` is a positive integer.

`timeout` is a duration.

### 25.8 Recorder config

```yaml
recorder:
  arrange_windows: true
```

`arrange_windows` is boolean.

### 25.9 Playback config

```yaml
playback:
  observation_delay: 0s
```

`observation_delay` is a duration used for slow/observation playback pacing. It does not replace normal Selenium waits.

### 25.10 Logging config

```yaml
logging:
  level: INFO
```

Allowed v1 levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

## 26. `credentials.yaml`

### 26.1 Top-level shape

```yaml
version: 1

credentials:
  社内システム:
    username: user001
    password: password123
    domain: CORP

  別システム:
    account: foo
    pin: "1234"
```

Fields:

| Field | Required | Type |
|---|---|---|
| `version` | yes | integer literal `1` |
| `credentials` | yes | map<CredentialGroupName, CredentialEntry> |

### 26.2 CredentialEntry

Unlike ordinary strict object schemas, a credential entry intentionally allows arbitrary non-empty string keys because different systems may use different credential field names.

Every credential value must be a string.

Examples:

```text
username
password
domain
account
pin
client_id
```

The top-level `credentials.yaml` structure remains strict even though each credential entry is an explicit free-form string map.

### 26.3 Credential references

A credential value is referenced as:

```text
${credential.<group>.<key>}
```

Example:

```text
${credential.社内システム.username}
```

Missing group/key references are validation/runtime errors according to the validation stage.

Credential values must never be exposed in normal logs, diagnostics, exception strings, or persisted expanded scenario content.

## 27. Serializer normalization

FlowTape-generated YAML should follow a stable canonical presentation so Git diffs remain readable.

Recommended v1 serializer rules:

- UTF-8
- two-space indentation
- no mandatory `---` document marker
- preserve step order
- preserve locator order
- preserve context traversal order
- emit Japanese text directly
- omit optional `null` fields
- omit fields whose value equals an implicit default where readability does not benefit from explicit output
- normally omit `enabled: true`
- preserve `_meta.id`
- avoid sorting semantic ordered lists
- use a stable documented field order within generated objects

The serializer must preserve semantic meaning even if a manually authored file used a different harmless formatting style before being loaded and re-saved.

## 28. Validation layers

Schema validation is distinct from semantic/runtime validation.

### 28.1 Schema validation

Examples:

- required field missing
- unknown field present
- wrong scalar/list/map type
- unsupported enum
- invalid duration syntax
- invalid action-specific field
- multiple Condition operators in one object
- `index` without `fragile: true`

### 28.2 Cross-file/static semantic validation

Examples:

- referenced credential syntax malformed
- known collection reference points to a single-target definition
- obvious action/target-kind incompatibility where determinable
- invalid page ID reference where page identity is statically known

### 28.3 Runtime/live validation

Examples:

- current page cannot be identified
- target resolves to zero/multiple acceptable elements
- live DOM no longer matches expectation
- state-dependent scenario begins on an unknown page

Runtime validation rules are specified separately.

## 29. Reserved future evolution

FlowTape v1 does not interpret arbitrary unknown keys as future extensions.

New persisted capabilities require one of:

1. a backward-compatible field explicitly added to the current schema definition, or
2. a schema-version increment with documented migration/compatibility behavior.

This prevents old implementations from silently accepting data whose meaning they do not understand.

## 30. Implementation guidance

The Python implementation should model persisted types explicitly rather than passing unvalidated dictionaries through application layers.

A practical implementation may use Pydantic models, dataclasses plus validators, or another explicit typed model layer, provided that the observable validation behavior follows this specification.

Recommended conceptual model families include:

```text
ScenarioDocument
ScenarioNode
ActionNode variants
Condition variants
ElementsDocument
PageDefinition
ElementDefinition
CollectionDefinition
Locator variants
Expectation
ContextStep variants
ConfigDocument
CredentialsDocument
```

Parser, editor, recorder, and player should operate on these validated domain models instead of independently interpreting raw YAML maps.
