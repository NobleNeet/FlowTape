# FlowTape Credential and Authoring UX

Status: specification

This document defines the application/Recorder authoring UX for runtime configuration, scenario package selection/creation, and credential reuse/registration.

It complements `03-recorder-ui.md`, `06-runtime-platform.md`, `07-data-schema.md`, `08-recorder-protocol.md`, and `12-application-scenario-lifecycle.md`.

For subjects explicitly covered here, this document is the authoritative authoring-UX specification. Persisted field legality remains defined by `07-data-schema.md`, browser-side secret capture rules remain defined by `08-recorder-protocol.md`, and general application/scenario/browser lifetime remains defined by `12-application-scenario-lifecycle.md`.

## 1. Goals

The desktop authoring workflow should allow a normal user to reach first recording/playback without hand-writing YAML.

The preferred first-use flow is:

```text
Launch FlowTape
    -> configure Edge / WebDriver if needed
    -> New Scenario or Open Scenario
    -> navigate browser
    -> record
    -> assign/reuse credentials when login inputs are encountered
    -> save
    -> play back
```

Manual editing of `config.yaml`, `credentials.yaml`, `scenario.yaml`, and `elements.yaml` remains supported, but is not required for the ordinary GUI workflow.

## 2. Application configuration UX

`config.yaml` remains application/environment-level configuration, not scenario data.

The GUI must provide an application-level settings workflow capable of creating or updating a usable runtime configuration rather than requiring the user to prepare `config.yaml` manually before first use.

Explicit saves create missing parent directories for the config or shared credential file. Directory-creation failures follow the same failure-aware persistence rules as file-write failures.

At minimum the settings UI should expose:

- Microsoft Edge executable when an explicit path is needed
- externally managed `msedgedriver` absolute path
- scenario root/directory
- logs directory
- downloads directory
- outputs directory
- credentials file path
- other runtime defaults already represented by the config schema where practical

A representative first-use view is:

```text
Browser settings

Edge executable:
[ auto/default or explicit path ] [Browse]

WebDriver:
[ C:\\CompanyTools\\EdgeDriver\\msedgedriver.exe ] [Browse]

Scenario directory:
[ ... ] [Browse]

Credentials file:
[ .../credentials.yaml ] [Browse]

[Save]
```

FlowTape must not automatically download/provision WebDriver. A GUI path picker is only a way to point at an externally managed driver.

If settings required for browser startup are missing/invalid, the application remains usable in `Browser unavailable` state according to `12-application-scenario-lifecycle.md`.

Changing browser/driver/profile/download configuration that requires browser restart must remain explicit and must respect recording/playback boundaries.

## 3. New Scenario UX

`New Scenario` should ask for:

- scenario name
- parent/save directory

The UI should show the resulting package directory before creation.

Preferred form:

```text
Scenario name:
[ UI Testing Playground ]

Save under:
[ /home/user/FlowTape/scenarios ] [Browse]

Package to create:
/home/user/FlowTape/scenarios/UI Testing Playground/

[Create]
```

The user is choosing a package directory, not a YAML file name.

FlowTape creates `scenario.yaml` and `elements.yaml` inside the new package according to `12-application-scenario-lifecycle.md`.

Existing package directories must not be silently overwritten or merged.

## 4. Open Scenario UX

The conceptual object being opened is a scenario package directory.

The primary GUI should therefore present package-directory selection where the native UI permits it.

Implementations may also accept direct selection of `scenario.yaml` as a compatibility/convenience path, but the user-facing model remains “open this scenario package”, not “open this one YAML file”.

Regardless of selection form, package validation/recovery rules from `12-application-scenario-lifecycle.md` apply before activation.

## 5. Credential storage model

FlowTape v1 uses one application/environment-level `credentials.yaml` selected by `config.yaml`.

Credential storage is deliberately not scenario-local.

A scenario package does not contain its own `credentials.yaml` as part of the normal v1 package model.

Conceptually:

```text
FlowTape runtime environment
├─ config.yaml
│   └─ credentials.path -> credentials.yaml
├─ credentials.yaml
├─ Scenario A/
│   ├─ scenario.yaml
│   └─ elements.yaml
├─ Scenario B/
│   ├─ scenario.yaml
│   └─ elements.yaml
└─ Scenario C/
    ├─ scenario.yaml
    └─ elements.yaml
```

This is intentional because the same credentials may be naturally reused by:

- multiple scenarios against the same site
- different sites sharing SSO credentials
- multiple procedures using the same service account
- multiple scenarios that switch among several named accounts

## 6. Credential groups are reusable authentication profiles

A credential group name is a user-chosen logical name for reusable authentication data.

It is not required to equal:

- scenario name
- scenario package directory name
- page ID
- site/hostname
- target name

Example:

```yaml
version: 1
credentials:
  社内SSO:
    username: user001
    password: secret
  Redmine管理者:
    username: admin001
    password: secret
```

Multiple scenarios and multiple sites may refer to the same group.

A single scenario may also refer to multiple groups.

Scenario references use the existing namespace syntax:

```text
${credential.<group>.<key>}
```

For example:

```yaml
- action: input
  target: ユーザーID
  value: ${credential.社内SSO.username}

- action: input
  target: パスワード
  value: ${credential.社内SSO.password}
```

## 7. Password recording safety boundary

The browser-side Recorder must continue to follow `08-recorder-protocol.md`:

- password plaintext is not emitted in `RawCaptureEvent`
- password plaintext is not written to normal diagnostics/logs/recovery/scenario files
- a password input is represented as a secret input requiring credential resolution

Credential registration/selection is therefore an application-side authoring workflow, not a relaxation of browser capture rules.

The Recorder must not depend on recovering a plaintext password from browser-side event data after the password input is committed.

## 8. Recorder credential-resolution workflow

When recording reaches a password/secret input, FlowTape must not require the user to type a raw `${credential.group.key}` string as the primary GUI workflow.

The Recorder should present an explicit choice:

```text
Authentication information

( ) Use existing credential group
    Group: [ 社内SSO ▼ ]

( ) Register new credential group
    Group name: [             ]

[Continue] [Cancel]
```

The exact widget layout may vary, but both choices must be available.

### 8.1 Use existing credential group

The UI lists available credential group names from the active application-level `credentials.yaml`.

Secret values must not be displayed in plaintext.

The UI may optionally show masked/non-secret hints where useful, for example a masked username, but displaying the password is not required.

Selecting an existing group means:

- use that group for the recorded scenario reference
- do not overwrite existing credential values with whatever the user typed during recording
- do not silently modify the selected group

For the password step, the generated value normally becomes:

```text
${credential.<selected-group>.password}
```

If a different key is explicitly selected/supported, the selected key is used instead.

### 8.2 Register new credential group

The Recorder must also allow creation of a new group during authoring.

A representative dialog is:

```text
New credential group

Group name:
[ Redmine検証 ]

User ID:
[ test-user ]

Password:
[ ******** ]

[Register and use]
```

The new group is written to the application-level `credentials.yaml` selected by `config.yaml`.

The scenario stores only credential references; it does not receive the plaintext credential values.

Credential-file persistence must be explicit and failure-aware. If the credential file cannot be updated safely, the scenario step must not be finalized as if credential registration succeeded.

Creating a group whose name already exists must not silently replace it. The UI must require explicit selection of the existing group or an explicit update/replace workflow.

## 9. Username/ID pairing during recording

A username/account ID field is usually an ordinary text input and therefore cannot be treated as secret solely from its HTML input type.

When a secret/password input is resolved to a credential group, FlowTape should look for a plausible immediately preceding or otherwise clearly associated recorded input that may represent the login ID/username.

If such a candidate exists, the user should be asked explicitly whether it belongs to the same credential group.

Offer pairing only when the selected or newly registered group contains a usable username string (non-empty after whitespace checking). Otherwise preserve the recorded username literal and do not offer a reference to a missing or blank username. This does not change manually authored credential schema legality.

Example:

```text
The preceding input “ユーザーID” appears to be part of this login.
Use 社内SSO.username for that step as well?

[Yes] [No]
```

If accepted, the earlier scenario step is changed from a literal value such as:

```yaml
value: user001
```

to:

```yaml
value: ${credential.社内SSO.username}
```

The matching must be conservative. FlowTape must not automatically reinterpret an unrelated earlier text input (for example a search field) as the username merely because it precedes a password field.

When confidence is insufficient, ask the user or leave the ordinary input unchanged.

## 10. Existing-group reuse versus new-group creation

The common Recorder paths are therefore:

```text
ID input
    -> password input
    -> secret detected
    -> choose existing group
    -> optionally pair preceding ID input with <group>.username
    -> scenario stores references only
```

or:

```text
ID input
    -> password input
    -> secret detected
    -> register new group
    -> write group to shared credentials.yaml
    -> pair ID input with <group>.username when confirmed
    -> scenario stores references only
```

This behavior is part of normal Recorder authoring and must not require later manual YAML editing for the ordinary login case.

## 11. Credential editing outside recording

Because credentials are reusable application-level data, the application should provide a credential-management entry point independent of one scenario when practical.

At minimum users should be able to:

- inspect available group names without exposing passwords
- add a group
- explicitly edit/update a group
- explicitly remove a group with warning when appropriate
- select/change the credentials file through application settings

A future implementation may provide richer reference analysis before deleting/renaming a group. Until then, destructive credential changes must not silently rewrite scenarios.

## 12. Failure and cancellation behavior

If the user cancels credential resolution for a password input:

- plaintext must still not be persisted
- the operation remains unresolved/pending or is discarded according to Recorder pending-operation rules
- FlowTape must not generate a runnable password step containing an empty/literal placeholder that appears valid

Credential resolution is a distinct pending state from target-rebind or navigation recovery. Cancelling or failing credential selection/registration must not start target reselection. Provide explicit retry of credential selection using the already confirmed target, or explicit discard of the pending operation. Timer polling must not repeatedly reopen credential dialogs. Clear the credential-pending state on completion, discard, or scenario unload.

If an existing credential reference is selected but missing required keys at playback/validation time, FlowTape reports an unresolved credential error rather than guessing another group/key.

## 13. Manual YAML compatibility

Manual authoring remains valid.

A user may continue to write:

```yaml
value: ${credential.社内SSO.username}
```

and maintain `credentials.yaml` manually.

The Recorder GUI is an authoring convenience over the same persisted credential namespace; it does not introduce a second credential representation.

## 14. Security and display rules

The existing security rules remain in force:

- scenario YAML stores references, not password plaintext
- normal logs/diagnostics must not reveal expanded credential values
- outputs must not contain secret-derived values where forbidden by the data/runtime specifications
- password fields in the credential-management UI are masked by default
- existing credentials are not overwritten merely because a recording session used different typed values
- credentials remain plaintext on disk in v1 and are protected by filesystem placement/permissions/policy

## 15. Implementation implications

Implementations should separate:

- application config editing
- credential store loading/persistence
- credential group selection/creation
- Recorder secret-input resolution
- username-step pairing
- scenario reference insertion

Do not implement Recorder credential handling as a text box that merely asks the user to memorize and type `${credential.<group>.<key>}` when the GUI can enumerate the credential store.

Do not add scenario-local credential files unless the specification is explicitly changed in the future.
