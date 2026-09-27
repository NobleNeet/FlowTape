# FlowTape Runtime and Platform

Status: initial specification before implementation

## 1. Target environment

Primary deployment target:

- Windows 11
- Microsoft Edge
- end user should not need to install Python

Primary development/test environment may be Linux.

FlowTape should therefore keep browser/DOM semantics portable and isolate OS-specific concerns.

## 2. Browser automation layer

The browser automation layer is Selenium.

The expected browser target for actual use is Microsoft Edge.

Linux development may use Microsoft Edge for Linux where practical so that browser-engine behavior remains close to the Windows deployment environment.

DOM-based Selenium behavior should be treated as cross-platform wherever possible.

## 3. Cross-platform design principle

The following should remain OS-independent:

- scenario semantics
- target resolution
- DOM locator generation
- accessible-name/role logic
- browser-side injected JavaScript
- condition and loop semantics
- YAML parsing/validation

Platform-specific logic should be isolated, including:

- executable paths
- filesystem path conventions
- browser/driver discovery
- download directories
- native file dialogs
- OS-specific process handling
- Windows-only native UI interaction, if later required

## 4. Packaging model

The intended distribution model is:

```text
FlowTape executable
    + external config
    + external scenarios
    + external elements definitions
    + replaceable browser/driver-related files/settings
```

The Python application is expected to be packaged using PyInstaller or an equivalent packaging step so that Python itself is not a prerequisite on the end-user PC.

## 5. Externalized files

Do not embed user-specific scenario data into the executable.

The following are expected to remain external:

- scenario YAML files
- `elements.yaml` or equivalent DOM registry files
- runtime configuration
- environment-specific browser/driver settings
- generated logs/results

This allows scenarios and environment settings to change without rebuilding the application.

## 6. WebDriver / browser-driver policy

Driver-related configuration should be replaceable independently from the executable.

The implementation must not assume one hard-coded absolute driver path compiled into the package.

The exact mechanism—explicit path, Selenium Manager, bundled-but-replaceable driver, or another strategy—will be selected during implementation testing.

Whichever method is chosen, environment-specific driver configuration belongs outside scenario logic.

## 7. Edge compatibility

A FlowTape scenario should not depend on the operating system when it only interacts with normal web DOM elements.

For example, these operations should behave equivalently in Linux Edge and Windows Edge when the page DOM is equivalent:

- click DOM button
- enter text
- select option
- read DOM text/value
- wait for element state
- resolve by role/name/label/CSS/XPath

OS-sensitive behavior must be identified separately rather than hidden inside normal DOM actions.

## 8. Native browser/OS UI boundary

Selenium controls web content, not every operating-system-native interface.

Examples that may require separate treatment:

- native file chooser dialogs
- OS credential dialogs
- external application windows
- browser permission prompts outside normal page DOM

Do not model these as ordinary DOM targets unless they are actually represented in the page DOM and accessible through Selenium.

## 9. Recorder windows

Expected first implementation:

- PySide6 desktop application window for FlowTape
- separate Selenium-controlled Edge/browser window

The FlowTape window manages recording/editing state while the browser remains a real interactive browser operated by the user during recording.

## 10. Injected JavaScript

The Recorder may inject JavaScript into the current page through Selenium in order to:

- observe user input/click events
- identify DOM elements
- collect metadata
- highlight elements in picker/debug modes

This JavaScript is part of the recording/inspection mechanism, not a replacement for Selenium playback.

## 11. Configuration boundary

The runtime configuration schema has not yet been finalized.

Likely responsibilities include:

- browser selection
- browser executable path override
- driver strategy/path override
- default timeout values
- scenario and registry locations
- log/output locations
- Recorder-related runtime settings

Do not prematurely mix these values into scenario YAML unless they directly affect procedure semantics.

## 12. Paths

Use path abstractions that work on both Linux and Windows.

Avoid assumptions such as:

- `/home/...` always exists
- drive letters always exist
- path separator is always `/` or always `\\`

Use platform-neutral path handling in Python.

## 13. Downloads and uploads

Download directories and upload file paths are environment-sensitive and should be resolved through configuration/variables rather than hard-coded recording-machine absolute paths.

A recorded operation should not accidentally serialize a developer-machine path as a permanent portable scenario value unless the user explicitly chooses that behavior.

## 14. Logging and diagnostics

Logs should make platform-sensitive failures distinguishable from target-resolution failures.

For example:

```text
TargetResolutionError
BrowserStartupError
DriverConfigurationError
NativeDialogUnsupportedError
ScenarioValidationError
```

Exact exception names are not yet fixed; the requirement is to preserve the distinction.

## 15. Initial implementation priority

For the first implementation, prioritize ordinary DOM automation that is portable between Linux development and Windows 11 Edge deployment.

Defer specialized native-OS automation until the browser/DOM recording and playback path is stable.
