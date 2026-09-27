# AGENTS.md

## Project

FlowTape is a browser automation tool built around a human-readable YAML DSL.

The intended product consists of:

- Recorder: observes a user's browser operation and converts it into semantic steps.
- Scenario Editor: edits the recorded linear steps and adds conditions, loops, and other structure.
- DOM Registry: stores how logical target names map to real DOM elements.
- Player: executes scenarios through Selenium.
- YAML DSL: remains readable as an operation manual, not merely as serialized Selenium commands.

The implementation is expected to be Python-based. Selenium is the browser automation layer. The Recorder UI is expected to use PySide6, while JavaScript injected into the controlled page observes and inspects browser-side DOM events.

## Source of truth

Before implementing or modifying behavior, read the relevant files under `docs/`.

The current specifications are split as follows:

- `docs/00-overview.md` — product goals and global principles
- `docs/01-architecture.md` — component boundaries and data flow
- `docs/02-yaml-dsl.md` — scenario YAML language
- `docs/03-recorder-ui.md` — Recorder and Scenario Editor interaction model
- `docs/04-target-registry.md` — logical targets and `elements.yaml`
- `docs/05-locator-generation.md` — DOM capture, locator generation, scoring, and fallback selection
- `docs/06-runtime-platform.md` — packaging, Selenium/Edge, and cross-platform constraints
- `docs/07-data-schema.md` — strict persisted schema for scenario, registry, config, credentials, outputs, and validation boundaries
- `docs/08-recorder-protocol.md` — browser-side Recorder protocol, RawCaptureEvent normalization, IME/input, navigation capture, reinjection, and picker behavior
- `docs/09-runtime-semantics.md` — Player execution semantics, resolver behavior, modes, waits, loops, outputs, retries, and playback control

When multiple documents touch the same subject, the more specific document governs its own layer. In particular, persisted field legality comes from `07-data-schema.md`, Recorder event behavior comes from `08-recorder-protocol.md`, and Player execution behavior comes from `09-runtime-semantics.md`.

If implementation and documentation disagree, do not silently reinterpret the specification. Either update the implementation to match the documented decision or explicitly update the specification as part of the same change.

## Design rules

### Scenario YAML is semantic

Scenario files describe the meaning and order of operations. They must not become a dump of CSS selectors, XPath expressions, DOM snapshots, or Selenium implementation details.

A scenario step references a logical target name, for example:

```yaml
- action: click
  target: ログイン
```

The actual DOM resolution belongs in the DOM registry.

### DOM resolution is conservative

Never silently select the first matching element when multiple elements remain.

A target is executable only when the resolver can identify exactly one acceptable element after applying its context, locator, and expectation rules.

Zero matches and unresolved multiple matches are errors or diagnostic states, not opportunities for implicit guessing.

### Recorder and Player share semantics

The Recorder/Element Capture Engine and the Player/Target Resolver must use compatible definitions of:

- accessible name
- role
- label relationships
- visibility and enabled state
- frame/shadow traversal
- locator matching
- target-kind validation

Do not let the Recorder generate definitions the Player interprets differently.

### Prefer semantic locators

Prefer stable and meaningful information such as:

- explicit test attributes
- stable IDs
- ARIA role + accessible name
- associated labels
- stable `name` or purpose-oriented attributes
- visible text when appropriate
- meaningful relative context such as a dialog, table row, form, section, or heading

CSS and XPath are supported fallbacks, not the conceptual center of the DSL.

Avoid fragile selectors such as absolute XPath, long DOM paths, `nth-child`, random framework-generated classes, or position indexes unless no stronger representation exists. Fragile fallbacks must remain explicitly identifiable as fragile.

### Keep YAML readable for Japanese users

Reserved keys and common browser action names remain English where that is clearer and conventional (`click`, `double_click`, `input`, `if`, `while`, etc.).

User-facing values and free text may be Japanese. Established mode/risk values use the Japanese vocabulary documented in the DSL specification.

### Normal flow first, structure second

The Recorder primarily records a completed linear human operation. Conditions and loops are then added by selecting a contiguous range of recorded steps and wrapping that range in a structural block.

Do not force users to define branching logic while recording the normal operation.

## Platform and packaging constraints

The development/test environment may be Linux, while the main deployment environment is Windows 11 with Microsoft Edge.

Keep browser/DOM logic OS-independent. Isolate platform-specific behavior such as executable paths, downloads, filesystem paths, driver discovery, and native UI interaction.

The long-term distribution model assumes:

- Python/Selenium application packaged with PyInstaller
- no Python installation required on the end-user machine
- scenario YAML stored outside the executable
- configuration stored outside the executable
- WebDriver/browser-driver related configuration replaceable without rebuilding the executable

Do not bake user scenarios or environment-specific paths into packaged code.

## Implementation discipline

- Prefer small modules with explicit boundaries between capture, scenario model, target registry, resolution, execution, and UI.
- Keep serialization models versioned.
- Preserve backwards compatibility deliberately; do not silently reinterpret existing YAML.
- Validation errors should identify the scenario step, target name, and reason.
- Diagnostic output should expose locator candidates and resolution reasons without leaking the complete DOM into normal scenario files.
- Keep generated locator scores as diagnostics/internal metadata unless a specification explicitly promotes them into the persisted schema.
- Add tests for resolver ambiguity, zero matches, semantic locator preference, dynamic-ID rejection, frame/shadow context, structural DSL behavior, output validation, Recorder event normalization, and runtime mode differences as those modules are implemented.

## Specification changes

When a design decision changes:

1. Update the appropriate document under `docs/`.
2. Update examples in other affected documents.
3. Update implementation and tests in the same change where practical.
4. Avoid leaving two conflicting syntaxes documented as equally valid unless compatibility explicitly requires both.
