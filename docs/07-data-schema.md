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

Runtime execution semantics such as exact action behavior in `実行` / `確認` / `デバッグ`, target fallback behavior, page-resolution behavior, waits, output file lifecycle, collection-member tracking, and retry behavior are defined in `09-runtime-semantics.md`.

Recorder browser-event transport and browser-side capture models are defined in `08-recorder-protocol.md`.

## 2. General schema principles

### 2.1 Strict schemas

FlowTape v1 uses strict persisted schemas.

Unknown fields are validation errors unless a field is explicitly documented as an extension/free-form area.

Example invalid input:

```yaml
- action: click
  target: 保存
  timout: 10s
```

FlowTape must not silently ignore `timout` or reinterpret it as `timeout`.

### 2.2 Schema version is not application version

Each persisted file has its own schema version:

```yaml
version: 1
```

This means version 1 of that file format, not the FlowTape application version.

Scenario, elements, config, and credentials schemas may evolve independently.

### 2.3 Enum values are exact

Enum values use exact spelling and case. FlowTape does not silently normalize unsupported variants.

Examples:

```yaml
mode: 実行
risk: 更新
action: double_click
```

### 2.4 Omission and `null`

For optional fields where no special `null` semantics are documented:

- omitted field = use default / not configured
- explicit `null` = not configured

The serializer should normally omit optional `null` fields.

### 2.5 Ordered structures

The following lists are semantically ordered and must preserve persisted order:

- scenario `steps`
- nested branch/loop `steps`
- output `columns`
- target `locate` candidates
- frame/shadow `context`

A serializer must not reorder them automatically.

### 2.6 UTF-8 and Japanese text

Persisted YAML is UTF-8.

Japanese user-facing names and descriptions are first-class values and should be emitted directly, not escaped as Unicode code points.

## 3. Scalar values

### 3.1 Scalar types

Where this document permits a scalar, supported YAML scalar types are:

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

Internally, the application may normalize durations to a standard Python duration representation.

## 5. Variables and references

### 5.1 Ordinary interpolation

FlowTape supports interpolation using:

```text
${name}
```

Examples:

```yaml
value: ${search_word}
value: "商品名: ${search_word}"
url: "https://example.com/search?q=${search_word}"
```

Runtime loop/context values use the same reference form:

```text
${row}
```

Variable references do not support arbitrary expressions, Python, function calls, or arithmetic.

Invalid examples:

```text
${foo + 1}
${len(items)}
${python:...}
```

### 5.2 Variable identifier grammar

The same ordinary variable-name grammar applies to:

- top-level `variables` keys
- `read.into`
- `for_each.as`
- other future ordinary runtime-variable declarations unless explicitly specified otherwise

A v1 ordinary variable identifier:

- is a non-empty Unicode identifier
- may begin with `_` or a Unicode letter
- subsequent characters may be `_`, Unicode letters, or Unicode decimal digits
- may contain Japanese identifiers
- may not contain whitespace
- may not contain `.` `/` `-` `:` or interpolation punctuation such as `${` / `}`

Examples valid in v1:

```text
search_word
_ticket_id
row2
起票者
チケット番号2
```

Examples invalid in v1:

```text
2row
search-word
foo.bar
foo/bar
foo bar
```

Implementations should validate this using Unicode-aware identifier semantics equivalent to Python-style identifiers rather than ASCII-only regular expressions.

### 5.3 Reserved namespaces

`credential` is a reserved root namespace and may not be declared as an ordinary scenario/runtime/loop variable name.

Credential references use:

```text
${credential.<group>.<key>}
```

Example:

```text
${credential.社内システム.username}
```

Dots are meaningful only inside explicitly defined reserved namespaces such as `credential`; they are not allowed in ordinary variable identifiers.

Namespace/collision behavior during execution is defined in `09-runtime-semantics.md`. In particular, scenario-declared variables must not be silently overwritten by a conflicting runtime/loop declaration.

## 6. `scenario.yaml`

### 6.1 Top-level schema

Conceptual form:

```yaml
version: 1
name: 商品検索
description: 商品を検索するシナリオ
mode: 実行

variables:
  search_word: RTX 5090

outputs:
  ticket_log:
    format: csv
    file: ticket_log.csv
    existing: new
    columns:
      - ticket_id
      - author

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
| `variables` | no | map<VariableName, scalar> | empty |
| `outputs` | no | map<OutputName, OutputDefinition> | empty |
| `steps` | yes | list<Node> | none |

Allowed `mode` values:

```text
実行
確認
デバッグ
```

Recorder/Editor-generated files may explicitly persist `mode: 実行` even though it is the default.

### 6.2 Scenario variables

Scenario-defined variables are scalar-only in v1.

Valid:

```yaml
variables:
  search_word: RTX 5090
  retry_count: 3
  enabled: true
  検索語: GPU
```

Invalid nested values:

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

## 7. Scenario outputs

### 7.1 Purpose

Scenario outputs are user-requested execution artifacts used to collect small amounts of structured or textual data during browser automation.

They are distinct from FlowTape diagnostic/system logs and browser downloads.

### 7.2 Output names

Output names are non-empty UTF-8 strings unique within one scenario.

An `append` action refers to an output by logical name.

### 7.3 OutputDefinition union

A v1 OutputDefinition is exactly one of:

```text
CsvOutputDefinition
JsonlOutputDefinition
TextOutputDefinition
```

`format` is the discriminator.

Supported values:

```text
csv
jsonl
text
```

All output definitions require:

- `format`
- `file`: non-empty relative path string

Optional:

- `existing`: enum, default `new`

Supported `existing` values:

```text
new
append
overwrite
```

Absolute paths are invalid in scenario output definitions.

Path traversal outside the configured output root (for example `../...`) is invalid.

### 7.4 CSV output

```yaml
outputs:
  tickets:
    format: csv
    file: tickets.csv
    existing: new
    columns:
      - id
      - author
      - subject
```

Fields:

| Field | Required | Type |
|---|---|---|
| `format` | yes | literal `csv` |
| `file` | yes | relative path string |
| `existing` | no | enum |
| `columns` | yes | non-empty ordered list<non-empty string> |

Column names must be unique. Column order is semantically significant.

### 7.5 JSON Lines output

```yaml
outputs:
  tickets:
    format: jsonl
    file: tickets.jsonl
    existing: new
```

JSON Lines does not require a fixed column declaration in v1. Each successful structured `append` writes one object record.

### 7.6 Text output

```yaml
outputs:
  processing_log:
    format: text
    file: processed.txt
    existing: new
```

Each successful text `append` writes one textual line.

### 7.7 Output lifecycle schema meaning

- `new`: use a new non-colliding run/result location; previous results are not overwritten
- `append`: append to the selected existing output
- `overwrite`: replace the output at run initialization

Exact runtime path/run-directory semantics are defined in `09-runtime-semantics.md`.

## 8. Scenario nodes

### 8.1 Node union

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

There is no persisted `GroupNode` in schema v1.

### 8.2 Common node fields

All node types may contain:

```yaml
enabled: true
description: 任意の説明
_meta:
  id: 01K...
```

| Field | Required | Type | Default |
|---|---|---|---|
| `enabled` | no | boolean | `true` |
| `description` | no | string | omitted |
| `_meta` | no | NodeMeta | omitted for hand-written YAML |

`description` has no execution meaning in v1.

The serializer should normally omit `enabled: true`.

## 9. Stable node identity

Recorder/Editor-created nodes use a stable persisted ULID:

```yaml
_meta:
  id: 01K6QZX...
```

Visible step numbers are presentation-only.

Hand-written YAML may omit `_meta.id`. FlowTape creates an in-memory ULID and persists it when later saved through the editor.

`_meta` is strict. Its v1 defined field is `id`; unknown fields are invalid until explicitly specified.

Verbose recorder diagnostics, raw DOM snapshots, coordinates, candidate scores, and rejected candidates do not belong in `_meta`.

## 10. Action nodes

### 10.1 Supported v1 actions

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
append
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

Each action accepts only its defined action-specific fields plus common node fields and optional `risk` metadata.

### 10.2 Navigation

`open` requires `url`: non-empty interpolatable string.

`back`, `forward`, and `refresh` have no action-specific required fields.

### 10.3 Click / double click

Required:

- `target`: non-empty string

Optional:

- `within`: runtime context reference string

### 10.4 Input

Required:

- `target`
- `value`: interpolatable scalar/string value

Optional `within`.

### 10.5 Select

Required `target` and exactly one of:

- `value`: interpolatable scalar identifying one option by normalized visible text; existing v1 syntax remains supported.
- `values`: list of non-null interpolatable scalars identifying the complete selected set of a native multi-select. An empty list clears selection. Duplicate normalized texts after expansion are invalid.

Optional `within`. `values` on a single-select is a runtime compatibility error. Option DOM values and indexes are not persisted selection keys.

### 10.6 Read

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

Required:

- `target`
- `source`
- `into`: VariableName

Optional `within`.

`read` stores a runtime value only; it does not write an output itself.

### 10.7 Append

Structured form for CSV/JSONL:

```yaml
- action: append
  output: tickets
  values:
    id: ${id}
    author: ${author}
```

Text form:

```yaml
- action: append
  output: processing_log
  value: "${id}: ${author}"
```

Rules:

- `output` required
- exactly one of `values` or `value`
- CSV/JSONL require `values`
- text requires `value`
- `values` is non-empty map<string, interpolatable scalar>
- for CSV, keys must exactly match declared `columns`; output order follows `columns`
- credential namespace references are forbidden anywhere inside append data

`append` may duplicate records if explicitly re-executed; v1 defines no implicit dedup/upsert.

### 10.8 Upload

Required:

- `target`
- `path`: interpolatable string

Optional `within`.

### 10.9 Key

Provide exactly one of:

```yaml
key: ENTER
```

or:

```yaml
keys:
  - CTRL
  - A
```

`target` is optional. `within` is allowed only when `target` is present.

### 10.10 Hover

Requires `target`; optional `within`.

### 10.11 Drag and drop

Requires:

- `from`: logical target name
- `to`: logical target name

### 10.12 JavaScript dialog actions

`alert_input` requires `value`.

`alert_accept` and `alert_dismiss` have no action-specific fields.

### 10.13 Wait

Requires `until`: WaitCondition.

Optional `timeout`: duration string.

### 10.14 Check

Requires `condition`: Condition.

### 10.15 Window actions

`switch_window.to` supports:

```text
newest
parent
```

`close_window` has no action-specific fields.

## 11. Risk metadata

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

`risk` is metadata in schema v1. Omission means no explicit risk classification was persisted; it is not schema-equivalent to writing `安全`.

## 12. Conditions

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

Target-state conditions contain one logical target name.

Value/text conditions require `target` and `value`.

`page` contains a page ID.

`all` and `any` require non-empty lists of Condition. `not` contains exactly one Condition.

## 13. Wait conditions

`wait.until` accepts ordinary conditions plus:

```yaml
download_complete: "*.csv"
```

Exact completion behavior belongs to runtime semantics.

## 14. Structural nodes

### 14.1 IfNode

Required:

- `if`: Condition
- `then`: list<Node>

Optional `else`: list<Node>.

### 14.2 RepeatNode

Required inside `repeat`:

- `count`: positive integer
- `steps`: list<Node>

### 14.3 WhileNode

A WhileNode combines:

- exactly one Condition operator
- optional `max_iterations`: positive integer
- optional `timeout`: duration
- required `steps`: list<Node>

The condition operator is written directly inside `while` rather than under an additional `condition` key.

Omitted limits use config defaults.

### 14.4 ForEachNode

Required inside `for_each`:

- `target`: collection name
- `as`: VariableName
- `steps`: list<Node>

The target must refer to a collection definition, not an ordinary single element.

Runtime MemberSnapshot/re-identification semantics are defined in `09-runtime-semantics.md` and are not persisted in the scenario.

## 15. `within`

`within` narrows target resolution to a runtime context such as:

```yaml
within: ${row}
```

It is an interpolatable runtime-context reference, not a place for raw CSS/XPath.

## 16. `elements.yaml`

Top-level schema:

```yaml
version: 1
pages: {}
```

Fields:

| Field | Required | Type |
|---|---|---|
| `version` | yes | integer literal `1` |
| `pages` | yes | map<PageId, PageDefinition> |

Page IDs are non-empty UTF-8 strings. Japanese IDs are allowed. Characters such as `/` or `.` do not implicitly define hierarchy.

## 17. PageDefinition and page identification

A page definition supports:

```yaml
identify: ...
elements: ...
collections: ...
```

`identify` is required. `elements` and `collections` are optional maps.

PageCondition is exactly one of:

```text
url
exists
all
any
not
```

URL condition uses exactly one of:

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

Regex is not part of v1.

DOM `exists` page evidence uses a SemanticSelector with supported fields:

```text
role
name
text
label
testid
id
```

At least one field is required.

Exact page-match semantics are defined in `09-runtime-semantics.md`.

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

Allowed v1 kinds:

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

`by` is the discriminator. A locator accepts only fields valid for its family plus common fields.

Common optional fields:

```yaml
fragile: true
index: 3
```

If `index` is present, `fragile: true` is required.

v1 runtime convention is **zero-based index** (`index: 0` means the first matched element). Implementations must not use one-based indexing.

Simple `testid`/`id`/`name`/`label`/`placeholder` locators require `value`.

Role locator:

```yaml
- by: role
  role: button
  name: 保存
```

`role` required; `name` optional.

Text locator:

```yaml
- by: text
  value: 注文を確定
  exact: true
```

`value` required; `exact` defaults to true.

Attribute locator requires `name` + `value`.

CSS/XPath locators require `value`.

Relative locator:

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
- `relation`
- `target`: SemanticSelector

Initial relations:

```text
descendant
row
dialog
form
section
nearby
```

## 20. SemanticSelector

Supported fields:

```text
role
name
text
label
testid
id
```

At least one is required. Unknown selector fields are invalid.

Exact accessible-name/role semantics are shared with `08-recorder-protocol.md` / `09-runtime-semantics.md`.

## 21. Expectation schema

Supported fields:

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

Allowed:

- `tag`: string
- `role`: string
- `input_type`: string
- `visible`: boolean
- `enabled`: boolean
- `editable`: boolean
- `attributes`: map<string,string>

Expectations should remain minimal and meaningful.

## 22. Traversal context

`context` is ordered.

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

Each step is exactly one of FrameContext or ShadowContext.

Mixed sequences such as frame -> shadow -> frame are valid where runtime support permits.

A context step must not contain both `frame` and `shadow` simultaneously.

## 23. CollectionDefinition

Collections are stored separately from `elements` because they intentionally resolve multiple members.

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

An ordinary `elements` definition must not be used as a `for_each` collection merely because its locator matches multiple nodes.

## 24. Fingerprint schema

Fingerprint is diagnostic metadata, not a fuzzy alternate locator.

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
- `attributes`: optional map<string,string>

Full DOM HTML, full ancestor chains, coordinates, and score tables are not persisted here.

## 25. `config.yaml`

Recommended v1 configuration:

```yaml
version: 1

browser:
  type: edge
  executable: null
  profile_path: null

driver:
  path: 'D:\\CompanyTools\\EdgeDriver\\msedgedriver.exe'

credentials:
  path: ./credentials.yaml

timeouts:
  default: 10s
  page_load: 30s

paths:
  scenarios: ./scenarios
  logs: ./logs
  downloads: ./downloads
  outputs: ./outputs

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

`browser.type` supports only `edge` in v1.

`driver.path` is required and must be absolute. FlowTape does not fall back to Selenium Manager or PATH discovery.

Relative paths other than `driver.path` resolve relative to the config directory.

`timeouts` and loop/playback durations use the explicit duration-string format.

`loops.max_iterations` is positive integer.

`recorder.arrange_windows` is boolean.

`logging.level` supports:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

`playback.observation_delay` controls slow/observation pacing and does not replace Selenium waits.

## 26. `credentials.yaml`

Top-level:

```yaml
version: 1
credentials:
  社内システム:
    username: user001
    password: password123
    domain: CORP
```

`credentials` is required map<CredentialGroupName, CredentialEntry>.

Each CredentialEntry intentionally allows arbitrary non-empty string keys because systems differ, but every value must be a string.

Credential references use:

```text
${credential.<group>.<key>}
```

Missing group/key references are validation/runtime errors according to stage.

Credential values must never appear in normal logs, diagnostics, exception strings, expanded persisted scenario content, or result outputs.

## 27. Serializer normalization

FlowTape-generated YAML should use stable canonical presentation:

- UTF-8
- two-space indentation
- no mandatory `---`
- preserve step order
- preserve locator order
- preserve context traversal order
- preserve output column order
- emit Japanese directly
- omit optional nulls
- omit defaults where readability does not benefit
- normally omit `enabled: true`
- preserve `_meta.id`
- stable field order

Re-saving manually authored harmless formatting may canonicalize formatting but must preserve semantic meaning.

## 28. Validation layers

### 28.1 Schema validation

Examples:

- required field missing
- unknown field
- wrong type
- unsupported enum
- invalid duration syntax
- invalid VariableName syntax
- reserved `credential` used as ordinary variable
- invalid action-specific field
- multiple Condition operators
- `index` without `fragile: true`
- absolute/path-traversing scenario output path
- malformed OutputDefinition

### 28.2 Cross-file/static semantic validation

Examples:

- malformed/missing credential reference syntax
- ordinary variable namespace collision determinable statically
- collection reference points to a single-target definition
- obvious action/target-kind incompatibility
- invalid page ID reference where determinable
- `append` references missing output
- CSV append key set differs from declared columns
- credential namespace used in output data

### 28.3 Runtime/live validation

Examples:

- current page unknown/ambiguous
- target zero/multiple acceptable matches
- live DOM expectation mismatch
- context traversal failure
- collection-member disappearance/ambiguity
- output write/header/lifecycle failure
- state-dependent scenario starts from unknown state

Runtime rules are specified in `09-runtime-semantics.md`.

## 29. Reserved future evolution

FlowTape v1 does not interpret unknown keys as future extensions.

New persisted capabilities require either:

1. an explicitly documented backward-compatible field addition, or
2. a schema-version increment with documented migration/compatibility behavior.

Old implementations must not silently accept data whose meaning they do not understand.

## 30. Implementation guidance

Persisted types should be modeled explicitly rather than passed through as unvalidated dictionaries.

Pydantic, dataclasses plus validators, or equivalent are acceptable provided observable validation follows this specification.

Recommended conceptual model families include:

```text
ScenarioDocument
OutputDefinition variants
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

Parser, editor, recorder, and player should operate on validated domain models rather than independently interpreting raw YAML maps.
