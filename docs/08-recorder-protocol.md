# FlowTape Recorder Protocol

Status: initial specification before implementation

## 1. Purpose

This document defines the internal protocol between the Selenium-controlled browser and the Python Recorder.

It specifies:

- injected browser-side JavaScript responsibilities
- event transport from browser to Python
- capture-event identity and document identity
- lightweight and detailed element snapshots
- event normalization into semantic browser operations
- text input, IME, and commit boundaries
- click and double-click normalization
- navigation/window/frame/shadow observation
- JavaScript reinjection behavior
- Picker/Rebind/Collection Picker behavior
- recorder synchronization and failure handling

This protocol is internal runtime behavior. It is not part of the persisted `scenario.yaml` or `elements.yaml` schemas.

The persisted DSL and schema are defined in `02-yaml-dsl.md` and `07-data-schema.md`. Locator generation is defined in `05-locator-generation.md`. Exact playback semantics are defined separately in `09-runtime-semantics.md`.

## 2. Architectural boundary

Recorder processing follows this conceptual pipeline:

```text
browser DOM/browser state
    -> injected observer JavaScript
    -> RawCaptureEvent queue
    -> Python polling
    -> EventNormalizer
    -> SemanticOperation
    -> Element Capture Engine / target binding
    -> Scenario Node + elements.yaml update
```

A raw DOM event must not map directly one-to-one to a Scenario Node.

The browser side is responsible for observing browser/DOM facts and capturing enough transient information before it disappears.

The Python side is responsible for semantic normalization, target generation, registry reuse, scenario editing, and persistence.

## 3. Transport model

### 3.1 JavaScript queue and Python polling

FlowTape v1 uses an injected browser-side event queue that is drained by Python through Selenium.

Conceptually:

```text
DOM event
    -> injected JavaScript
    -> window.__flowtape.events[]
    -> Python executes script to drain queue
```

The polling interval is an implementation parameter and is not persisted in scenario files.

A practical initial value may be approximately 50-100 ms, but correctness must not depend on one exact polling interval.

The protocol must not depend on browser console logs, browser extensions, or mandatory Chrome DevTools Protocol event transport.

### 3.2 Drain semantics

A queue-drain operation should atomically return currently queued events and remove those returned events from the browser-side queue.

Python must not intentionally process the same RawCaptureEvent twice.

If a transport retry makes duplicate delivery possible, event identity described below must allow Python to discard duplicates safely.

## 4. Protocol versioning

Injected JavaScript exposes a protocol version independent from persisted YAML schema versions.

Conceptually:

```text
protocol_version = 1
```

Every RawCaptureEvent carries or inherits the active protocol version.

A Python Recorder and injected script with incompatible protocol versions must fail explicitly with a protocol-version diagnostic rather than silently continuing.

## 5. Recorder session identity

The Python Recorder maintains one RecorderSession while a recording/editing browser session is active.

Conceptual state includes:

```text
session_id
interaction_mode
recording_enabled
known_window_handles
active_window_handle
document instances
last consumed event sequence per document
pending click state
pending input state
pending navigation state
scenario insertion position
```

This state is runtime-only and is not persisted into ordinary scenario YAML.

## 6. Document identity

### 6.1 `document_instance_id`

Each injected document instance receives a random runtime identifier when FlowTape initializes the script in that document.

Every event from that document includes:

```text
document_instance_id
```

This identity is required because:

- a full navigation replaces the document
- the URL may remain the same after reload
- SPA navigation may change URL without replacing the document
- multiple frames can contain different documents simultaneously

A document instance ID is not a page ID and is not persisted into `elements.yaml`.

### 6.2 Event sequence

Each injected document maintains a monotonically increasing event sequence number:

```text
event_seq
```

The pair:

```text
(document_instance_id, event_seq)
```

uniquely identifies a RawCaptureEvent within one Recorder session.

A UUID per event is unnecessary in v1.

## 7. RawCaptureEvent

### 7.1 Purpose

RawCaptureEvent represents an observed browser-side fact before semantic normalization.

It is a serializable internal DTO, not a persisted FlowTape file format.

Conceptual form:

```yaml
protocol_version: 1
document_instance_id: "runtime-document-id"
event_seq: 184
timestamp: 123456.789
type: click

window_context:
  frame_path: []

document:
  url: https://example.com/tickets/123
  title: Ticket 123

target:
  element_ref: 42
  snapshot:
    ...

data:
  button: 0
  modifiers: []
```

Exact Python/JavaScript field names may differ if the implementation preserves these semantics.

### 7.2 Required common concepts

A RawCaptureEvent must provide enough information to determine:

- protocol version
- source document instance
- event order
- browser timestamp/order context
- event type
- source window/frame context
- current URL
- event-specific data
- target snapshot when the event is target-dependent

## 8. Event types

The initial browser observer should support at least the raw events needed to derive:

```text
click
double-click
text/input changes
select changes
meaningful keyboard operations
focus loss / input commit
IME composition
page/document lifecycle
SPA history changes
picker hover/selection
```

Useful native browser events include:

```text
click
dblclick
input
change
keydown
focusout
compositionstart
compositionend
pagehide
beforeunload
popstate
```

`pointerover` or equivalent hover observation is enabled for picker/highlight workflows.

`mousedown` and `mouseup` may be observed for diagnostics or specialized normalization, but they do not normally become Scenario steps.

## 9. Event listener behavior

### 9.1 Capture phase

Important Recorder listeners should normally be installed in capture phase so that application code calling `stopPropagation()` does not prevent FlowTape from observing the operation where browser behavior permits.

Conceptually:

```javascript
addEventListener(type, handler, true)
```

### 9.2 Non-interference in Record mode

In normal Record mode, FlowTape observes user operations but must not change the page's behavior.

Recorder listeners must not normally call:

```text
preventDefault
stopPropagation
stopImmediatePropagation
```

Record mode is observational.

## 10. Element references

### 10.1 Short-lived `element_ref`

When later detail capture may be useful, injected JavaScript may assign a short-lived runtime reference to a DOM element.

The recommended model uses JavaScript-side weak associations such as:

```text
WeakMap<Element, element_ref>
```

The reference is meaningful only within the current document instance.

### 10.2 Do not mutate application elements for identity

FlowTape must not add identity attributes such as:

```html
data-flowtape-id="..."
```

to application DOM elements merely to remember them.

FlowTape-owned overlays may use FlowTape-specific marker attributes because those nodes are created by FlowTape itself.

## 11. Snapshot model

### 11.1 Two-stage capture

FlowTape uses two levels of target information.

#### Stage 1: lightweight event snapshot

Captured synchronously at or immediately around the meaningful event.

It contains enough information to avoid losing the target when a click immediately navigates away.

Typical data includes:

```text
tag
id
name
type
explicit/computed role
accessible name
visible text
important attributes
basic state
minimal frame/shadow context
```

#### Stage 2: detailed capture snapshot

Requested when the EventNormalizer or Element Capture Engine determines that the operation needs target registration/rebinding/locator generation.

It may add:

```text
meaningful ancestors
heading context
form context
dialog context
row/list context
nearby text
frame traversal evidence
shadow traversal evidence
candidate-generation support data
```

Stage 2 is best-effort because the original DOM may disappear after navigation.

### 11.2 Navigation-loss rule

For target-dependent events that can immediately cause navigation, the lightweight Stage 1 snapshot must be captured before the old document can disappear.

The Recorder must not rely on a later Selenium lookup of the clicked element as the sole source of target information.

This rule specifically prevents loss of information in sequences such as:

```text
user clicks link
    -> navigation starts immediately
    -> old DOM is destroyed
    -> Python polls after destruction
```

The click event must still contain enough target evidence for target generation or diagnostics.

## 12. ElementSnapshot contents

ElementSnapshot is normalized capture data used by locator generation and target naming.

Conceptual structure:

```yaml
tag: button

attributes:
  id: checkout-submit
  name: null
  type: submit
  aria-label: 注文を確定
  data-testid: checkout-submit
  class:
    - button
    - primary

semantics:
  explicit_role: button
  computed_role: button
  accessible_name: 注文を確定
  label: null

text:
  visible_text: 注文を確定

state:
  visible: true
  enabled: true
  editable: false
  checked: null
  selected: null

relations:
  heading: ご注文内容
  form: 購入フォーム
  dialog: 注文確認
  row: null
```

The browser side must not serialize the full DOM or every available attribute by default.

Only information useful to semantic matching, locator generation, expectation generation, fingerprinting, and diagnostics should be captured.

## 13. Shared DOM semantics

Recorder and Player must use the same or behaviorally equivalent semantics for:

- actionable-target normalization
- role computation
- accessible-name computation
- label relationships
- visible text normalization
- visibility checks
- enabled/editable state
- frame/shadow traversal

The recommended implementation is to keep browser-side reusable semantic helpers separate from Recorder-specific hooks, for example conceptually:

```text
dom-semantics.js
recorder-hook.js
picker.js
```

The Player may invoke the same semantic helpers through Selenium script execution where appropriate.

Recorder and Player must not independently invent incompatible accessible-name or role logic.

## 14. Actionable-target normalization

The raw event target is not always the logical control.

Example:

```html
<button aria-label="保存">
  <svg><path /></svg>
</button>
```

A click on `path` should normally normalize to the actionable `button` before target generation.

The browser snapshot should preserve enough raw context for diagnostics, but SemanticOperation and locator generation should use the normalized actionable target.

## 15. Python-side EventNormalizer

### 15.1 Responsibility

Semantic normalization belongs primarily in Python.

The browser side should perform only low-level aggregation needed to preserve transient state efficiently.

Conceptual transformation:

```text
RawCaptureEvent(s)
    -> EventNormalizer
    -> SemanticOperation
```

### 15.2 SemanticOperation

SemanticOperation is an internal model distinct from both RawCaptureEvent and Scenario Node.

Initial conceptual variants include:

```text
SemanticClickOperation
SemanticDoubleClickOperation
SemanticInputOperation
SemanticSelectOperation
SemanticKeyOperation
SemanticNavigationOperation
SemanticWindowSwitchOperation
```

The separation allows FlowTape to retain the fact that a user clicked or entered text even if target registration later fails.

## 16. Click normalization

A normal browser click sequence such as:

```text
pointerdown
mousedown
pointerup
mouseup
click
```

produces one semantic `click` operation.

The native `click` event is normally the primary commit signal.

`mousedown`/`mouseup` are not emitted as independent Scenario steps.

## 17. Double-click normalization

Browsers commonly emit a sequence similar to:

```text
click
click
dblclick
```

FlowTape must not convert this into two clicks plus one double-click.

### 17.1 Pending click rule

A click that may become part of a double-click is held briefly as pending rather than immediately converted into a Scenario step.

Conceptually:

```text
first click
    -> pending click
second click / dblclick
    -> discard pending single-click result
    -> emit one SemanticDoubleClickOperation
```

If the double-click does not occur within the implementation's double-click decision window, the pending click becomes one SemanticClickOperation.

The exact timer value is an implementation parameter in v1; the observable requirement is correct coalescing.

## 18. Text input normalization

### 18.1 Final-value model

Normal character entry is recorded as one `input` operation containing the resulting value, not as a key-by-key replay transcript.

Example user editing:

```text
A
B
C
Backspace
D
```

with final value:

```text
ABD
```

produces one input operation whose value is `ABD`.

### 18.2 Pending input state

The browser/Recorder maintains pending input state per active editable element while recording.

Repeated `input` events update the pending final value rather than generating steps immediately.

### 18.3 Commit boundaries

A pending input should be committed when one of the following meaningful boundaries occurs:

1. `change` indicates commit
2. focus leaves the editable element
3. Enter semantically commits the input
4. another meaningful browser operation begins
5. recording stops
6. the document is about to be replaced and the pending value can still be flushed

The implementation may commit earlier where browser semantics clearly indicate completion, provided it does not produce per-keystroke scenario noise.

## 19. IME and composition

Japanese and other IME composition must be explicitly supported.

### 19.1 Composition state

During:

```text
compositionstart
    ... intermediate input events ...
compositionend
```

intermediate text must not be mistaken for a committed scenario input value.

### 19.2 Commit after composition

The final value after `compositionend` becomes the pending input value and is later committed according to ordinary input boundaries.

### 19.3 Enter during composition

An Enter key used to confirm IME conversion must not automatically become an independent `key: ENTER` Scenario action merely because a keydown event occurred.

The Recorder must distinguish IME composition confirmation from an application-level Enter action where possible.

## 20. Password and secret inputs

When the target is recognized as a password input, the browser-side protocol must not include the plaintext value in RawCaptureEvent data or diagnostic snapshots.

Conceptually:

```yaml
input:
  secret: true
  value: null
```

The Editor may create the input step and require the user to assign an explicit credential reference later.

Application-side selection/registration and cancellation behavior follow `13-credential-and-authoring-ux.md`. The ordinary GUI does not finalize a password step until credential resolution succeeds; unresolved operations remain pending. New-group registration uses separately entered, masked application fields and never obtains the password from browser event data. Minimal `autocomplete` evidence may be captured to support conservative username pairing; it contains no input value.

FlowTape must not automatically persist captured plaintext password values into scenario YAML, logs, diagnostics, crash recovery, or output files.

## 21. Select normalization

For native `<select>` elements, `change` is the normal semantic commit event.

The capture data should include both:

- selected option value
- selected option visible text

Scenario generation should normally favor the visible option text for human readability where replay semantics can remain deterministic.

For multi-selects, capture `multiple: true`, `values` (DOM option values for internal evidence) and `texts` (normalized visible texts) for the complete selected set on every change, including an empty set. Persist `texts` as the step's `values` list; do not stop recording when more than one option is selected. Single-selects retain their scalar visible-text step. Normalize option text with the shared DOM whitespace rule, including non-breaking spaces.

Native select/option clicks are selection gestures and must not create additional `click`/`double_click` steps; picker suppression and selection remain active before this filtering. Changes are the selection commit boundary.

Exact Player matching rules for select values/text are defined in runtime semantics.

## 22. Checkbox and radio controls

Recorder v1 represents ordinary user activation of checkbox/radio controls as `click` unless the DSL later adds dedicated idempotent `check`/`uncheck` actions.

The captured snapshot may include current checked state for diagnostics and expectation generation.

## 23. Keyboard normalization

Ordinary printable character entry and editing keys used inside text entry are absorbed into `input` semantics.

Independent `key` operations are produced for meaningful keyboard actions such as:

```text
ENTER
ESCAPE
TAB
arrow/navigation keys
function keys
Ctrl/Alt/Meta shortcuts
```

### 23.1 Enter after text input

If Enter both commits an input and triggers a meaningful application action such as search or form submission, the normalized result may be:

```text
SemanticInputOperation
SemanticKeyOperation(ENTER)
```

If Enter only inserts a line break in a multiline editor, it remains part of the input value and does not become an independent key step.

### 23.2 Textarea and multiline contenteditable

A normal Enter inside a multiline editable area is treated as text input.

Explicit shortcuts such as Ctrl+Enter may remain independent key operations.

## 24. Contenteditable

Basic plain-text `contenteditable` editing is supported in v1 as input-like behavior.

The Recorder should capture a normalized plain-text value.

FlowTape v1 does not guarantee faithful recording/replay of rich-text formatting operations such as arbitrary inline style changes, embedded object manipulation, or editor-specific command models.

## 25. Navigation observation

### 25.1 Click-caused navigation

When a recorded click causes navigation, the click remains the semantic operation.

FlowTape should not normally append an additional `open` step for the resulting destination URL.

### 25.2 Browser-state observer

Python observes browser state including:

```text
current URL
window handles
document_instance_id
```

to correlate navigation with preceding operations.

### 25.3 Direct navigation without a DOM action

If the URL/document changes without a preceding recorded DOM action that explains it, FlowTape may create a SemanticNavigationOperation when the transition can be identified deterministically.

Browser chrome/address-bar interactions are not directly observable by page-injected JavaScript.

Inference of `open`, `back`, `forward`, or `refresh` from external browser UI behavior is therefore best-effort unless FlowTape itself initiated or explicitly observed the operation.

The Recorder must not invent an uncertain navigation action silently.

## 26. SPA navigation

Injected JavaScript should observe SPA history changes where practical, including:

```text
history.pushState
history.replaceState
popstate
```

A history change is an internal navigation observation, not automatically a Scenario step.

If it is the consequence of a preceding click, the click remains primary.

If it is independently user-triggered and can be classified deterministically, the EventNormalizer may produce a navigation operation.

## 27. Page lifecycle flushing

The injected script should make a best-effort attempt to flush pending browser-side state during lifecycle events such as:

```text
pagehide
beforeunload
```

This mechanism supplements but does not replace the requirement to capture lightweight target snapshots at meaningful events.

Correctness must not depend solely on `beforeunload`, because it is not guaranteed in every navigation/crash case.

## 28. Window and tab observation

### 28.1 Source of truth

The authoritative source for existing browser windows/tabs is Selenium's window-handle state.

Injected observation of `window.open` may provide hints but is not the authoritative source.

### 28.2 Parent relation

If an operation in window A is followed by a newly observed handle B, FlowTape records a runtime parent relationship:

```text
B -> A
```

when deterministic.

### 28.3 User switches windows

Injected event queues are associated with the window/frame in which they occur.

If user interaction occurs in another known browser window, Python can correlate the event source with that handle and generate a semantic window switch where needed.

Window-switch DSL generation must follow the supported deterministic forms such as `newest` and `parent`.

## 29. iframe support

### 29.1 Per-document injection

Top-level page injection is insufficient for events inside iframes.

Python's Injection Manager must discover accessible frame documents and inject the Recorder script into each relevant frame document.

This applies to both same-origin and cross-origin iframes insofar as Selenium can switch into the frame and execute the required script there.

### 29.2 Frame identity/context

Events originating inside frames carry runtime frame-path/context information sufficient to associate the event with its source document.

Persisted frame locator generation remains the responsibility of the Element Capture Engine and `elements.yaml` target definition.

### 29.3 Dynamic iframe reinjection

Frames may be created or replaced after initial page load.

FlowTape must support reinjection into dynamically added/replaced frames.

Recommended design:

```text
MutationObserver or equivalent frame-change hint
    -> Python notices/discovers frame tree change
    -> Selenium switches into new frame document
    -> inject if FlowTape protocol is not already present
```

Python may also periodically reconcile the frame tree as a fallback.

### 29.4 Frame navigation

If an iframe navigates and creates a new document instance, the old injected state is lost.

The Injection Manager must detect the new frame document and inject again.

A stale frame/document execution error during such transition is normally a resynchronization condition, not immediately a fatal Recorder failure.

## 30. Shadow DOM

### 30.1 Open shadow roots

FlowTape v1 supports open Shadow DOM where browser APIs/Selenium can observe and traverse it reliably.

Observer/picker support should include relevant open shadow roots rather than assuming document-level listeners alone are always sufficient.

### 30.2 Closed shadow roots

Closed Shadow DOM is unsupported in v1 unless the browser exposes a deterministic mechanism available to both Recorder and Player.

The Recorder must report an explicit unsupported/diagnostic condition rather than pretending to capture a reliable target.

## 31. Injection Manager

Python owns an Injection Manager responsible for ensuring that Recorder support is installed in every active observable browser document that requires it.

It reacts to at least:

```text
new top-level document
new browser window/tab
new iframe
iframe navigation/replacement
new relevant open shadow-root observation point
```

### 31.1 Idempotent injection

Injected initialization must be idempotent.

Conceptually:

```javascript
if (window.__flowtape?.protocolVersion === 1) {
  return;
}
```

Repeated discovery of the same document must not install duplicate event handlers or duplicate queues.

### 31.2 Version mismatch

If an older incompatible injected version is found, FlowTape must explicitly reinitialize it or report a protocol mismatch. It must not run two incompatible observer versions simultaneously.

## 32. Interaction modes

Browser-side interaction intent is explicit.

Initial conceptual modes include:

```text
observe
record
pick
rebind
collection_pick
```

These internal names do not have to be exposed verbatim in the GUI.

The essential rule is that the same browser click has different protocol meaning depending on interaction mode.

## 33. Record mode

In Record mode:

- normal user operations proceed normally
- FlowTape observes them
- FlowTape must not suppress the application's click/input behavior
- meaningful operations are normalized into SemanticOperations

## 34. Pick/Rebind/Collection Pick suppression

### 34.1 Selection must not trigger the application

When the user is selecting a DOM element for:

- Pick
- Rebind
- collection representative selection
- a DOM-dependent condition/source in the Editor

that selection click is a FlowTape editing gesture, not an application action.

The browser-side picker must suppress the page's normal click behavior.

For the selection event it may use:

```text
preventDefault()
stopPropagation()
stopImmediatePropagation()
```

as needed.

### 34.2 Suppression boundary

This suppression behavior is permitted only for explicit picker-style modes.

It must not leak into Record mode.

### 34.3 Picker click is not recorded

A click used to choose a target in Pick/Rebind/Collection Pick must never produce a normal scenario `click` step.

## 35. Picker hover and overlay

### 35.1 Local highlight handling

High-frequency hover/mousemove events should be handled primarily inside the browser rather than transported continuously to Python.

The browser script may directly draw/update the highlight overlay.

Python only needs meaningful picker state changes and final selection.

### 35.2 Internal overlay exclusion

FlowTape-owned overlay nodes must be marked as internal and excluded from target capture/normalization.

For example, FlowTape-owned nodes may carry an internal marker such as:

```html
data-flowtape-internal
```

This exception applies only to FlowTape-created nodes, not to application elements.

## 36. Collection Picker

For `for_each` collection authoring:

```text
user chooses collection-picker mode
    -> selects one representative item
    -> Capture Engine generates collection locator candidates
    -> current matching members are highlighted
    -> UI shows count/examples
    -> user confirms a candidate
```

The representative-selection click is suppressed and not recorded as a scenario click.

Collection generation may reuse ordinary snapshot/scoring infrastructure but produces a CollectionDefinition rather than an ElementDefinition.

## 37. `read` and `append` authoring boundary

`read` and `append` are explicit scenario-authoring intentions, not operations that the Recorder can reliably infer merely from what the user looks at on a page.

The Editor should therefore create `read` through an explicit action such as:

```text
値を取得
    -> browser picker selects DOM target
    -> choose source: text/value/attribute
    -> choose runtime variable name
```

The resulting Scenario node is conceptually:

```yaml
- action: read
  target: 起票者
  source: text
  into: author
```

Likewise, `append` is added explicitly by the Editor and binds runtime values to a declared scenario output.

Neither is inferred from passive browser observation.

## 38. Existing target reuse

When a normalized operation references a DOM element that is already represented by a target in the current page scope, Recorder should prefer reusing that logical target instead of creating a duplicate target entry.

Reuse is allowed only when current evidence identifies the same live element deterministically.

If multiple existing targets could represent the element, Recorder must not silently choose one.

## 39. Page association during recording

An event may occur before the current page has been identified or before a newly visited page definition exists.

Recorder must not discard such events solely because page identification is pending.

It may hold the SemanticOperation in a pending-page-association state until:

- the current page maps uniquely to an existing page definition, or
- the Recorder creates/requests creation of a new page definition.

Exact PageIdentifier semantics are defined in runtime semantics.

## 40. Start recording

Starting recording establishes a semantic boundary.

Operations that occurred before Start Recording are not retroactively recorded.

Existing values already present in input fields are not automatically turned into input steps merely because recording begins.

Only meaningful operations observed after the start boundary enter the Recorder pipeline.

## 41. Stop recording

Stopping recording performs an orderly finalization sequence.

Conceptually:

1. stop accepting new record-mode operations
2. drain queued RawCaptureEvents
3. flush pending IME/input state
4. resolve pending click/double-click decision
5. normalize remaining events
6. insert resulting Scenario nodes at the active insertion position

The Selenium browser remains open for editing, picking, rebinding, validation, and later resumed recording.

## 42. Recording pause

A dedicated Record Pause state is not required for v1.

Start/Stop is sufficient initially and avoids additional ambiguity around pending input, pending clicks, and document transitions.

Playback pause is a separate UI/runtime concept and is not defined by this Recorder protocol.

## 43. Queue limits and overflow

The browser-side event queue must be bounded or otherwise protected against unbounded growth.

If the queue overflows or FlowTape knows events were dropped, the Recorder must not silently continue as though recording were complete.

It must surface an error/paused-desynchronized state because the resulting scenario may otherwise omit user operations.

A queue-overflow condition is more severe than simply dropping oldest events.

## 44. Synchronization and reinjection failures

Expected transition errors such as:

```text
stale frame/document
execution context destroyed
no such window during a just-closed window transition
```

may be treated as resynchronization signals when they coincide with observed browser transitions.

The Recorder should attempt to rediscover windows/documents/frames and reinject.

If it cannot reestablish observation deterministically, recording enters an explicit desynchronized/error state.

It must not silently claim that subsequent user operations were recorded reliably.

## 45. Suggested diagnostic categories

Initial internal/user-visible categories may include:

```text
RecorderInjectionError
RecorderProtocolVersionMismatch
RecorderEventQueueOverflow
RecorderSnapshotCaptureError
RecorderFrameInjectionError
RecorderClosedShadowRootUnsupported
RecorderDesyncError
```

Exact Python exception class names are implementation details, but diagnostics should preserve the distinction between these causes.

## 46. Observer health

Python should periodically verify that the active observable document still exposes a compatible FlowTape observer.

A lightweight probe may check the equivalent of:

```text
window.__flowtape.protocolVersion
```

If the observer disappeared because of navigation or frame replacement, normal reinjection is attempted.

If FlowTape detects that an unknown interval of user interaction may have occurred while observation was unavailable, it must warn or stop recording rather than silently bridging the gap.

## 47. Data minimization and privacy

Recorder capture should minimize browser data retained or transported.

Principles:

- no whole-page DOM dumps by default
- no plaintext password transport
- no credential expansion into diagnostics
- no unnecessary text/attribute capture unrelated to target identification
- no persistent storage of raw capture events unless explicitly required for debugging/recovery policy

Normal diagnostic logs should prefer statements such as:

```text
read target 起票者 succeeded
```

over dumping the actual extracted value unless a dedicated diagnostic mode explicitly requires it and policy permits it.

Scenario outputs are separate user-requested artifacts and follow the output rules in the DSL/runtime specifications.

## 48. v1 supported recording scope

The first Recorder should reliably target:

- ordinary clicks
- double-clicks
- normal text input
- Japanese IME text input
- textarea input
- basic plain-text contenteditable input
- native select changes
- meaningful keyboard operations
- ordinary new tab/window workflows
- iframe-contained DOM operations where Selenium can inject
- open Shadow DOM where observable/replayable
- Picker/Rebind/Collection Picker target selection

Support may be best-effort or explicitly limited for:

- complex HTML5/custom drag-and-drop
- rich text editors with editor-specific internal commands
- canvas/WebGL internal interaction
- closed Shadow DOM
- browser extension UI
- browser chrome/native UI
- native OS dialogs
- custom gesture systems

Recorder limitations must be reported clearly rather than hidden by fragile synthetic guesses.

## 49. Non-goals

The Recorder protocol does not attempt to:

- persist raw browser events directly as the public DSL
- record every physical mouse movement
- turn every keydown into a Scenario step
- use fuzzy heuristics to silently guess ambiguous targets
- modify application DOM elements to attach persistent FlowTape identities
- capture secrets for later plaintext replay
- infer arbitrary scraping/output intent from passive viewing
- guarantee browser-native UI automation outside the web page

## 50. Implementation guidance

Recommended internal component boundaries are:

```text
InjectionManager
BrowserObserverClient
RawCaptureEvent
ElementSnapshot
EventNormalizer
SemanticOperation variants
InputAccumulator
ClickCoalescer
PickerController
RecorderSession
```

The JavaScript implementation should remain focused on observation, transient state capture, picker behavior, and small shared DOM-semantic helpers.

The Python implementation should own semantic coalescing, recorder state, Element Capture Engine invocation, target reuse/creation, and Scenario Node generation.

The protocol should be covered by tests for at least:

- single click -> one semantic click
- double-click -> no duplicate single-click steps
- multi-keystroke text -> one final input step
- Japanese IME composition -> no intermediate-value step
- Enter during IME conversion -> no false application key step
- password input -> no plaintext RawCaptureEvent value
- click immediately followed by navigation -> target snapshot retained
- full navigation -> reinjection into new document
- iframe navigation/replacement -> reinjection into new frame document
- dynamically added iframe -> observer injection
- Pick click -> application action suppressed and no scenario click generated
- Record click -> application action not suppressed
- queue overflow -> explicit error/desync state
- duplicate/retried event delivery -> no duplicate semantic operation


## 49. Native input diagnostics and source verification

The optional `FLOWTAPE_RECORDER_TRACE` developer diagnostic records only runtime document/sequence identities, event kinds, trusted flags, pipeline state/counts/reasons and Step identities. It must never persist input values, credentials, accessible names, URLs, snapshots or complete raw events. It traces admission at the observer, binding delivery, merged transport, normalization and UI queue/commit boundaries. Explicitly ignored native-select clicks and label activation relays are identified rather than counted as losses.

For top-level clicks with no frame/shadow context, Stage 1 may synchronously verify bounded semantic locator candidates against the original element with the same shared locator/acceptance definitions used by the Player. It also captures existing PageDefinition matches/conditions on that source document. This evidence remains in memory. After navigation, the UI may use only verified, stable candidates and source page evidence to register/reuse the original target and finalize the original click. Page registration/target naming remain explicit. Existing URL-only conditions may be evaluated against the captured URL; DOM-dependent conditions require contemporaneous source evidence. Ambiguous or missing evidence retains the pending operation instead of guessing. No extra open step is added to explain a captured navigation click.

Label activation sends a click to its associated control. The originating non-interactive label click is not a separate operation; the forwarded control click is recorded. Links/buttons/other interactive descendants retain their own actions. Native acceptance coverage and transport-stage evidence are documented in `testing/recorder-native-input.md`.
