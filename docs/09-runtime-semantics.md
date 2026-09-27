# FlowTape Runtime Semantics

Status: initial specification before implementation

## 1. Purpose

This document defines how validated FlowTape scenario data is interpreted at runtime by the Player.

It specifies:

- common step execution lifecycle
- `実行` / `確認` / `デバッグ` behavior
- page identification
- target resolution and fallback behavior
- action requirements and expectation filtering
- implicit target waiting
- condition and wait evaluation
- loop semantics
- collection iteration across DOM replacement and navigation
- variable namespaces and secret propagation
- navigation/window/frame/shadow behavior
- output file lifecycle and `append`
- pause/stop/single-step/selected-position playback control
- failure, retry, skip, and restart behavior
- runtime error categories

Persisted syntax is defined in `02-yaml-dsl.md` and `07-data-schema.md`. Target registry structure is defined in `04-target-registry.md`. Recorder-side event capture is defined in `08-recorder-protocol.md`.

## 2. Runtime principles

FlowTape runtime behavior follows these principles:

1. deterministic resolution is preferred over silent recovery
2. ambiguity is an error unless a construct explicitly expects multiple members
3. current DOM state is re-evaluated when required instead of relying on stale Selenium elements
4. user-facing scenario semantics remain separate from browser implementation details
5. non-mutating validation should be useful in `確認` / `デバッグ`
6. mutating browser/file operations are suppressed outside `実行` unless explicitly documented otherwise
7. credentials and secret-derived values must not leak into result files, logs, diagnostics, or exception text
8. runtime failures stop at the affected step unless the user explicitly chooses another recovery action

## 3. Common step execution lifecycle

An enabled ActionNode conceptually executes as:

```text
start step
    -> expand permitted variables/references
    -> establish required browser/window/page context
    -> resolve target if target-dependent
    -> apply persisted expectations
    -> apply action-specific runtime requirements
    -> execute or validate according to mode
    -> perform action-specific completion checks
    -> mark step complete
```

If any required stage fails, the step fails and normal playback stops at that node.

Structural nodes execute their condition/loop semantics and then execute child nodes according to the same rules.

## 4. `enabled`

### 4.1 Disabled action node

`enabled: false` means the node is intentionally skipped.

Runtime behavior:

- do not expand action parameters
- do not resolve page/target
- do not execute browser/file operations
- do not create runtime variables
- do not append output data
- report only that the node was disabled/skipped

### 4.2 Disabled structural node

A disabled `if`, `repeat`, `while`, or `for_each` skips the entire block at runtime.

Its descendants are not runtime-evaluated.

Static schema/cross-file validation still applies before playback.

## 5. Execution modes

Scenario-level `mode` is one of:

```text
実行
確認
デバッグ
```

v1 does not support per-step mode overrides.

Changing mode during active playback is not supported. Stop playback first.

### 5.1 Mode summary

| Operation category | 実行 | 確認 | デバッグ |
|---|---|---|---|
| target resolution | yes | yes | yes + detailed diagnostics/highlight |
| click/input/select/upload/drag-drop/key | execute | validate only | validate + diagnostics |
| navigation actions | execute | do not navigate | do not navigate + diagnostics |
| window-changing actions | execute | do not change | do not change + diagnostics |
| alert mutation | execute | do not mutate | do not mutate + diagnostics |
| `read` | read and assign | read and assign | read and assign + diagnostics |
| `check` | evaluate | evaluate | evaluate + diagnostics |
| `wait` | wait | wait | wait + diagnostics |
| `append` | write output | do not write | do not write; show/retain preview diagnostics |

The exact diagnostic UI is implementation-dependent, but Debug mode must not change matching semantics.

### 5.2 Validation-only mutation rule

In `確認` and `デバッグ`, FlowTape must not perform browser/file operations whose primary purpose is to mutate browser/application/output state.

It still performs the page/target/compatibility checks necessary to decide whether the step is executable.

## 6. Variable namespaces

Runtime values are logically separated into namespaces:

```text
scenario variables
runtime variables created by actions such as read
loop/context variables such as row
credential values
```

A runtime variable must not silently overwrite a scenario-defined variable or loop variable of the same name.

Name collisions that would make resolution ambiguous should be validation/runtime errors.

Repeated assignment to the same runtime variable name is allowed, including inside loops.

## 7. Secret propagation

Credential values are secret values.

Runtime values should carry secret/taint metadata independent of their string representation.

A value derived directly from a credential remains secret.

Secret-derived values must not be emitted to:

- scenario result outputs
- ordinary logs
- diagnostics
- exception messages
- crash-recovery state that is not explicitly secret-safe

An `append` attempting to output a secret-derived value fails with a credential-output prohibition error.

String-pattern inspection alone is not sufficient for enforcing this rule.

## 8. Page identification

### 8.1 Evaluation

When current page identity is required, FlowTape evaluates all PageDefinitions in the scenario-local registry.

Result:

```text
0 matching pages   -> UnknownPage
1 matching page    -> CurrentPage
2+ matching pages  -> AmbiguousPage
```

Registry order is never an implicit tie-breaker.

### 8.2 URL conditions

v1 URL matching is string-based:

- `equals`: complete URL string equality
- `contains`: substring containment
- `starts_with`: prefix match

Query and fragment components remain part of the URL string.

FlowTape does not aggressively normalize distinct URLs into equivalence.

### 8.3 DOM `exists` page condition

A page-identification `exists` semantic selector is true when at least one acceptable matching element exists.

Page identification does not require single-target uniqueness for `exists` evidence.

### 8.4 Page identification scope

v1 page-identification DOM checks operate in the top document only.

They do not recursively search all iframes/shadow roots unless the schema is extended explicitly in a future version.

### 8.5 Page identity caching

Implementations may cache page identity, but must invalidate/re-evaluate when relevant state changes.

At minimum, invalidate on:

```text
full navigation
document replacement
window switch
refresh
back/forward
SPA history change
```

When page identification depends on DOM evidence and the same document may change substantial screen state without navigation, re-evaluation before target-dependent work is preferred over stale caching.

## 9. Target resolution

### 9.1 Resolver pipeline

For a single-target operation:

```text
identify current page
    -> load page-scoped target definition
    -> enter persisted frame/shadow context
    -> apply dynamic `within` scope if present
    -> evaluate persisted locator candidates in order
    -> apply persisted expect filters
    -> apply action-specific runtime requirements
    -> evaluate resulting cardinality
```

### 9.2 Ordered fallback algorithm

For each persisted locator candidate, in order:

1. locate current matches in the current scope
2. apply target expectation filters
3. apply action requirements
4. if exactly one acceptable element remains, select it immediately
5. if zero acceptable elements remain, continue to the next locator
6. if multiple acceptable elements remain, record ambiguity diagnostics and continue to later locators

After all candidates:

```text
some candidate resolved exactly one -> use first such candidate
no unique result, at least one candidate remained multiple -> AmbiguousTarget
all candidates produced zero acceptable matches -> TargetNotFound
```

This means an early ambiguous candidate does not prevent a later fallback from resolving uniquely.

The runtime does not re-score persisted locator candidates. Persisted order is the runtime priority.

### 9.3 No first-match fallback

FlowTape never silently chooses the first DOM element from multiple acceptable matches for an ordinary target.

Explicit positional locators are allowed only when already encoded in the registry as fragile semantics.

## 10. Expectation and action requirements

Persisted `expect` filters locator matches before cardinality acceptance.

Action requirements are separate runtime constraints implied by the action.

Examples:

```text
click          -> visible and enabled
input          -> editable; compatible input/textarea/contenteditable semantics
select         -> compatible selectable target
upload         -> compatible file input
hover          -> visible target
read text      -> resolvable target
```

If persisted `expect` and action semantics are statically contradictory, validation should fail before playback where possible.

If the contradiction depends on live state, runtime resolution fails.

## 11. Implicit target wait

Target-dependent ordinary actions use `config.timeouts.default` as an implicit resolution deadline unless the action has explicitly defined different semantics.

During the deadline, FlowTape may re-evaluate when:

- no acceptable target currently exists
- multiple acceptable targets currently exist
- context traversal is temporarily unavailable during a transition

At deadline:

```text
0 acceptable -> TargetNotFound
2+ acceptable -> AmbiguousTarget
context unavailable -> TargetContextError
```

The polling interval is an implementation detail and is not persisted.

## 12. Stale elements

Player logic must not intentionally retain Selenium WebElements across unrelated scenario steps.

If an element becomes stale inside one action after resolution, the action may restart resolution a small bounded number of times, typically once.

Retries must not become unbounded.

Retrying an action whose side effect may already have occurred requires special caution and must not blindly duplicate irreversible operations.

## 13. `within`

`within` narrows target resolution to a runtime context such as the current `for_each` member.

Conceptually:

```text
page scope
    -> target persisted frame/shadow context
    -> active runtime `within` context
    -> target locator
```

A runtime context is valid only when its corresponding collection/member can currently be re-established in the active browser page/context.

Using `${row}` on a page where that collection member cannot exist is an error, not an instruction to search globally.

## 14. Conditions

### 14.1 `exists`

`exists: target` is true when at least one acceptable target instance exists according to its page/target semantics.

Not found -> false.

Ambiguous -> error.

### 14.2 `not_exists`

Not found -> true.

At least one acceptable target -> false.

Ambiguous -> error.

### 14.3 `visible`, `hidden`, `enabled`, `disabled`

A missing target normally evaluates false for positive predicates such as `visible`/`enabled`.

Ambiguous target resolution is an error.

`hidden` and `disabled` use the target's live state when the target can be resolved. They are not general substitutes for `not_exists`.

### 14.4 Value/text conditions

`text_equals` and `value_equals` require a resolvable single target.

Target not found or ambiguous is an error rather than an automatic false.

### 14.5 Page condition

`page: id` compares the current uniquely identified page ID with the requested page ID.

Unknown or ambiguous current page is an error unless a future condition form explicitly defines otherwise.

### 14.6 Logical operators

`all`, `any`, and `not` use normal boolean composition over condition results.

Errors are not silently converted into false merely to continue boolean evaluation.

## 15. `wait`

A wait repeatedly evaluates its condition until:

```text
condition becomes true -> success
explicit timeout expires -> WaitTimeout
user stops playback -> stopped
```

The poll interval is an implementation detail.

Temporary not-found or ambiguous states may be re-evaluated during the wait window.

If the deadline expires while the condition remains ambiguous, diagnostics should preserve the ambiguity as the final reason.

`wait` must not be implemented as a fixed sleep that ignores the requested condition.

## 16. Action semantics

### 16.1 `open`

In `実行`, expand the URL and navigate with the configured browser driver.

Browser/page-load timeout uses `timeouts.page_load` where applicable.

FlowTape does not require the destination to match a registered PageDefinition merely for `open` to succeed.

A later target-dependent step may require page identification.

In `確認` / `デバッグ`, validate/interpolate the URL but do not navigate.

### 16.2 `back`, `forward`, `refresh`

In `実行`, invoke the corresponding browser navigation operation.

After execution, invalidate current page identity and stale browser-context caches.

In validation/debug modes, do not navigate.

### 16.3 `click`

Resolve a compatible visible/enabled target and perform one click in `実行`.

Successful completion of the click operation is sufficient for the step itself.

FlowTape does not infer that a particular destination page must appear afterward.

If the scenario requires a resulting state/page, express it with a later `wait` or `check`.

### 16.4 `double_click`

Resolve a compatible target and perform a Selenium-level double-click in `実行`.

The same page/target resolution rules as click apply.

### 16.5 `input`

`input` means replace/set the editable target's value rather than append arbitrary text to its current contents.

Implementation may clear/select-all and enter the requested value according to target type.

After input, FlowTape should verify the resulting value where reliable browser semantics permit.

In validation/debug modes, resolve and validate editability but do not change the value.

### 16.6 `select`

v1 interprets `value:` primarily as exact visible option text.

If no option matches, the step fails.

If multiple options have the same acceptable visible text and cannot be distinguished deterministically, selection is ambiguous and fails.

Future schema versions may add explicit select-by-value/index semantics.

### 16.7 `read`

Resolve one target and obtain:

- `text`: normalized visible text
- `value`: current DOM value
- `attribute`: current attribute value

An empty string is a successful value.

A missing requested attribute yields `null` rather than a target-resolution error.

The result is assigned to the named runtime variable.

`read` executes in all three scenario modes because it is non-mutating and may be required by later checks/preview logic.

### 16.8 `upload`

In `実行`, resolve a compatible DOM file input and send the expanded filesystem path through Selenium.

FlowTape does not automate the native OS chooser.

Validation/debug modes validate compatibility and path syntax without performing the upload.

### 16.9 `key`

In `実行`, send the configured key or key combination either to the resolved target or the current browser context when targetless.

Validation/debug modes validate key syntax/target compatibility without sending the key.

### 16.10 `hover`

In `実行`, move pointer focus over the resolved target using Selenium/ActionChains-compatible behavior.

Validation/debug modes resolve and validate the target without changing pointer state.

### 16.11 `drag_drop`

In `実行`, resolve source and destination and attempt the supported ActionChains-style drag/drop behavior.

Unsupported custom drag implementations fail explicitly rather than falling back to arbitrary script injection without specification.

### 16.12 JavaScript dialogs

`alert_accept`, `alert_dismiss`, and `alert_input` operate on the current JavaScript dialog when present.

In `確認` / `デバッグ`, FlowTape may validate dialog presence/type where possible but must not accept/dismiss/mutate the dialog.

## 17. Loops

### 17.1 `repeat`

Execute the body exactly `count` times unless a child step fails or playback is stopped.

### 17.2 `while`

`while` is a pre-test loop:

```text
evaluate condition
false -> finish normally
true  -> execute body -> repeat
```

`max_iterations` and `timeout` are safety limits.

If the condition remains true and a configured safety limit is reached, the loop fails with `LoopLimitExceeded`; reaching a safety cap is not treated as normal completion.

### 17.3 Loop child failure

A child failure stops the loop and normal playback at that child node.

FlowTape does not silently continue with the next iteration.

## 18. `for_each` collection semantics

### 18.1 Initial collection snapshot

At loop start, resolve the collection and establish the ordered logical member set that will be processed by this loop execution.

Iteration order is current DOM order.

A collection containing zero members completes normally with zero iterations.

Members added after loop start are not added to the current loop execution.

### 18.2 Do not retain long-lived WebElements

FlowTape must not treat the initial Selenium WebElements as stable iteration identities across navigation or DOM replacement.

Instead it creates runtime-only MemberSnapshots that contain enough stable evidence to re-identify each original logical member later.

Useful member identity evidence may include:

```text
stable href
stable id/testid/name
meaningful attributes
semantic/visible text
other small member fingerprint evidence
original ordinal as weak supporting data
```

MemberSnapshots are not persisted to scenario or elements files.

### 18.3 Re-identify each member

At the start of each iteration that requires the collection page/context:

1. re-identify the collection's page
2. re-resolve the collection definition against the current DOM
3. find the original MemberSnapshot's corresponding current member
4. bind the loop variable such as `${row}` to that current member context
5. execute the body

### 18.4 Re-identification priority

Prefer stable member evidence over ordinal position.

Ordinal may be used as supporting evidence but must not silently redirect execution to a different member when stronger fingerprint evidence conflicts.

### 18.5 Collection changes during execution

If new members appear after loop start, ignore them for the current loop.

If an unprocessed original member disappears before its iteration, fail explicitly with a collection-member-not-found diagnostic.

If member order changes but an original member can still be uniquely identified from its snapshot evidence, continue with that member.

If an original member cannot be uniquely re-identified, fail with a collection-member-ambiguity diagnostic.

### 18.6 Navigation away and back

A `for_each` body may navigate to another page and later return.

FlowTape does not automatically issue `back`/navigation operations merely because the next iteration requires the collection page.

The scenario must explicitly return and, where useful, wait/check the collection page.

Example:

```yaml
- for_each:
    target: チケット一覧/行
    as: row
    steps:
      - action: click
        target: チケットを開く
        within: ${row}
      - action: wait
        until:
          page: ticket_detail
      - action: read
        target: 起票者
        source: text
        into: author
      - action: back
      - action: wait
        until:
          page: ticket_list
```

If the next iteration begins while the required collection context is unavailable, fail rather than silently navigating.

### 18.7 Loop-variable DOM lifetime

The logical loop variable remains defined for the iteration, but its DOM scoping capability is valid only while the associated member can be re-established in the current collection page/context.

Using `within: ${row}` on an unrelated detail page is an error.

## 19. Window semantics

### 19.1 Window creation order

FlowTape tracks its own observed window creation order.

`switch_window: newest` means the newest currently alive window according to FlowTape runtime tracking, not arbitrary Selenium handle-list order.

### 19.2 Parent relationship

When deterministically observable, FlowTape tracks a runtime parent relation between newly opened windows and the window that caused/opened them.

`switch_window: parent` uses this FlowTape relation.

`window.opener` may be supporting evidence but is not the only required runtime source.

### 19.3 Automatic popup return

If the current popup/window disappears by itself:

1. detect the missing current handle
2. if its known FlowTape parent still exists, switch to that parent
3. invalidate/re-identify current page state
4. continue

If a unique return target cannot be determined, fail.

### 19.4 `close_window`

In `実行`, close the current window.

After close, automatically return only to a known surviving FlowTape parent.

If no known parent exists, do not arbitrarily choose among remaining windows; fail with browser-context diagnostics.

Validation/debug modes do not close the window.

## 20. Frame and Shadow DOM context

Target context traversal is ordered and must follow the persisted `context` sequence exactly.

If any frame/shadow traversal step cannot be established, report a context-specific failure rather than reducing it to generic target-not-found.

Open Shadow DOM is supported where specified by the target definition and browser adapter.

Closed Shadow DOM is unsupported in v1 unless a future implementation adds an explicit supported mechanism.

## 21. Output runtime semantics

### 21.1 Separation from logs

Scenario outputs are user-requested execution artifacts and are separate from FlowTape diagnostic/system logs.

### 21.2 Output root

Scenario output files are rooted under `config.paths.outputs`.

Scenario output definitions provide relative file paths only.

### 21.3 Run identity

Each playback execution has a runtime run identity.

For `existing: new`, FlowTape creates a new run-specific output directory, recommended conceptually as:

```text
outputs/
  <scenario-safe-name>/
    <timestamp>-<run-id>/
      ticket_log.csv
```

Exact safe-name/timestamp formatting is an implementation detail as long as run outputs do not overwrite prior runs.

### 21.4 `existing: new`

Each new run creates new output storage and does not reuse the previous run's file.

### 21.5 `existing: append`

Use/reuse the designated output file and append records.

For CSV:

- if file does not exist, create it and write the declared header
- if file exists, validate its header against declared `columns`
- header mismatch -> `OutputSchemaMismatch`

### 21.6 `existing: overwrite`

Truncate/create the output file once at run initialization, not once per `append` step.

For CSV, write the header at run initialization.

### 21.7 `append` execution

For a structured output:

```text
expand values
    -> reject secret-derived values
    -> validate output record against OutputDefinition
    -> serialize one record
    -> append to file
    -> flush userspace buffer
    -> mark step success
```

For text output, append the expanded line/value according to the text-output format rules.

A successful `append` means the record has been handed to the output stream and flushed from the application's userspace buffer.

OS-level `fsync` after every record is not required by v1.

### 21.8 CSV record validation

CSV `values` keys must exactly match the declared columns according to the data-schema rules.

Runtime-expanded values are serialized in declared column order.

`null` becomes an empty CSV cell.

### 21.9 JSONL and text

JSONL appends one JSON object per successful append step.

Text appends one expanded text value/line per successful append step.

### 21.10 Validation/debug behavior

In `確認` / `デバッグ`, `append` validates:

- referenced output exists
- record shape is valid
- variable expansion succeeds
- no secret-derived value would be emitted

It does not modify the output file.

Debug mode may display a preview of the record that would be written, subject to secret redaction rules.

### 21.11 Retry and duplicate risk

A completed `append` is not idempotent by default.

Explicitly re-running an already successful append step may duplicate a record.

The UI should warn when the user requests such a retry.

If an output write produces an uncertain outcome (for example the application cannot determine whether a record was committed before an I/O error), FlowTape must not blindly auto-retry in a way that may duplicate the record.

v1 does not provide automatic deduplication/upsert semantics.

## 22. Runtime variables from `read`

A runtime variable assigned by `read` may be overwritten by a later `read` using the same runtime variable name.

This is required for normal loop usage.

Runtime variables are not automatically persisted after playback ends unless another explicit feature exports them.

## 23. Playback pacing and control

### 23.1 Slow playback

Slow playback inserts the configured observation delay only after normal step completion.

It must not replace proper target/wait/navigation synchronization with fixed sleeps.

### 23.2 Pause

Pause should occur at safe boundaries.

FlowTape guarantees pausing between action steps.

Long-running wait/loop polling should observe pause requests and suspend cooperatively.

A Selenium/browser call already in progress is not forcibly interrupted unless the browser adapter explicitly supports safe cancellation.

### 23.3 Stop

Stop behavior:

- between steps: stop immediately
- during wait/loop polling: stop promptly through cooperative checks
- during an active Selenium/native call: stop after the call returns or fails

Stopping playback does not close the browser by default.

### 23.4 Single-step

User-facing single-step advances by one executable ActionNode.

Structural-node evaluation may occur as necessary to determine the next action.

Errors during structural evaluation still stop playback normally.

### 23.5 Execute until selected position

`選択位置まで` stops immediately before the selected node is executed.

This allows the user to inspect or modify that selected node before single-stepping it.

The UI should make this boundary clear.

### 23.6 Playback-mode change

Changing `実行`/`確認`/`デバッグ` during active playback is unsupported in v1.

Stop playback before changing mode.

## 24. Failure state

When a step fails, preserve enough non-secret diagnostic context to explain the failure.

Useful runtime failure data includes:

```text
node id
action/structural node kind
current page id or page-identification failure
window/context information
logical target name
locator candidates attempted
match counts
expect/action-requirement rejection reasons
error category
timestamp
```

Do not include credential/secret plaintext.

The failed node remains selected/marked in the UI for repair/retry workflows.

## 25. Retry

Retrying a failed target-dependent action must perform page and target resolution again.

Do not reuse the previous Selenium WebElement.

Automatic retry is allowed only where the runtime can do so without unsafe duplicate side effects.

User-requested retry of a mutating step may require warning depending on whether prior side effects could already have occurred.

## 26. Skip

Skip occurs only through explicit user action.

The Player does not automatically skip failed steps.

The UI may warn that later browser state may no longer match scenario assumptions.

## 27. Restart

Restarting from the beginning creates a fresh runtime execution context:

- reinitialize runtime variables
- reinitialize loop/member snapshots
- reinitialize runtime window-parent tracking
- invalidate page/target caches

For outputs:

- `existing: new` starts a new run-specific output directory
- `append` continues according to its declared append semantics
- `overwrite` reinitializes according to run-start overwrite rules

FlowTape does not attempt to rewind an existing output artifact to a previous step boundary.

## 28. Editing while paused

If only not-yet-executed steps are modified, playback may resume after validation.

If an already-executed step is modified, the current live browser state still reflects the old execution.

The UI must warn and allow at least:

- restart from the beginning
- continue from current live browser state knowingly

FlowTape does not pretend retroactive edits changed browser/output state already produced.

## 29. Browser/page transitions and explicit waits

Browser mutations such as click, input, or key may trigger asynchronous page/application state changes.

FlowTape does not infer arbitrary business-level completion from the initiating action.

Scenarios should use explicit `wait`/`check` steps when the next operation depends on a resulting page or DOM state.

This keeps implicit Selenium synchronization separate from explicit scenario semantics.

## 30. Error categories

Implementations may use different concrete exception class names, but runtime diagnostics should distinguish at least:

```text
ScenarioValidationError
UnknownPage
AmbiguousPage
TargetNotFound
AmbiguousTarget
TargetExpectationError
TargetContextError
ActionCompatibilityError
WaitTimeout
LoopLimitExceeded
CollectionMemberNotFound
CollectionMemberAmbiguous
CollectionContextUnavailable
BrowserContextError
OutputWriteError
OutputSchemaMismatch
CredentialOutputForbidden
UnsupportedOperationError
```

Errors should identify the affected node and logical target/output where relevant.

## 31. Implementation guidance

Recommended runtime components include conceptually:

```text
Player
ExecutionContext
PageIdentifier
TargetResolver
ConditionEvaluator
LoopExecutor
CollectionRuntime
WindowContextManager
OutputManager
SecretValue / taint tracking
BrowserAdapter
```

Domain/runtime components should avoid leaking Selenium WebElements into long-lived scenario/editor state.

Browser implementation details should remain behind adapter/service boundaries where practical.

## 32. Determinism rule

When FlowTape cannot determine uniquely:

- the current page
- the intended target
- the current collection member
- the return window/context
- the output schema/record meaning

it fails explicitly rather than choosing an arbitrary plausible candidate.

This rule takes precedence over convenience fallbacks throughout runtime execution.
