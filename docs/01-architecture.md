# FlowTape Architecture

Status: initial specification before implementation

## 1. High-level structure

FlowTape is divided into UI, scenario/domain, DOM-resolution, and browser-execution layers.

```text
+--------------------+
| Recorder / Editor  |
+---------+----------+
          |
          v
+--------------------+
| Scenario Model     |
| YAML Parser        |
| Validator          |
+---------+----------+
          |
          +-------------------+
          |                   |
          v                   v
+--------------------+  +--------------------+
| DOM Registry       |  | Control Flow       |
| elements.yaml      |  | if / loops / vars  |
+---------+----------+  +---------+----------+
          |                       |
          +-----------+-----------+
                      v
              +---------------+
              | Player        |
              | TargetResolver|
              +-------+-------+
                      |
                      v
              +---------------+
              | Selenium      |
              +-------+-------+
                      |
                      v
              +---------------+
              | Edge/Browser  |
              +---------------+
```

The Recorder additionally uses browser-injected JavaScript to observe user operations and inspect DOM details.

## 2. Main modules

### 2.1 Recorder UI

Responsibilities:

- launch/connect to the controlled browser session
- start/stop recording
- display recorded steps as a vertical ordered list
- show current recording state
- allow step selection
- open target information/editing
- invoke element picking/binding
- hand the captured event to the Element Capture Engine

The Recorder must not own locator-generation logic directly.

### 2.2 Scenario Editor

Responsibilities:

- display scenario steps in execution order
- edit action parameters
- select a contiguous step range
- wrap ranges in structural blocks
- configure `if`, `else`, loop, and similar behavior
- maintain a readable relationship between UI structure and YAML structure

The normal editing model is a vertical step sequence with visible range blocks around grouped steps.

### 2.3 Injected browser script

A JavaScript component is injected into the Selenium-controlled page.

Responsibilities include:

- observe pointer/click/input-related events
- identify the immediate event target
- collect browser-side DOM information that Selenium alone would be cumbersome to obtain repeatedly
- support hover/highlight/picker interaction
- communicate captured DOM information back to Python

It does not become a second execution engine. Playback remains controlled by the Python/Selenium side.

### 2.4 Element Capture Engine

This is shared by Recorder, Picker, and Bind workflows.

Input:

- the user-indicated DOM element
- DOM snapshot/context information

Output:

- normalized operation target
- logical-name suggestion
- locator candidates
- candidate scores and diagnostics
- `expect` information
- optional fingerprint information
- context path such as iframe/shadow traversal

It must separate candidate generation from candidate scoring.

### 2.5 DOM Registry

The DOM Registry persists logical target definitions, normally in `elements.yaml`.

Responsibilities:

- lookup by logical target name
- persistence/versioning
- name collision handling
- storing locators, context, expectations, and limited fingerprint data
- updating/rebinding an existing target

The registry is not the same thing as a full captured DOM snapshot.

### 2.6 Target Resolver

The Player asks the Target Resolver to convert a logical target name into one acceptable current DOM element.

Resolution order is conceptually:

```text
logical target
    -> load definition
    -> enter frame/shadow context
    -> try locator candidate
    -> inspect match count
    -> validate against expect
    -> accept exactly one element
```

If a locator yields no acceptable element, the resolver may try the next persisted locator.

If multiple acceptable elements remain, it must not pick the first one implicitly.

### 2.7 Player

Responsibilities:

- load and validate scenario YAML
- load DOM registry
- evaluate control flow
- resolve target immediately before each operation
- perform the Selenium operation
- apply waits/timeouts
- expose diagnostic information
- support execution modes such as execution, validation, and debug

The Player should not reuse a stale WebElement across unrelated steps when a logical target can be resolved again at operation time.

### 2.8 YAML parser and validator

Responsibilities:

- schema/version validation
- reserved-word validation
- action-parameter validation
- target existence/binding checks
- kind/action compatibility checks
- structural block validation
- invalid loop/condition detection

It should produce errors that identify the affected scenario step and target.

## 3. File responsibilities

### Scenario file

Contains procedure semantics.

Examples:

- `open`
- `click`
- `input`
- `read`
- conditions
- loops
- variables
- logical target references

### Elements file

Contains DOM resolution knowledge.

Examples:

- locator candidates
- expected element role/type
- relative scope
- iframe/shadow context
- fragile fallback marker

### Configuration file

Contains runtime/environment-specific values.

Examples may include:

- browser choice
- Edge binary path if needed
- driver settings/path
- timeout defaults
- output/log settings

The exact format is intentionally not fixed yet.

## 4. Data flow during recording

```text
User performs operation
    -> Injected JS observes event
    -> event normalization/coalescing
    -> immediate DOM target captured
    -> target normalization
    -> ElementSnapshot creation
    -> locator candidate generation
    -> candidate validation and scoring
    -> logical target naming
    -> DOM Registry update
    -> semantic scenario step appended
```

Scenario generation and DOM registration are related but separate outputs.

The event-normalization layer converts low-level event streams into semantic operations. For example, `mousedown`/`mouseup`/`click` should normally become one click step, and typing should normally become one input step when the edit is committed rather than one step per keystroke.

## 5. Data flow during manual binding

```text
Scenario contains unknown target name
    -> Bind mode detects missing target
    -> browser navigates/reaches relevant state
    -> UI asks user to select the target
    -> picker identifies element
    -> Element Capture Engine processes it
    -> registry definition is written
```

Manual scenario authoring must therefore not require manually authoring selector internals.

## 6. Data flow during playback

```text
Load scenario
    -> validate schema
    -> load registry
    -> evaluate current control-flow node
    -> resolve logical target at current DOM state
    -> validate target kind/state
    -> execute or inspect according to mode
    -> playback controller decides continue/pause/step/stop
```

Playback pacing/control is separate from execution semantics. The controller must support continuous playback, slow observation delays, single-step execution, execute-until-selected-position, pause/resume/stop, and handoff from playback to recording.

A failure should leave the player positioned on the failed step so that the UI can rebind/repair and retry that step without reconstructing the entire application process.

## 7. Target normalization boundary

A raw browser event target is not always the intended operation target.

For example:

```html
<button aria-label="保存">
  <svg><path /></svg>
</button>
```

A click may originate on `path`, but the normalized target should be the actionable `button`.

The normalizer should climb through ancestors to find the appropriate actionable semantic element when needed.

Typical actionable elements include:

- button
- anchor with href
- input
- textarea
- select
- contenteditable elements
- common ARIA interactive roles

JavaScript-clickable generic elements may be accepted as fallbacks when no stronger semantic ancestor exists.

## 8. Shared semantic rules

Recorder and Player must share or mirror the same definitions for:

- accessible name
- explicit/computed role
- label association
- text normalization
- visible/enabled/editable checks
- frame traversal
- shadow-root traversal
- unique-match requirements

A generated locator is invalid as a persisted primary candidate if the Player cannot reproduce its semantics.

## 9. Suggested implementation layering

A practical package split may eventually resemble:

```text
flowtape/
  app/
  recorder/
  editor/
  scenario/
  targets/
  capture/
  resolver/
  player/
  browser/
  config/
```

This is not yet a mandatory filesystem layout. The architectural boundaries above are mandatory; exact module names may evolve.

## 10. Dependency direction

Preferred dependency direction:

```text
UI
 -> application services
 -> domain models / capture / resolution
 -> Selenium adapter
```

Avoid making domain models depend on PySide6 widgets or Selenium WebElement objects directly where plain serializable models are sufficient.

## 11. Versioning

Persisted formats should be versioned from the beginning.

At minimum:

```yaml
version: 1
```

should exist for scenario and DOM-registry formats or be represented equivalently.

Schema changes must be deliberate and documented rather than inferred at runtime from ambiguous shapes.

## 12. Editor transaction boundary

Scenario editing should operate against an in-memory model with explicit save semantics and undo/redo support.

Persisted step/node identity should be distinct from visible step numbering so reordering does not destroy references used by diagnostics or editor history.

External file changes should be detected and reconciled deliberately rather than silently overwriting unsaved editor state.
