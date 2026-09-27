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

Runtime execution semantics such as exact action behavior in `実行` / `確認` / `デバッグ`, target fallback behavior, page-resolution behavior, waits, output file lifecycle, and retry behavior are defined separately in the runtime-semantics specification.

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

### 2.2 Schema version is not application version

Each persisted file has its own schema version.

```yaml
version: 1
```

means version 1 of that file format. It is not the FlowTape application version.

Scenario, elements, config, and credentials schema versions may evolve independently.

### 2.3 Enum values are exact

Enum values use exact spelling and case. FlowTape does not silently normalize unsupported variants.

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
| `variables` | no | map<string, scalar> | empty |
| `outputs` | no | map<OutputName, OutputDefinition> | empty |
| `steps` | yes | list<Node> | none |

Allowed `mode` values:

```text
実行
確認
デバッグ
```

### 6.2 Scenario variables

Scenario-defined variables are limited to scalar values in v1.

Valid:

```yaml
variables:
  search_word: RTX 5090
  retry_count: 3
  enabled: true
```

Nested arrays/maps are not allowed as scenario variables in v1.

## 7. Scenario outputs

### 7.1 Purpose

Scenario outputs are user-requested execution artifacts used to collect small amounts of structured or textual data during browser automation.

They are distinct from FlowTape diagnostic/system logs.

### 7.2 Output names

Output names are non-empty UTF-8 strings unique within one scenario.

An `append` action refers to an output by this logical name.

### 7.3 OutputDefinition union

A v1 OutputDefinition is exactly one of:

```text
CsvOutputDefinition
JsonlOutputDefinition
TextOutputDefinition
```

The `format` field is the discriminator.

Supported values:

```text
csv
jsonl
text
```

All output definitions require:

- `format`
- `file`: non-empty relative path string

All output definitions may contain:

- `existing`: enum, default `new`

Supported `existing` values:

```text
new
append
overwrite
```

Absolute paths are invalid in scenario output definitions. Environment-specific output roots belong in `config.yaml`.

Path traversal outside the configured output root (for example `../...`) is invalid.

### 7.4 CSV output

Example:

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

Column names must be unique.

The ordered list controls CSV column order.

### 7.5 JSON Lines output

Example:

```yaml
outputs:
  tickets:
    format: jsonl
    file: tickets.jsonl
    existing: new
```

Fields:

| Field | Required | Type |
|---|---|---|
| `format` | yes | literal `jsonl` |
| `file` | yes | relative path string |
| `existing` | no | enum |

JSON Lines does not require a fixed column declaration in v1.

Each successful structured `append` writes one JSON object record.

### 7.6 Text output

Example:

```yaml
outputs:
  processing_log:
    format: text
    file: processed.txt
    existing: new
```

Fields:

| Field | Required | Type |
|---|---|---|
| `format` | yes | literal `text` |
| `file` | yes | relative path string |
| `existing` | no | enum |

Each successful text `append` writes one textual line.

### 7.7 Output lifecycle policy

Schema meanings:

- `new`: use a new non-colliding result location/path for the run; previous results are not overwritten
- `append`: append to the selected existing output
- `overwrite`: replace the output at run initialization

The exact run-directory and filename-generation convention is runtime semantics, not schema.

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

### 8.2 Common node fields

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

## 9. Stable node identity

Recorder/Editor-created nodes use a stable persisted ULID:

```yaml
_meta:
  id: 01K6QZX...
```

Hand-written YAML may omit `_meta.id`.

When loaded, FlowTape creates an in-memory ULID and persists it when the scenario is later saved through the editor.

`_meta` is reserved for explicitly specified FlowTape bookkeeping only. Raw DOM snapshots, coordinates, scores, and rejected candidates do not belong there.

## 10. Action nodes

### 10.1 Action discriminator

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

Each action accepts only fields defined for that action plus common node fields and optional risk metadata where applicable.

### 10.2 Navigation actions

`open` requires:

- `url`: non-empty interpolatable string

`back`, `forward`, and `refresh` have no action-specific required fields.

### 10.3 Click actions

`click` and `double_click` require:

- `target`: non-empty string

Optional:

- `within`: runtime context reference string

### 10.4 Input action

Required:

- `target`
- `value`: interpolatable scalar/string value

Optional:

- `within`

### 10.5 Select action

Required:

- `target`
- `value`

Optional:

- `within`

### 10.6 Read action

Supported `source` forms:

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
- `into`: non-empty runtime-variable name

Optional:

- `within`

`read` stores a runtime value only; it does not itself write to an output.

### 10.7 Append action

`append` has two schema forms according to the referenced output format.

Structured form for CSV/JSONL:

```yaml
- action: append
  output: tickets
  values:
    id: ${id}
    author: ${author}
```

Required:

- `output`: non-empty output name
- `values`: non-empty map<string, interpolatable scalar>

Text form:

```yaml
- action: append
  output: processing_log
  value: "${id}: ${author}"
```

Required:

- `output`
- `value`: interpolatable scalar/string

Rules:

- exactly one of `values` or `value` is allowed
- referenced output must exist in top-level `outputs`
- CSV/JSONL require `values`
- text requires `value`
- for CSV, `values` keys must exactly match the declared `columns` set; the file column order still follows `columns`
- credential namespace references are forbidden anywhere inside `append.value` or `append.values`

`append` is externally observable and may produce duplicate records if re-executed. v1 defines no implicit deduplication/upsert schema.

### 10.8 Upload action

Required:

- `target`
- `path`: interpolatable string

Optional:

- `within`

### 10.9 Key action

A key action provides exactly one of:

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

### 10.10 Hover action

Required:

- `target`

Optional:

- `within`

### 10.11 Drag-and-drop action

Required:

- `from`: logical target name
- `to`: logical target name

### 10.12 JavaScript dialog actions

`alert_input` requires `value`.

`alert_accept` and `alert_dismiss` have no action-specific fields.

### 10.13 Wait action

Required:

- `until`: WaitCondition

Optional:

- `timeout`: duration string

### 10.14 Check action

Required:

- `condition`: Condition

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

`risk` is metadata in schema v1.

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

`wait.until` accepts ordinary conditions plus wait-specific conditions.

The v1 wait-specific condition is:

```yaml
download_complete: "*.csv"
```

The exact completion semantics are defined in runtime semantics.

## 14. Structural nodes

### 14.1 IfNode

Required:

- `if`: Condition
- `then`: list<Node>

Optional:

- `else`: list<Node>

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

Loop limits omitted from the node use configuration defaults.

### 14.4 ForEachNode

Required inside `for_each`:

- `target`: collection name
- `as`: runtime variable name
- `steps`: list<Node>

The referenced target must resolve to a collection definition, not a normal single-element target.

## 15. `within`

`within` narrows resolution to a runtime context, for example:

```yaml
within: ${row}
```

It is not a place for raw CSS/XPath selectors.

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

Page IDs are non-empty UTF-8 strings. Japanese IDs are allowed. `/` and `.` have no implicit hierarchy semantics.

## 17. PageDefinition

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

Single-element targets and collections are intentionally separate because their resolution cardinality differs.

## 18. Page identification schema

Supported v1 PageCondition operators:

```text
url
exists
all
any
not
```

A PageCondition uses exactly one operator.

A URL condition uses exactly one of:

```text
equals
contains
starts_with
```

Regular expressions are not part of v1.

DOM existence checks use a SemanticSelector.

## 19. ElementDefinition

Conceptual fields:

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

## 20. Locator union

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

Common optional fields include:

```yaml
fragile: true
index: 3
```

If `index` is present, `fragile: true` is required.

Simple locator families require `value` where appropriate.

Role locators require `role` and may contain `name`.

Text locators may contain `exact`, default `true`.

Attribute locators require `name` and `value`.

Relative locators require `anchor`, `relation`, and `target`.

Supported initial relative relations:

```text
descendant
row
dialog
form
section
nearby
```

## 21. SemanticSelector

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

## 22. Expectation schema

Supported v1 fields:

- `tag`: string
- `role`: string
- `input_type`: string
- `visible`: boolean
- `enabled`: boolean
- `editable`: boolean
- `attributes`: map<string, string>

Expectations should remain minimal and meaningful.

## 23. Traversal context

`context` is an ordered list of exactly one of:

```text
FrameContext
ShadowContext
```

Mixed sequences such as frame -> shadow -> frame are valid where supported.

A context step must not contain both `frame` and `shadow`.

## 24. CollectionDefinition

Collections are stored separately from `elements`.

Conceptual fields:

| Field | Required | Type |
|---|---|---|
| `context` | no | ordered list<ContextStep> |
| `locate` | yes | non-empty ordered list<Locator> |
| `expect` | no | CollectionExpectation |
| `fingerprint` | no | Fingerprint |

Collection locators intentionally resolve multiple members.

## 25. Fingerprint schema

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

Full DOM HTML, full ancestor chains, coordinates, and score tables must not be persisted as fingerprints.

## 26. `config.yaml`

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

### 26.1 Browser config

`browser.type` v1 supports only `edge`.

`executable` and `profile_path` are optional path strings.

### 26.2 Driver config

`driver.path` is required and must be an absolute filesystem path.

FlowTape does not fall back to Selenium Manager or PATH discovery.

### 26.3 Credentials config

`credentials.path` may be relative to the directory containing `config.yaml`.

### 26.4 Timeout config

`timeouts.default` and `timeouts.page_load` use the duration format defined here.

### 26.5 Runtime paths

```yaml
paths:
  scenarios: ./scenarios
  logs: ./logs
  downloads: ./downloads
  outputs: ./outputs
```

Relative paths are resolved relative to the directory containing `config.yaml` unless another specification explicitly states otherwise.

`outputs` is the root for declared scenario result artifacts. Scenario output definitions may not escape this root.

### 26.6 Loop defaults

`max_iterations` is a positive integer. `timeout` is a duration.

### 26.7 Recorder config

`recorder.arrange_windows` is boolean.

### 26.8 Playback config

`playback.observation_delay` is a duration used for observation pacing. It does not replace Selenium waits.

### 26.9 Logging config

Allowed v1 levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

## 27. `credentials.yaml`

Top-level shape:

```yaml
version: 1
credentials:
  社内システム:
    username: user001
    password: password123
```

Fields:

| Field | Required | Type |
|---|---|---|
| `version` | yes | integer literal `1` |
| `credentials` | yes | map<CredentialGroupName, CredentialEntry> |

A credential entry intentionally allows arbitrary non-empty string keys. Every credential value must be a string.

Credential references use:

```text
${credential.<group>.<key>}
```

Credential values must never be exposed in normal logs, diagnostics, exception strings, persisted expanded scenario content, or scenario output artifacts.

## 28. Serializer normalization

FlowTape-generated YAML should follow a stable canonical presentation.

Recommended v1 serializer rules:

- UTF-8
- two-space indentation
- no mandatory `---` marker
- preserve step order
- preserve output column order
- preserve locator order
- preserve context traversal order
- emit Japanese text directly
- omit optional `null` fields
- normally omit `enabled: true`
- preserve `_meta.id`
- avoid sorting semantic ordered lists
- use a stable documented field order within generated objects

## 29. Validation layers

### 29.1 Schema validation

Examples:

- required field missing
- unknown field present
- wrong scalar/list/map type
- unsupported enum
- invalid duration syntax
- invalid action-specific field
- multiple Condition operators
- `index` without `fragile: true`
- absolute or escaping scenario output path
- duplicate CSV output column
- `append` containing both `value` and `values`

### 29.2 Cross-file/static semantic validation

Examples:

- malformed credential reference
- known collection reference points to a single target
- obvious action/target-kind incompatibility
- `append.output` references an undeclared output
- CSV `append.values` keys do not match declared columns
- text output uses `values`
- structured output uses `value`
- any credential reference appears in an `append` payload

### 29.3 Runtime/live validation

Examples:

- current page cannot be identified
- target resolves to zero/multiple acceptable elements
- live DOM no longer matches expectation
- output file cannot be created/opened/written
- an existing-file policy cannot be satisfied

Runtime rules are specified separately.

## 30. Output data and diagnostics separation

Values read from page DOM are not automatically copied into FlowTape diagnostic logs.

Normal diagnostics should be able to state that `read` or `append` succeeded without including the extracted business/user data itself.

Declared outputs are the explicit destination for such collected data.

This separation does not make arbitrary collected page data secret, but it prevents diagnostics from unintentionally becoming a duplicate data-export channel.

## 31. Authoring boundary for read/output actions

A `read` step is an explicit scenario-authoring intent. It is not inferred merely because the user visually inspected a page.

The editor should create `read` through an explicit flow using the browser picker to bind the DOM target and then choose `text`, `value`, or an attribute source.

Similarly, `append` is created explicitly by selecting or creating an output and mapping runtime values to its record fields.

These authoring clicks are picker/editor operations and are not normal recorded browser-operation steps.

## 32. Reserved future evolution

FlowTape v1 does not interpret arbitrary unknown keys as future extensions.

New persisted capabilities require either an explicitly documented backward-compatible field or a schema-version increment with migration/compatibility rules.

General-purpose scraping transforms, aggregate/group-by expressions, implicit database behavior, and arbitrary expression evaluation are not part of schema v1.

## 33. Implementation guidance

The Python implementation should model persisted types explicitly rather than passing unvalidated dictionaries through application layers.

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

Parser, editor, recorder, and player should operate on validated domain models instead of independently interpreting raw YAML maps.