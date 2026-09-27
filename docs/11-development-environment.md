# Development Environment

## Purpose

This document defines the development and test environment constraints for FlowTape v1.

These rules apply to Codex CLI and any other automated development agent operating in the dedicated development VM.

Product behavior and persisted formats remain governed by the other specification documents under `docs/`. This document governs development permissions, dependency installation, browser usage, external test-site usage, and side-effect boundaries.

## Environment model

FlowTape development is performed inside a dedicated VirtualBox VM.

Codex CLI is started from the cloned FlowTape repository directory and operates as a normal, non-root user.

The VM is disposable as a development environment. Changes inside the VM are generally allowed when they are necessary for implementing, building, or testing FlowTape, provided they stay within the permission and external-side-effect limits defined below.

## Privilege boundary

### Root and sudo are forbidden

Development agents must not perform any operation that requires root privileges or privilege escalation.

The following are explicitly forbidden:

- `sudo`
- `su`
- obtaining or attempting to obtain a root shell
- running commands as root
- changing system-owned files that require elevated privileges
- modifying system services
- modifying system-wide package state
- installing OS packages through `apt`, `apt-get`, or another system package manager
- modifying the system Python installation in a way that requires elevated privileges
- attempting privilege escalation as a workaround for a missing dependency

A missing dependency is not permission to elevate privileges.

If an implementation or test requires an OS-level dependency that is not already available, first look for a non-root alternative. Examples include:

- a Python wheel
- a user-local binary
- a portable binary
- a repository-local tool
- a pure-Python implementation
- Selenium Manager
- a mock or local fixture for functionality that cannot otherwise be exercised

If no reasonable non-root alternative exists, do not install the dependency. Record the missing dependency, the affected functionality or test, and the limitation in the final report.

## Preinstalled OS packages

The user has already performed the following setup before starting Codex CLI:

```bash
sudo apt update

sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    binutils \
    git \
    curl \
    wget \
    pkg-config

sudo apt install -y \
    libgl1 \
    libegl1 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libxcb-xinerama0
```

Treat these packages as already available.

Do not rerun these installation commands and do not add further `apt install` commands during automated development.

## Python dependencies

Python packages required for FlowTape may be installed freely as long as this is done without root privileges.

Prefer a repository-local virtual environment, for example:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ...
```

Permitted examples include:

- Selenium
- PySide6
- PyYAML or another YAML implementation selected by the project
- schema validation libraries
- pytest and related test tools
- formatters
- linters
- type checkers
- PyInstaller
- other Python dependencies reasonably required by the implementation

Do not use `sudo pip`, do not modify the system Python installation, and do not treat PEP 668 or similar protections as something to bypass.

Project dependency metadata should be maintained in the repository where appropriate, for example with `pyproject.toml`, requirements files, or lock files.

## Microsoft Edge

Microsoft Edge is already installed in the VM and may be used freely for FlowTape development and testing.

It may be used for:

- Selenium integration tests
- Recorder tests
- Player tests
- end-to-end scenario tests
- headed browser tests
- headless browser tests
- localhost fixture tests
- the approved external test sites listed below
- normal WebDriver and DevTools-based automation needed by the project

Prefer an isolated temporary profile or FlowTape-specific test profile instead of relying on or modifying an existing everyday browser profile.

Agents may launch and terminate Edge repeatedly as needed for testing.

Do not reinstall, upgrade, or modify the system-wide Edge installation if doing so requires root privileges.

If an Edge WebDriver is required, prefer Selenium Manager or another user-space mechanism that does not require root privileges or system package installation.

## Operations allowed inside the VM

Subject to the no-root rule, development agents may perform operations inside the VM that are reasonably required for FlowTape development.

Examples include:

- creating or deleting Python virtual environments
- installing Python packages inside a virtual environment
- creating repository-local build and test artifacts
- adding, modifying, or deleting files in the FlowTape repository
- creating temporary files and test data
- downloading user-space development tools or portable binaries
- changing user-owned configuration required for testing
- starting and stopping Microsoft Edge
- starting local HTTP servers on `localhost`
- creating local HTML fixtures for browser tests
- performing local Git operations
- reading from GitHub
- running `git fetch`
- downloading dependencies, source archives, documentation, or test resources
- accessing the approved public test sites below

Local Git commits are allowed.

## External side-effect boundary

The VM is the boundary within which changes are permitted.

Development agents must not intentionally modify state outside the VM, except for the explicitly approved, non-destructive web test interactions described later in this document.

The following are forbidden:

- modifying files on the VirtualBox host OS
- writing through VirtualBox Shared Folders to change host-side files
- changing host OS settings
- changing data on attached external devices such as USB storage
- modifying other machines on the LAN
- using SSH or another remote shell to modify another machine
- changing cloud infrastructure or external service configuration
- modifying production systems
- making persistent changes to unrelated third-party services
- pushing changes to GitHub
- creating or modifying GitHub Pull Requests
- creating or modifying GitHub Issues
- creating or modifying GitHub Releases
- changing other remote repositories

`git push` is explicitly forbidden.

Network access itself is allowed. Reading documentation, downloading dependencies, fetching Git data, and exercising approved test sites are permitted.

When uncertain, apply both of these rules:

1. If the operation requires root or `sudo`, do not perform it.
2. If the operation may modify state outside the VM, do not perform it unless this document explicitly allows that test interaction.

## Approved browser test sites

The following public sites may be used for normal functional browser-automation testing.

### UI Testing Playground

https://www.uitestingplayground.com/

This site is intended for UI automation practice and may be used to test cases such as:

- Dynamic ID
- Hidden Layers
- Load Delay
- AJAX Data
- Client-side Delay
- Click behavior
- Text Input
- Scrollbars
- Visibility
- other equivalent automation-focused examples exposed by the site

### SauceDemo / Swag Labs

https://www.saucedemo.com/

This site may be used for end-to-end browser flows such as:

- login
- product listing
- add to cart
- cart review
- checkout flow

Use only credentials explicitly published for testing by the service.

Do not use real personal credentials or personal information.

### Selenium official sample pages

Official Selenium documentation sample pages may be used for minimal WebDriver behavior checks, including:

- text input
- submit
- select
- checkbox
- navigation
- element retrieval
- other basic Selenium examples

## Limits on external test-site usage

Approved external sites are an exception to the general rule against changing state outside the VM only to the extent necessary for ordinary, intended test interaction.

Testing must remain non-destructive and proportionate.

Do not perform:

- load testing
- stress testing
- denial-of-service-like repeated requests
- vulnerability scanning
- exploit attempts
- destructive operations
- attempts to bypass authentication or authorization
- use of real personal credentials
- actions unrelated to FlowTape browser automation testing

Prefer localhost fixtures when stable reproduction is more important than testing against a live public site.

## Local browser fixtures

Development agents are encouraged to build localhost fixtures for deterministic browser tests.

Appropriate fixture cases include:

- dynamic IDs
- DOM replacement
- delayed rendering
- AJAX-like updates
- hidden or disabled controls
- duplicate target ambiguity
- iframes
- nested frames
- shadow DOM
- input events
- IME-related protocol sequences where practical
- click / double-click normalization
- navigation and reinjection
- picker click suppression

Local fixtures should be used when an external site would make the test flaky or difficult to reproduce.

## Cross-platform implications

The development VM is Linux, while the primary deployment target includes Windows 11 with Microsoft Edge.

Development inside this VM must therefore avoid assumptions that only work accidentally on Linux.

Keep platform-specific behavior isolated, especially for:

- paths
- executable discovery
- browser binary discovery
- WebDriver discovery
- downloads
- filesystem behavior
- process invocation
- native UI behavior

Windows-only behavior that cannot be exercised in the Linux VM should be covered as far as practical with abstraction, unit tests, mocks, and code review, then reported as not yet verified on a Windows host.

Do not attempt to reach outside the VM to a Windows machine merely to complete such testing.

## Packaging and build tools

User-space build and packaging tools may be installed and used, including PyInstaller, if they do not require root privileges.

Build outputs may be created inside the VM.

If packaging cannot be completed because of a missing root-only OS dependency, report the limitation rather than installing the dependency with elevated privileges.

## Final reporting requirement

At the end of a substantial implementation task, report environment-related limitations explicitly.

If applicable, include:

- dependencies that could not be installed because they require root privileges
- tests skipped because of missing OS-level dependencies
- Windows-specific behavior not verifiable in the Linux VM
- browser integration tests actually performed with the installed Microsoft Edge
- public test sites used
- localhost fixtures used

Before finishing, confirm that no forbidden external write operation or privilege escalation was performed.
