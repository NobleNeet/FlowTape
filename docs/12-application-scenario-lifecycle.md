# FlowTape Application and Scenario Lifecycle

Status: specification

This document defines the application-level startup and scenario lifecycle that sits above the Recorder/Editor UI in `03-recorder-ui.md` and the runtime/platform rules in `06-runtime-platform.md`.

Where an older document assumes that the GUI can only start with an already-selected scenario package, this document takes precedence: the FlowTape application can exist with no scenario open.

The start-view priority, primary New/Open labels, and visible command hierarchy are governed by `14-primary-user-flows-and-ui-hierarchy.md`. The lifecycle and safety boundaries below remain authoritative.

## 1. Core lifecycle principle

FlowTape application lifetime, scenario lifetime, and Selenium-controlled browser lifetime are distinct.

```text
Application lifetime
    != Scenario lifetime
    != Browser lifetime
```

The unit that the user launches is the FlowTape application, not a scenario.

Starting FlowTape must therefore not require an existing `scenario.yaml` or `elements.yaml`.

A scenario package is opened or created after the application is running.

## 2. Neutral startup state

Normal GUI startup enters a neutral `No Scenario` state.

Expected startup sequence:

```text
Launch FlowTape
    -> create FlowTape application window
    -> start or attempt to start the Selenium-controlled Edge window
    -> show No Scenario start view
    -> user chooses New Scenario or Open Scenario
```

The start view should make the primary choices obvious:

```text
FlowTape

No scenario is open.

[ + New Scenario ]
[   Open Scenario ]

Recent scenarios
- ...
```

The exact visual layout may evolve, but the user must not be required to create empty YAML files manually before reaching the GUI.

## 3. Browser startup and browser failure

The normal desktop experience should attempt to start the Selenium-controlled Edge browser together with the FlowTape GUI.

Browser startup failure must not terminate the FlowTape application.

If Edge or WebDriver cannot be started, FlowTape remains usable for scenario package creation, opening, inspection, and non-browser editing where possible, while browser-dependent commands are disabled.

The UI should expose a clear browser status and recovery actions such as:

```text
Browser: unavailable
Microsoft Edge could not be started.

[Retry] [Settings]
```

Recorder, Picker, Rebind, DOM diagnostics, and Player require a usable controlled browser.

When a scenario and valid browser configuration are loaded, an idle recording, URL-opening, or fresh-playback request may start the controlled browser before using the Recorder or Player. Record (including the empty-scenario command), Open URL, Play, and Continue-recording remain available after the old browser has closed. They must not require a separate browser-retry click. Check the existing session at this command boundary, since browser closure may not yet have been detected by polling; release a stale session before starting Edge. Unresolved capture blocks this launch until resolved. Missing/invalid configuration retains the setup/retry workflow. Startup failure leaves recording stopped and the command available for retry. Creating an empty package alone neither starts recording nor synthesizes a browser action.

The application window itself does not.

## 4. No Scenario state

When no scenario is open:

Enabled application-level operations include at least:

- New Scenario
- Open Scenario
- Recent Scenarios
- browser startup/retry
- direct browser navigation where useful
- application/runtime settings
- application exit

Scenario-dependent operations must be disabled, including at least:

- Record
- insertion recording
- Pick/Rebind that writes to a scenario registry
- scenario structural editing
- Save Scenario
- Player execution
- target diagnostics that require the current scenario registry

This is an explicit application state, not an unnamed empty scenario.

## 5. New Scenario

`New Scenario` is available both from the neutral start view and while another scenario is already open.

The minimum creation dialog asks for:

- scenario name
- destination location

A representative dialog is:

```text
Scenario name:
[ UI Testing Playground Test ]

Save under:
[ /home/user/FlowTape/scenarios/ ] [Browse]

Package to create:
/home/user/FlowTape/scenarios/UI Testing Playground Test/

[Cancel] [Create]
```

The exact naming/path widgets are implementation details.

### 5.1 Package creation

Creating a scenario creates the scenario package itself. The user must not be asked to hand-create the package files.

The initial package contains at least:

```text
<scenario-package>/
    scenario.yaml
    elements.yaml
```

Minimum initial `scenario.yaml`:

```yaml
version: 1
name: UI Testing Playground Test
mode: 実行
steps: []
```

Minimum initial `elements.yaml`:

```yaml
version: 1
pages: {}
```

The generated documents must pass the normal schema/package validation before the new package becomes the active scenario.

### 5.2 Creation failure

Package creation should be atomic from the user's perspective.

If FlowTape cannot create a valid package, it must:

- report the error
- avoid presenting a partially created package as successfully open
- return to the previous application/scenario state where possible

It must not silently overwrite an existing scenario package.

If the requested destination already exists, the user must explicitly choose another destination or an explicitly supported replacement/copy workflow. `New Scenario` must not merge unrelated files into an existing package directory.

## 6. Open Scenario

`Open Scenario` is available both from the neutral start view and while another scenario is open.

The user may select a scenario package directory or, where the native file dialog workflow makes this more practical, the package's `scenario.yaml`.

A valid package is resolved to the directory containing:

```text
scenario.yaml
elements.yaml
```

Before making it active, FlowTape performs the normal package checks, including:

- interrupted-save/recovery state
- YAML parsing
- scenario schema validation
- registry schema validation
- cross-file package validation

An invalid package must not terminate the FlowTape application.

The UI reports the error and keeps or returns to a valid application state.

## 7. Recent scenarios

FlowTape should maintain a recent-scenario list as application UI convenience state.

Recent-scenario metadata is not part of `scenario.yaml` and does not change scenario semantics.

Selecting a recent entry is equivalent to `Open Scenario` and must perform the same validation/recovery checks.

If a recent path no longer exists, FlowTape should report that fact and allow the stale entry to be removed without failing application startup.

## 8. Active Scenario state

Once a package is successfully created or opened, FlowTape enters `Scenario Open` state.

The existing Recorder, Scenario Editor, target registry, diagnostics, save/recovery, and Player behavior defined by the other specifications becomes available against that active package.

Only one scenario package is active in one FlowTape application window at a time in v1.

Opening or creating another scenario replaces the active scenario after the current scenario's unsaved-change policy has been resolved.

## 9. New/Open while another scenario is active

`New Scenario` and `Open Scenario` are not startup-only commands.

They must remain available while a scenario is open.

Before replacing the current active scenario, FlowTape resolves pending state.

If there are unsaved scenario/registry edits, the user must receive an explicit choice equivalent to:

```text
The current scenario has unsaved changes.

[Save and continue]
[Discard changes and continue]
[Cancel]
```

The requested New/Open operation proceeds only after that decision succeeds.

Pending Recorder operations, an active recording session, or active playback must also be brought to a safe explicit boundary before switching scenarios. FlowTape must not silently transfer Recorder/Player state from one scenario package to another.

## 10. Close Scenario

FlowTape provides a `Close Scenario` operation separate from application exit.

Closing the active scenario:

- resolves unsaved/pending state using the same safety rules as switching scenarios
- unloads scenario/editor/player state
- returns the FlowTape application to `No Scenario`
- does not by itself close the FlowTape application
- does not normally close the Selenium-controlled browser

This allows the user to finish one scenario and create/open another without restarting FlowTape or losing the useful browser session unnecessarily.

## 11. Application exit

Exiting FlowTape is distinct from closing a scenario.

Application exit must resolve:

- unsaved scenario changes
- pending/unconfirmed Recorder events
- active playback/recording shutdown
- browser/transport shutdown

After those checks, the application closes the controlled browser it owns and terminates.

## 12. Browser lifetime across scenario switches

The controlled Edge browser normally survives:

- Close Scenario
- New Scenario
- Open another Scenario

unless a browser restart is explicitly required by configuration/profile changes or recovery from a browser failure.

A newly opened scenario does not inherit semantic execution progress from the previously active scenario. It merely uses the current browser as its current browser state.

This is intentional because FlowTape supports state-dependent scenarios that may begin from the current browser state.

The user can always execute a self-starting scenario whose first actions establish its own URL/state.

At a fresh playback boundary, retain a valid current WebDriver window. If that handle has been closed and exactly one controlled tab survives, select that unique tab and establish fresh Recorder/Player window tracking before any preload or step command. Remove transports for closed top-level targets. Multiple surviving tabs without a valid current handle remain an explicit ambiguity. If the browser session is already gone, close its stale application resources and start a new browser using the loaded configuration. This is a new run boundary, not automatic browser restart or window guessing during an active/paused/failed run.

## 13. Application-level configuration

Runtime/environment configuration is application-level/environment-level state, not a property of one scenario package.

Scenario packages contain procedure semantics and their scenario-local DOM registry. They should not need a private `config.yaml` merely in order to exist.

The desktop application resolves one active runtime configuration containing settings such as:

- Edge executable/profile
- WebDriver absolute path
- credentials path
- logs/downloads/outputs roots
- timeout defaults
- window arrangement preferences
- playback/runtime defaults

The external `config.yaml` schema defined by `06-runtime-platform.md` remains valid. A packaged desktop application may remember the selected application configuration path through private application preferences, but that preference is not scenario data.

Changing configuration that requires a browser restart must be made explicit. It must not silently replace a live browser in the middle of recording or playback.

## 14. Menu/application commands

A representative File menu is:

```text
File
  New Scenario...
  Open Scenario...
  Recent Scenarios >
  Close Scenario
  ----------------
  Save
  Save As...        # optional/when supported
  ----------------
  Exit
```

`Save` is enabled only when a scenario is active.

`Save As` is optional for the first implementation. If implemented, it must create a coherent scenario package rather than copying only `scenario.yaml` and leaving registry/recovery state behind.

## 15. Startup CLI contract

GUI startup must support launching without a scenario argument.

Preferred forms:

```text
flowtape ui
```

Starts the application in neutral `No Scenario` state.

```text
flowtape ui /path/to/scenario-package
```

Starts the application and requests that package to be opened immediately. If opening fails, the application remains open in a usable neutral state and reports the error.

A scenario argument is therefore optional for the `ui` command.

Scenario-oriented non-GUI commands remain explicit and continue to require a scenario package where applicable, for example:

```text
flowtape validate /path/to/scenario-package
flowtape run /path/to/scenario-package
```

Application runtime configuration may still be supplied explicitly through CLI options. The GUI should also have an application-level way to resolve its normal configuration so that an end user is not required to type a scenario path merely to start the desktop application.

## 16. State model

The minimum application-level state model is:

```text
Application start
       |
       v
+------------------+
| No Scenario      |
| Browser ready or |
| unavailable      |
+------------------+
       |
       | New / Open
       v
+------------------+
| Scenario Open    |
| Browser ready or |
| unavailable      |
+------------------+
       |
       | New / Open another
       | Close Scenario
       +----------------------> No Scenario
```

Browser readiness is orthogonal to scenario state.

Conceptually the application therefore tracks at least two independent axes:

```text
Scenario: none | open
Browser:  unavailable | ready
```

Recorder/Player sub-states exist only when the required scenario/browser prerequisites are satisfied.

## 17. Recovery interaction at startup/open

Interrupted package-save recovery belongs to the package being opened, not to application startup in general.

Therefore:

- FlowTape can start normally even if no scenario has been selected
- recovery inspection occurs when a package is opened (including a recent/CLI-requested package)
- the user explicitly chooses rollback/complete according to the existing persistence specification
- cancelling recovery leaves the application running without activating that package

One broken/recovery-required package must not prevent FlowTape itself from starting.

## 18. Compatibility with Recorder/Editor specifications

The two-window model in `03-recorder-ui.md` remains unchanged:

1. FlowTape application window
2. Selenium-controlled browser window

This document only adds the application-level state above the existing scenario editor.

When no scenario is active, the normal scenario/structure panes may be replaced by a start view or disabled placeholder. Once a scenario is active, the existing Recorder/Editor layout is shown.

Recording remains an explicit start/stop operation and does not start merely because a new blank scenario was created.

## 19. Compatibility with runtime/platform specifications

The browser remains externally controlled through Selenium as defined in `06-runtime-platform.md`.

WebDriver is still externally managed and is not automatically downloaded by FlowTape.

A browser startup/configuration error becomes an application-visible `Browser unavailable` state rather than a reason that the desktop application cannot exist.

Scenario package files remain external to the executable.

## 20. Required initial implementation changes

The desktop implementation must no longer construct its main window under the assumption that a valid scenario path already exists.

At minimum, implementation needs distinct operations for:

- create application window without scenario model
- start/retry browser independently
- create scenario package
- open scenario package
- unload/close scenario package
- switch active package after resolving unsaved/pending state
- enable/disable actions according to scenario/browser prerequisites
- maintain optional recent-scenario application state

Existing package loading, validation, save/recovery, Recorder, and Player code should be reused behind these lifecycle operations rather than duplicated.
