# FlowTape Architecture

Status: initial specification before implementation

## 1. High-level structure

FlowTape is divided into UI, scenario/domain, page/DOM-resolution, browser-context, browser-execution, and result-output layers.

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
          +------------------------+
          |                        |
          v                        v
+--------------------+    +--------------------+
| Page + DOM Registry|    | Control Flow       |
| elements.yaml      |    | if / loops / vars  |
+---------+----------+    +---------+----------+
          |                         |
          +------------+------------+
                       v
              +--------------------+
              | Player             |
              | PageIdentifier     |
              | TargetResolver     |
              | WindowContext      |
              +----+----------+----+
                   |          |
                   v          v
             +-----------+  +----------------+
             | Selenium  |  | Result Output  |
             +-----+-----+  | Writer         |
                   |        +----------------+
                   v
             +-----------+
             | Edge      |
             +-----------+
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
- invoke element picking/binding/rebinding
- hand captured browser events to normalization and the Element Capture Engine

The Recorder must not own locator-generation logic directly.

### 2.2 Scenario Editor

Responsibilities:

- display scenario steps in execution order
- edit action parameters
- select contiguous step ranges
- wrap ranges in structural blocks
- configure `if`, `else`, `repeat`, `for_each`, and `while`
- add explicit `read` and `append` actions when the user wants result collection
- edit named output definitions
- maintain a readable relationship between UI structure and YAML structure
- maintain explicit save state and undo/redo

The Editor must not infer that visible page text should be collected merely because the user viewed or clicked it.

### 2.3 Injected browser script

A JavaScript component is injected into the Selenium-controlled page.

Responsibilities include:

- observe pointer/click/input-related events
- identify the immediate event target
- collect browser-side DOM information
- support hover/highlight/picker interaction
- communicate captured DOM information back to Python

It does not become a second execution engine. Playback remains controlled by Python/Selenium.

Detailed transport, normalization, reinjection, IME, navigation-snapshot, and picker rules are defined in `08-recorder-protocol.md`.

### 2.4 Element Capture Engine

Shared by Recorder, Picker, Bind, and Rebind.

Input:

- the user-indicated DOM element
- DOM snapshot/context information

Output:

- normalized actionable target
- logical-name suggestion
- locator candidates
- candidate scores/diagnostics
- `expect` information
- diagnostic fingerprint information
- ordered iframe/shadow traversal context

Candidate generation and scoring remain separate stages.

The canonical runtime ElementSnapshot structure is defined by `08-recorder-protocol.md`; locator-generation code consumes that model rather than inventing a second incompatible snapshot DTO.

### 2.5 Page Identifier

The Page Identifier determines which page scope in the scenario-local registry applies to the current browser document.

Page definitions may use:

- URL conditions
- DOM-identification conditions
- a combination of both

Rules:

- zero matching page definitions -> `UnknownPage`
- exactly one matching page definition -> use that page scope
- multiple matching page definitions -> `AmbiguousPage`

Page identification must not guess based on ordering.

### 2.6 DOM Registry

The DOM Registry persists scenario-local page and target definitions in `elements.yaml`.

Responsibilities:

- page identification definitions
- page-scoped logical target lookup
- persistence/versioning
- target name collision handling within page scope
- storing locator candidates, ordered traversal context, expectations, and fingerprint data
- collection definitions for `for_each`
- updating/rebinding existing targets

The registry is not a full DOM snapshot.

### 2.7 Target Resolver

Resolution order is conceptually:

```text
identify current page
    -> load page-scoped target definition
    -> enter ordered frame/shadow context
    -> apply runtime `within` scope where present
    -> try locator candidate
    -> inspect matches
    -> validate against expect
    -> apply action-specific requirements
    -> accept exactly one element
```

If a locator yields no acceptable element, later persisted locators may be tried. If multiple acceptable elements remain, the resolver must not choose the first implicitly. Exact retry/fallback semantics are defined in `09-runtime-semantics.md`.

Positional/index-based definitions are allowed only as explicit fragile fallbacks.

### 2.8 Window Context Manager

The Window Context Manager tracks Selenium window handles and FlowTape-level parent relationships.

When an operation in window A creates a new window B, FlowTape records B's parent as A when the relationship can be determined from observed handle changes. It must not rely only on browser `window.opener`.

Conceptual stack:

```text
A -> B -> C
parent stack: [A, B]
current: C
```

If the current popup closes automatically:

1. detect that its handle disappeared
2. return to its known parent if the parent still exists
3. re-identify the current page
4. continue execution

If the current window remains open, no automatic return occurs. If the current window closes and the correct return target is not deterministically known, execution fails rather than choosing an arbitrary remaining window.

### 2.9 Player

Responsibilities:

- load and validate the scenario package
- load scenario-local `elements.yaml`
- load runtime config and credentials
- evaluate control flow
- identify the current page
- resolve the target immediately before each operation
- perform Selenium operations
- manage windows/tabs
- apply waits/timeouts and loop safety limits
- support execution/validation/debug modes
- manage runtime variables and collection-member snapshots
- invoke the Result Output Writer for `append`
- expose diagnostic information

The Player should not reuse stale `WebElement` objects across unrelated steps when logical targets can be resolved again.

Exact Player behavior is defined in `09-runtime-semantics.md`.

### 2.10 Result Output Writer

The Result Output Writer handles user-requested scenario result artifacts and is separate from diagnostic logging.

Responsibilities:

- resolve scenario-declared logical outputs against configured `paths.outputs`
- enforce relative-path/root-containment rules
- initialize `new`, `append`, and `overwrite` lifecycle behavior
- write CSV, JSON Lines, and text outputs
- preserve CSV column order and validate existing headers where required
- flush successful `append` results so partial runs retain completed records
- reject credential/secret-derived values
- surface output-specific failures without conflating them with browser logging

The writer does not decide what page data to collect; `read` and `append` remain explicit scenario actions.

### 2.11 YAML parser and validator

Responsibilities:

- schema/version validation
- reserved-word validation
- action-parameter validation
- output-definition and append-schema validation
- target existence/binding checks in the applicable page scope
- kind/action compatibility checks
- page-definition validation
- structural block validation
- loop/condition validation
- credential-reference syntax validation without exposing credential values
- variable-name and namespace validation

Errors should identify the affected scenario step, page scope, target/output name, and reason where applicable.

### 2.12 Runtime configuration and credentials

`config.yaml` contains environment/runtime settings. `credentials.yaml` contains plaintext IDs/passwords used through the dedicated `credential` variable namespace.

The credential provider must prevent secret values and secret-derived runtime values from appearing in normal logs, diagnostics, error messages, or result outputs.

## 3. File responsibilities

### Scenario package

Recommended initial layout:

```text
scenarios/
  scenario-name/
    scenario.yaml
    elements.yaml
```

`scenario.yaml` and `elements.yaml` in the same scenario directory are implicitly associated.

### Scenario file

Contains procedure semantics such as:

- navigation
- click/input/select/read/append/upload/key/hover actions
- alert handling
- checks/waits
- conditions and loops
- variables
- named output definitions
- logical target references
- explicit window/tab context transitions

### Elements file

Contains scenario-local page/DOM knowledge:

- page identification rules
- page-scoped locator candidates
- expected element role/type
- relative scope
- ordered iframe/shadow traversal
- fragile fallback markers
- fingerprints
- collection sources

### Configuration file

Contains environment-specific values, including:

- browser settings
- required absolute WebDriver path
- timeout defaults
- credential file path
- download/log/output locations
- optional persistent FlowTape Edge profile path
- Recorder/runtime preferences
- playback observation-delay preferences
- loop safety defaults

### Credentials file

Contains plaintext username/password entries referenced by scenario credential variables. It is external operational data and must be excluded from source control.

### Generated outputs

Generated outputs are execution artifacts rooted under configured `paths.outputs` and are not scenario source files.

They contain only data explicitly emitted by scenario `append` actions. They are distinct from FlowTape system logs and browser downloads.

## 4. Data flow during recording

```text
User performs operation
    -> Injected JS/browser observation
    -> RawCaptureEvent queue
    -> Python polling
    -> event normalization/coalescing
    -> detect page/window context changes
    -> capture immediate DOM target when applicable
    -> normalize actionable target
    -> ElementSnapshot creation
    -> locator candidate generation
    -> candidate validation/scoring
    -> logical target naming in current page scope
    -> DOM Registry update
    -> semantic scenario step appended
```

Raw events are normalized into semantic operations. For example, `mousedown`/`mouseup`/`click` normally become one click step, ordinary typing becomes one `input` step rather than one step per keystroke, and IME composition is handled before input commit.

`read`/`append` result collection is not inferred from ordinary page observation. The user adds those operations explicitly through the Editor/Picker workflow.

## 5. Data flow during manual binding

```text
Scenario references unknown target
    -> determine intended page scope
    -> Bind mode reports missing target
    -> user reaches the correct browser state
    -> user selects the target
    -> Element Capture Engine processes it
    -> page-scoped registry definition is written
```

Manual scenario authoring must not require hand-authoring selector internals.

## 6. Data flow during playback

```text
Load scenario package
    -> load config/credentials/registry
    -> validate schemas
    -> initialize runtime variables/output lifecycle
    -> establish browser/window context
    -> identify current page
    -> evaluate current control-flow node
    -> resolve current logical target
    -> validate expectations/action requirements
    -> execute or inspect according to mode
    -> write explicit result output when action=append and mode=実行
    -> detect resulting page/window changes
    -> playback controller decides continue/pause/step/stop
```

Playback pacing/control is separate from execution semantics. The controller supports continuous playback, slow observation delays, single-step execution, execute-until-selected-position, pause/resume/stop, and handoff from playback to recording.

A failure should leave the player positioned on the failed step so the UI can repair/rebind/retry without reconstructing the entire application process.

## 7. Target normalization boundary

A raw browser event target is not always the intended control.

For example, a click on an SVG `path` inside a button should normally normalize to the actionable button.

Typical actionable elements include:

- button
- anchor with href
- input
- textarea
- select
- contenteditable elements
- common interactive ARIA roles

Generic JavaScript-clickable elements may be accepted as fallbacks when no stronger semantic ancestor exists.

## 8. Shared semantic rules

Recorder and Player must share or mirror definitions for:

- accessible name
- explicit/computed role
- label association
- text normalization
- visible/enabled/editable checks
- page identification
- frame/shadow traversal
- unique-match requirements

A generated locator is invalid as a persisted primary candidate if the Player cannot reproduce its semantics.

The canonical browser-side/runtime snapshot and semantic-helper boundary is defined in `08-recorder-protocol.md`.

## 9. Suggested implementation layering

A practical package split may resemble:

```text
flowtape/
  app/
  recorder/
  editor/
  scenario/
  pages/
  targets/
  capture/
  resolver/
  player/
  outputs/
  browser/
  config/
  credentials/
```

This is not a mandatory filesystem layout. Architectural boundaries are mandatory; exact module names may evolve.

## 10. Dependency direction

Preferred dependency direction:

```text
UI
 -> application services
 -> domain models / capture / resolution / outputs
 -> Selenium/filesystem adapters
```

Domain models should not depend directly on PySide6 widgets, Selenium `WebElement` objects, or open file handles where plain serializable models are sufficient.

## 11. Versioning

Persisted formats should be versioned from the beginning.

At minimum, `version: 1` should exist for scenario, DOM-registry, config, and credentials formats where applicable.

Recorder protocol versioning is independent from persisted YAML schema versioning.

Schema changes must be deliberate and documented.

## 12. Editor transaction boundary

Scenario editing operates against an in-memory model with explicit save semantics and undo/redo support.

Persisted step/node identity is distinct from visible step numbering so reordering does not destroy references used by diagnostics/editor history.

External file changes must be detected and reconciled deliberately rather than silently overwriting unsaved state.
