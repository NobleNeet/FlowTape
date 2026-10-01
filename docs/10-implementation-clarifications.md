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

## 9. Unknown-page PageDefinition authoring

When Recorder observes a semantic operation on a browser state that cannot be associated uniquely with an existing PageDefinition, the operation must not be discarded and the Recorder must not invent an unreviewed page identity silently.

The v1 authoring flow is:

1. hold the SemanticOperation in a pending-page-association state.
2. generate a proposed PageDefinition from current browser evidence.
3. present the proposed page ID and `identify` conditions to the user.
4. allow the user to edit the proposed page ID and identification conditions.
5. persist the new PageDefinition only after explicit confirmation.
6. associate the pending SemanticOperation with the confirmed page and continue ordinary target creation/recording.

### 9.1 Page ID proposal

The Recorder should propose a readable page ID using stable human-readable evidence where available, in this preference family:

```text
meaningful document/page title
meaningful distinctive heading
stable URL path segment
fallback generated page_<n>
```

The proposal is only a convenience. The user may edit it before persistence.

The final page ID must satisfy the ordinary PageId schema and be unique within the scenario-local registry.

### 9.2 Identification-condition proposal

The Recorder may propose URL and semantic DOM evidence from the current page.

Guidelines:

- prefer stable URL `contains` or `starts_with` evidence over volatile exact URLs containing IDs, tokens, query parameters, or fragments.
- use `url.equals` only when the full URL is reasonably stable and exact identity is desirable.
- prefer distinctive semantic DOM evidence such as heading/control role + accessible name when URL evidence alone is insufficient.
- multiple pieces of evidence may be combined with `all` where that reduces ambiguity without making the page definition fragile.
- never persist a candidate identification rule that already matches multiple registered/current logical pages without explicit user correction.

The user sees the proposed identification conditions before confirmation.

### 9.3 Cancellation

If the user cancels new-page registration, FlowTape must not fabricate a PageDefinition or persist the pending operation under an arbitrary existing page.

Recording stops or remains explicitly blocked at that pending operation with an unresolved-page-authoring state. Previously completed recorded steps remain valid.

Cancellation is an authoring stop, not a Recorder transport desynchronization error.

## 10. `alert_input` semantics

`alert_input` sets the text value of the current JavaScript `prompt` dialog only.

It does **not** accept, dismiss, or otherwise close the dialog.

To enter text and then confirm the prompt, the scenario uses two explicit actions:

```yaml
- action: alert_input
  value: ABC123

- action: alert_accept
```

To enter text and then cancel the prompt, use:

```yaml
- action: alert_input
  value: ABC123

- action: alert_dismiss
```

`alert_input` against a current dialog that does not accept prompt text fails with an action/dialog compatibility diagnostic.

This separation keeps `alert_input`, `alert_accept`, and `alert_dismiss` independently readable and deterministic.

## 11. Variable interpolation and scalar-type preservation

FlowTape distinguishes a pure variable reference from a string template containing a variable reference.

### 11.1 Pure reference

When the entire persisted scalar string consists of exactly one ordinary or credential reference, for example:

```yaml
value: ${count}
```

runtime expansion yields the referenced scalar value with its underlying scalar type preserved where the consuming field permits that type.

Examples:

```yaml
variables:
  count: 3
  active: true
```

A structured JSONL append such as:

```yaml
- action: append
  output: result
  values:
    count: ${count}
    active: ${active}
```

produces JSON scalar types equivalent to:

```json
{"count": 3, "active": true}
```

rather than forcing both values to strings.

### 11.2 Template interpolation

If a scalar contains literal text in addition to references, expansion always produces a string.

Example:

```yaml
value: "count=${count}"
```

expands to:

```text
count=3
```

### 11.3 String-consuming browser fields

Fields whose browser/filesystem semantics require text convert the expanded scalar to its textual representation after interpolation/type resolution.

This includes at least:

```text
open.url
input.value
select.value
select.values entries
upload.path
alert_input.value
key/key-combination textual tokens where applicable
```

Boolean textual conversion uses lowercase YAML/JSON-style text:

```text
true
false
```

`null` is not valid for a required string-consuming field unless that field explicitly documents null semantics; otherwise runtime validation fails before browser mutation.

### 11.4 Output serialization

Output formats behave as follows:

- JSONL preserves expanded scalar types for pure references.
- CSV serializes expanded scalar values to text; `null` becomes an empty cell as already defined by runtime semantics.
- text output serializes the expanded result as text.
- template interpolation always yields text before output serialization.

### 11.5 Values produced by `read`

DOM `read` operations normally produce strings.

A missing requested DOM attribute produces `null` as already defined by runtime semantics.

FlowTape does not automatically parse DOM text such as `"10"`, `"true"`, or `"3.14"` into numeric/boolean types in v1.

Any future explicit type-conversion feature requires a separate schema decision; v1 performs no implicit parsing.

## 12. Final implementation-readiness decision

The pre-implementation specification audit is complete.

The decisions in this document remove identified implementation-time product decisions from:

- destructive-risk execution confirmation
- supported v1 window switching
- page-scoped target rename
- strict config parsing/defaults
- strict frame/shadow context persistence
- collection expectation behavior
- relative locator support boundary
- unknown-page PageDefinition authoring
- JavaScript prompt input behavior
- interpolation/type-preservation behavior

No known product-level decision remains that should require implementation to stop and request user clarification before ordinary v1 development can proceed.

If implementation later exposes a genuinely new contradiction or an unrepresentable real-world workflow, update the specification deliberately rather than inventing undocumented behavior locally.

## 13. Native multi-select extension

The additive v1 `select.values` field denotes the complete selected set and is mutually exclusive with the existing scalar `select.value`. An empty list clears a multi-select. Each entry uses section 11 text conversion and exact matching after shared whitespace normalization. Scalar steps preserve other multi-select choices and never toggle a selected option off. Validate the complete requested set before mutation; ambiguity and missing/disabled options are errors. The Recorder emits all selected texts for a multi-select change rather than treating multiple selections as unsupported. Details are authoritative in `07` (schema), `08` (capture), and `09` (execution). Existing YAML remains valid; older FlowTape builds reject the new field rather than silently reinterpreting it.
