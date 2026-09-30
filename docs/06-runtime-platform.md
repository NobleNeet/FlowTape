# FlowTape Runtime and Platform

Status: initial specification before implementation

## 1. Target environment

Primary deployment target:

- Windows 11
- Microsoft Edge
- end user should not need to install Python
- managed/corporate environments may have restricted network access and may reset user-profile/environment state at logoff

Primary development/test environment may be Linux.

FlowTape should keep browser/DOM semantics portable and isolate OS-specific concerns.

## 2. Browser automation layer

The browser automation layer is Selenium.

The expected browser target for actual use is Microsoft Edge.

Linux development may use Microsoft Edge for Linux where practical so browser-engine behavior stays close to Windows deployment.

## 3. Cross-platform design principle

The following should remain OS-independent where practical:

- scenario semantics
- page identification
- target resolution
- DOM locator generation
- accessible-name/role logic
- browser-side injected JavaScript
- condition and loop semantics
- YAML parsing/validation

Platform-specific logic should be isolated, including:

- executable paths
- filesystem path conventions
- browser/driver startup
- download directories
- output directories
- native dialogs
- OS-specific process handling
- optional window placement

## 4. Packaging model

Intended distribution:

```text
FlowTape executable
    + external config.yaml
    + external credentials.yaml
    + external scenario packages
    + externally managed WebDriver
    + optional external persistent browser profile
    + generated logs/outputs/downloads
```

The Python application is expected to be packaged with PyInstaller or equivalent so Python itself is not required on the end-user PC.

## 5. Externalized files

Do not embed user-specific scenario/runtime data into the executable.

Expected external data includes:

- scenario directories containing `scenario.yaml` + `elements.yaml`
- `config.yaml`
- `credentials.yaml`
- WebDriver executable at an administrator/user-managed absolute path
- optional Edge profile directory
- generated logs/outputs/downloads

## 6. WebDriver policy

WebDriver is never automatically downloaded or provisioned by FlowTape.

The expected corporate environment may not provide a mechanism for automatic Selenium/WebDriver retrieval. Therefore:

- the user/administrator places `msedgedriver.exe` in an externally managed location
- `config.yaml` contains the full absolute path
- `driver.path` is required
- relative driver paths are not accepted
- FlowTape does not use Selenium Manager as a fallback
- FlowTape does not silently search PATH or guess another driver
- FlowTape does not require a `driver/` directory under its own installation directory

Example:

```yaml
driver:
  path: 'D:\\CompanyTools\\EdgeDriver\\msedgedriver.exe'
```

At browser startup FlowTape validates that the configured file exists and can be invoked. Missing/invalid paths fail before normal scenario execution with a driver-configuration diagnostic.

If Edge/WebDriver versions are incompatible, FlowTape reports the problem; it does not attempt an automatic update/download.

## 7. Configuration file

`config.yaml` is the runtime/environment configuration file.

Configuration belongs to the application/environment, independently of a scenario package (`12-application-scenario-lifecycle.md`). `flowtape ui` accepts optional scenario and `--config` arguments. Without an explicit config, the GUI may load a previously selected configuration from private application preferences. If no valid configuration is available, the application remains open with Browser unavailable and provides Settings to select an external config. FlowTape never invents or downloads a driver path. Browser/driver/profile/download-directory changes require explicit browser restart confirmation and a safe recording/playback boundary; other runtime defaults can change without replacing the browser.

Representative initial shape:

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

Persisted duration values use explicit units (`ms`, `s`, `m`, or `h`) as defined in `07-data-schema.md`; bare numeric seconds are not valid v1 configuration syntax.

Relative paths other than `driver.path` are resolved relative to the directory containing `config.yaml` unless a more specific specification says otherwise.

Runtime/environment settings should not be mixed into scenario YAML unless they directly change procedure semantics.

Guided first-use Edge/WebDriver setup follows `14-primary-user-flows-and-ui-hierarchy.md`, using schema defaults and separate application data roots without downloading a driver. The complete desktop Settings workflow can create/update this config without hand-written YAML (`13-credential-and-authoring-ux.md`). It exposes browser/profile/driver paths, scenario/log/download/output roots, credentials path, timeouts, loop limits, playback defaults, logging and destructive confirmation. The GUI validates the config and respects restart/recording/playback boundaries before saving; failure does not install the new configuration.

## 8. Credentials file

IDs and passwords are stored separately in plaintext `credentials.yaml`.

Example:

```yaml
version: 1

credentials:
  社内システム:
    username: user001
    password: password123
```

The configuration selects its location:

```yaml
credentials:
  path: ./credentials.yaml
```

This design is intentional for managed environments where environment variables and user-profile data may be reset at logoff.

Security rules:

- scenarios refer to credentials through the dedicated `credential` namespace
- credential values are never written to normal logs/debug output/error text after expansion
- GUI/diagnostic displays mask secret values
- password recording must not serialize the entered plaintext into `scenario.yaml`
- `credentials.yaml` is excluded from source control
- a `credentials.example.yaml` placeholder may be committed

Plaintext file storage means filesystem access to this file reveals the credentials. Protection is therefore delegated to placement, OS/file permissions, and corporate storage policy in v1.

The shared application-level store can be managed from Settings or selected/extended during Recorder secret-input authoring (`13-credential-and-authoring-ux.md`). Existing group reuse never replaces values from captured browser input. Updates/removal are explicit and do not rewrite scenarios. Single-file saves validate the store, detect changed content/writer conflicts, stage a user-only temporary file, and atomically replace the destination; no credential values enter scenario save journals or recovery files.

## 9. Browser profile and session policy

FlowTape supports both temporary and persistent Selenium Edge profiles.

```yaml
browser:
  profile_path: 'D:\\FlowTapeData\\edge-profile'
```

Rules:

- if `profile_path` is omitted/null, FlowTape may use a temporary isolated profile
- if supplied, FlowTape uses that dedicated persistent profile so cookies/session/SSO state can survive launches where the environment permits it
- use of a dedicated FlowTape profile is preferred over sharing a user's ordinary interactive Edge profile
- the profile path is runtime configuration, not scenario semantics

## 10. Edge compatibility

A scenario that interacts only with normal web DOM/browser primitives should not depend on the OS when the page behavior is equivalent.

Expected portable operations include:

- click/double-click
- input/select/read
- result `append` to configured output storage
- hover/key operations
- DOM file upload
- page-state waits/checks
- JavaScript alert/confirm/prompt handling through Selenium
- target resolution by semantic/CSS/XPath strategies
- ordinary tab/window switching

OS-sensitive behavior must remain explicit.

## 11. Native browser/OS UI boundary

Selenium controls web content and supported browser context, not every native OS interface.

Examples outside ordinary DOM automation:

- native file chooser UI
- OS credential dialogs
- external application windows
- native browser permission UI not exposed through supported Selenium/browser mechanisms

`<input type="file">` is supported through the DOM without automating the native file chooser.

## 12. Recorder windows

Expected first implementation:

- PySide6 FlowTape application window
- separate Selenium-controlled Edge/browser window

The browser should not be embedded into PySide6 for the initial implementation.

When practical FlowTape may arrange the windows side-by-side at startup. Window placement is a usability feature only and must not be required for correctness.

The implementation should:

- attempt convenient initial placement where supported
- allow normal user move/resize
- remember/respect a user-established layout where practical
- avoid forcing automatic placement every launch after a usable layout is known
- never identify page elements by desktop coordinates

## 13. Injected JavaScript

Recorder JavaScript may be injected through Selenium to:

- observe input/click-related events
- collect DOM metadata
- identify elements
- highlight picker/debug targets

It remains recording/inspection infrastructure rather than a replacement playback engine.

Detailed Recorder protocol, reinjection, and event normalization rules are defined in `08-recorder-protocol.md`.

## 14. Paths

Use platform-neutral path handling in Python.

Do not assume:

- `/home/...` exists
- Windows drive letters exist on all platforms
- one path separator convention

The WebDriver path is the intentional exception to portable-relative-path defaults: it is required to be an absolute path configured by the operator.

Scenario output definitions use relative paths under configured `paths.outputs`; they must not escape that root.

## 15. Downloads

The configured download directory is environment-specific.

Scenario steps should not accidentally serialize a developer-machine absolute download path.

A normal click may start a download. Completion can be awaited through the DSL's `download_complete` wait condition.

FlowTape should detect completion using the configured download directory and browser download behavior; temporary/in-progress files must not be treated as completed downloads.

## 16. Uploads

Upload paths may be supplied through normal scenario variables/configuration as appropriate.

DOM `<input type="file">` is supported. Native file chooser automation is not required in v1.

## 17. Outputs

Scenario result outputs are distinct from FlowTape diagnostic logs and browser downloads.

- `scenario.yaml` declares logical outputs and relative file names.
- `config.yaml` supplies the environment-specific `paths.outputs` root.
- `append` writes user-requested result data according to `09-runtime-semantics.md`.
- credential/secret-derived values must never be written to outputs.
- `existing: new`, `append`, and `overwrite` behavior follows the schema/runtime specifications.

The platform layer is responsible for safe cross-platform path handling and creation of the required output directories, not for changing scenario-level output semantics.

## 18. Browser windows/tabs

Window/tab handles are managed through Selenium plus FlowTape's own parent relationship tracking.

When an operation in A produces a new window B, FlowTape records B's parent as A when deterministically observable.

If B closes automatically after its operation:

- detect B's disappearance
- return automatically to the known parent A if it still exists
- re-identify the current page before continuing

If B remains open, FlowTape stays on B until an explicit scenario context operation changes it.

If the current window disappears and the correct parent/return target cannot be determined uniquely, FlowTape fails rather than selecting an arbitrary remaining window.

This parent relation is a FlowTape runtime relation and must not depend solely on JavaScript `window.opener`.

## 19. Scenario starting state

A scenario may be self-starting or state-dependent.

Self-starting example:

```yaml
- action: open
  url: https://example.com
```

A scenario may also omit initial navigation and intentionally begin from the current browser state.

For state-dependent starts, FlowTape identifies the current page before executing target-dependent operations. If the expected state cannot be established unambiguously, execution stops with diagnostics.

This enables workflows such as playing a partially recorded scenario to its current end and handing control back to the user/Recorder for continuation.

## 20. Logging and diagnostics

Logs must distinguish categories such as:

```text
TargetResolutionError
UnknownPage
AmbiguousPage
BrowserStartupError
DriverConfigurationError
BrowserContextError
NativeDialogUnsupportedError
ScenarioValidationError
OutputWriteError
```

Exact exception class names are implementation details, but diagnostic categories must remain distinct.

Credentials/secrets must never be exposed in normal logs or diagnostics.

## 21. Initial implementation priority

Prioritize ordinary browser/DOM automation portable between Linux development and Windows 11 Edge deployment.

v1 includes:

- normal DOM actions
- page-scoped target resolution
- checks/waits and download-completion waits
- simple scenario outputs (`csv`, `jsonl`, `text`) through `append`
- DOM file upload
- keyboard and hover operations
- limited Selenium-compatible drag/drop
- JavaScript alert/confirm/prompt operations
- new-tab/new-window workflows
- popup auto-return to a known parent

Defer specialized native-OS automation until the browser/DOM path is stable.

## 22. Editor persistence and recovery

User-authored scenario/registry files use explicit saves rather than unconditional background overwrite.

FlowTape may maintain separate private recovery data after crashes, but recovery state must not silently replace authoritative files.

## 23. External file change detection

Scenario and registry files are intentionally external/editable. FlowTape should detect external modifications while open.

If external changes conflict with unsaved GUI edits, the user must be given an explicit reconciliation choice. Silent overwrite is not acceptable.

## 24. Initial appearance policy

The initial UI may rely on Qt/platform-default appearance and controls. Dedicated custom themes are not required for the first implementation.

Accessibility and readability take priority over custom theming during the initial implementation.
