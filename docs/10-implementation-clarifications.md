# FlowTape v1 Implementation Clarifications

Status: implementation-blocking clarifications finalized before implementation

## 1. Purpose and precedence

This document resolves a small set of remaining v1 ambiguities discovered during the final pre-implementation audit.

For the subjects explicitly covered here, this document is the authoritative clarification and takes precedence over broader or earlier wording in `02-yaml-dsl.md` through `09-runtime-semantics.md`.

This document does not introduce a new schema version. It narrows and completes the intended meaning of schema version 1.

## 2. Destructive-risk confirmation

### 2.1 Runtime meaning

`risk` remains metadata at the Player/domain execution-semantics layer.

The Player must not reject an otherwise executable ActionNode merely because it contains:

```yaml
risk: 破壊的
```

Target/page validation and ordinary execution semantics remain unchanged.

### 2.2 UI execution gate

When playback is initiated through the FlowTape desktop UI in `実行` mode, an enabled ActionNode with:

```yaml
risk: 破壊的
```

must pass an application/UI confirmation gate immediately before that action is executed.

The confirmation gate belongs to the application/UI orchestration layer, not to target resolution or browser-action semantics.

The initial v1 configuration is:

```yaml
safety:
  destructive_confirmation: always
```

Supported v1 values are:

```text
always
once_per_run
off
```

Meaning:

- `always`: confirm before every enabled `risk: 破壊的` action in `実行` mode.
- `once_per_run`: the first destructive action in one playback run requires confirmation; after confirmation, later destructive actions in the same run do not ask again.
- `off`: no risk-based confirmation gate is added.

Default:

```text
always
```

`確認` and `デバッグ` do not show this execution confirmation because mutating browser/file operations are already suppressed by their execution-mode semantics.

A user cancellation at the confirmation gate leaves playback paused/stopped before the destructive action; the action is not marked successful and no browser mutation is performed.

## 3. Window/tab switching scope in v1

FlowTape v1 formally supports only the following deterministic scenario-level window transitions:

```yaml
- action: switch_window
  to: newest
```

and:

```yaml
- action: switch_window
  to: parent
```

Their meanings remain those defined in `09-runtime-semantics.md`:

- `newest`: newest currently alive FlowTape-observed window according to FlowTape creation tracking.
- `parent`: known surviving FlowTape parent of the current window.

The automatic return to a known parent after the current popup closes remains supported.

### 3.1 Explicit non-support

v1 does not define a persisted scenario syntax for arbitrary switching to:

- a sibling window/tab
- an older unrelated existing window/tab
- a window by title
- a window by URL
- a window by Selenium handle
- a window by positional index

The Recorder must not invent unsupported `switch_window` syntax or silently approximate such a switch as `newest` or `parent`.

If the user manually performs a window switch that cannot be represented by one of the supported deterministic forms, recording enters an explicit unsupported/unrepresentable-operation state and asks the user to adjust the workflow or stop recording. It must not persist a misleading scenario step.

Future schema versions may add stable logical window aliases if real workflows require arbitrary existing-window switching.

## 4. Page-scoped target rename semantics

A target name is unique only within one page scope, while ordinary scenario target references do not persist a page ID. Therefore GUI rename must not perform an unsafe global text replacement.

Renaming a target through FlowTape follows these rules:

1. rename the registry key only inside the selected PageDefinition.
2. analyze known scenario references to the old logical target name.
3. automatically update only references whose applicable page scope can be determined statically and uniquely to be the renamed page.
4. if any reference to the old name cannot be statically attributed to exactly one page scope, do not guess.
5. if ambiguous references exist, stop the rename transaction before persistence and require explicit user resolution.

The UI must show the ambiguous reference locations and allow the user to decide which references belong to the renamed page before committing the transaction.

A rename is atomic: either the registry rename plus all confirmed scenario-reference updates are persisted together, or none of them are persisted.

A simple global replacement of the target string is forbidden.

## 5. `config.yaml` strict v1 schema completion

Because FlowTape v1 uses strict persisted schemas, config fields require explicit required/default behavior.

Top-level v1 fields are:

```text
version
browser
driver
credentials
timeouts
paths
loops
recorder
playback
logging
safety
```

Unknown top-level or nested config fields are validation errors.

### 5.1 Required fields

The only values that must be explicitly present are:

```yaml
version: 1

driver:
  path: <absolute path>
```

`driver.path` must be an absolute filesystem path.

### 5.2 Defaults

All other config sections/fields are optional and use these defaults when omitted:

```yaml
browser:
  type: edge
  executable: null
  profile_path: null

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

safety:
  destructive_confirmation: always
```

If a section is present partially, omitted fields inside that section still use their defaults.

Relative config paths other than `driver.path` resolve relative to the directory containing `config.yaml`.

`browser.type` supports only `edge` in schema v1.

Supported logging levels remain:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

## 6. FrameContext and ShadowContext strict schema

Each persisted context step contains exactly one of `frame` or `shadow`.

### 6.1 FrameContext

A frame context contains exactly one selector key from:

```text
id
name
css
```

Examples:

```yaml
context:
  - frame:
      id: payment-frame
```

```yaml
context:
  - frame:
      name: payment
```

```yaml
context:
  - frame:
      css: iframe.payment-frame
```

Each selector value is a non-empty string.

Multiple frame selector keys in one FrameContext are invalid in v1.

Frame XPath, positional frame index, and nested general Locator objects are not part of FrameContext v1.

### 6.2 ShadowContext

A shadow context has exactly one supported field:

```text
css
```

Example:

```yaml
context:
  - shadow:
      css: app-shell
```

The value is a non-empty CSS selector string identifying the shadow host in the current traversal scope.

Only open Shadow DOM is supported in v1.

## 7. CollectionExpectation

`CollectionExpectation` uses the same persisted field vocabulary and field meanings as ordinary `Expectation`:

```text
tag
role
input_type
visible
enabled
editable
attributes
```

The difference is cardinality semantics, not schema shape.

For a CollectionDefinition:

1. resolve the collection locator candidate.
2. apply `CollectionExpectation` independently to each matched member.
3. discard members that fail the expectation.
4. preserve DOM order of the remaining members.
5. zero remaining members is a valid empty collection.
6. multiple remaining members are expected and are not an ambiguity error.

CollectionExpectation must not be used to choose one arbitrary member from several matches.

## 8. Relative locator scope for initial v1 implementation

The initial v1 implementation formally supports these relative relations:

```text
descendant
row
dialog
form
```

Although earlier design documents list `section` and `nearby` as desirable relations, they are deferred until their cross-site semantics are specified precisely enough for Recorder and Player to reproduce identically.

A strict v1 parser/validator must therefore reject persisted relative locators using:

```text
section
nearby
```

until a later specification explicitly promotes them into the supported schema.

### 8.1 `descendant`

Resolve the anchor SemanticSelector, require one unambiguous anchor scope, then resolve the target SemanticSelector among DOM descendants of that anchor.

### 8.2 `row`

Resolve the anchor, then determine the nearest containing row context in this priority:

1. nearest ancestor with computed/explicit ARIA role `row`
2. nearest HTML `<tr>` ancestor

Resolve the target SemanticSelector within that row context.

If no row context exists, that relative candidate produces zero acceptable matches.

### 8.3 `dialog`

Resolve the anchor, then determine the nearest containing dialog context in this priority:

1. nearest ancestor with computed/explicit role `dialog` or `alertdialog`
2. nearest HTML `<dialog>` ancestor

Resolve the target within that dialog context.

### 8.4 `form`

Resolve the anchor, then use the nearest containing HTML `<form>` ancestor as the scope and resolve the target within it.

If no containing form exists, that relative candidate produces zero acceptable matches.

### 8.5 Anchor ambiguity

For all supported relative relations, if the anchor SemanticSelector itself resolves to multiple acceptable anchor elements and the relation cannot yield exactly one deterministic scope, the relative candidate is ambiguous. It must not silently use the first anchor.

## 9. Implementation readiness effect

The decisions in this document are intended to remove implementation-time product decisions from the following areas:

- destructive-risk execution confirmation
- supported v1 window switching
- page-scoped target rename
- strict config parsing/defaults
- strict frame/shadow context persistence
- collection expectation behavior
- relative locator support boundary

Implementation code and tests should use these rules rather than inventing alternate behavior locally.
