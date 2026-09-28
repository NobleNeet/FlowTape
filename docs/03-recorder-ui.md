# FlowTape Recorder and Scenario Editor UI

Status: initial specification before implementation

## 1. Overall UI concept

The expected desktop implementation uses PySide6 for the FlowTape application UI and Selenium to control a separate browser window.

The conceptual UI has two physical windows:

1. FlowTape application window
2. Selenium-controlled browser window

Inside the FlowTape application, the primary editing layout should use two panes:

- scenario/structure view
- selected-item properties / target details

Conceptually:

```text
Selenium browser                  FlowTape application
+--------------------------+      +----------------------+------------------+
|                          |      | Scenario / Structure | Properties       |
| Real target Web page     |      |                      |                  |
|                          |      | vertical step list   | selected action  |
| hover/pick/highlight     |      | nested range blocks  | target/condition |
|                          |      |                      | diagnostics      |
+--------------------------+      +----------------------+------------------+
```

The browser is the place where the user indicates real DOM elements. The scenario/structure view shows execution flow, and the properties pane edits the meaning/details of the currently selected step or structural block.

The exact widget implementation may evolve, but these responsibilities and the two-window model should remain separated.

Application startup and New/Open/Close operations are defined by `12-application-scenario-lifecycle.md`. The GUI starts without requiring a scenario package. In `No Scenario`, a start view offers New/Open and recent packages; the editor appears after validated activation. Browser readiness is independent: browser failure leaves non-browser editing available. Closing a scenario normally retains the controlled browser; exiting the application shuts it down after resolving pending and unsaved state.

## 2. Recording model

The Recorder is optimized for recording a normal successful path.

Typical flow:

```text
Start recording
    -> operate browser normally
    -> each meaningful operation becomes a step
    -> stop recording
    -> review steps
    -> add structure such as loops/conditions afterward
```

The Recorder should not force the user to define branching logic while demonstrating the normal path.

The intended responsibility split is:

- Recorder: capture linear browser operations and acquire/reacquire DOM targets
- Scenario Editor: add or modify control-flow semantics such as conditions, loops, and alternate branches after recording

Both may live in the same FlowTape application window, but their responsibilities should remain conceptually distinct.

## 3. Browser-side observation

JavaScript injected into the controlled page observes user operations and DOM information.

It should support at least:

- hover tracking for picker/highlight use
- click/double-click observation
- text/input change observation
- selected option changes
- operation target capture
- DOM metadata collection

Captured browser events are sent back to the Python application for normalization and semantic interpretation.

## 4. Vertical step list

Recorded operations are shown as a vertical sequence in execution order.

Conceptual appearance:

```text
01  Open      https://example.com
02  Input     メールアドレス = test@example.com
03  Input     パスワード = ${credential.社内システム.password}
04  Click     ログイン
05  Click     次へ
06  Click     次へ
07  Click     完了
```

When a password field has been recorded but no credential reference has yet been assigned, the UI should display an explicit unresolved/credential-required state rather than the captured plaintext value.

The ordinary GUI resolution is group/key selection or explicit new-group registration, as defined in `13-credential-and-authoring-ux.md`; it does not require manually typing a reference string. A plausible preceding username input may be paired only after explicit confirmation. Cancellation or credential persistence failure keeps the secret operation pending without creating a literal/empty password step. The application-level Settings and credential manager work independently of an active scenario.

Each row should expose the operation in human-readable terms rather than raw Selenium details.

## 5. Range selection and structural blocks

Conditions and loops are added by selecting a contiguous range of recorded steps.

Example before wrapping:

```text
04 Click 次へ
05 Read  明細
06 Click 次へ
```

The user selects steps 04-06 and chooses a structure such as `while`.

Conceptual result:

```text
┌ while: 「次へ」が存在する
│ 04 Click 次へ
│ 05 Read  明細
│ 06 Click 次へ
└
```

The UI should visually bracket the range so that nesting remains understandable.

The same editing model applies to:

- `if`
- `else`
- `repeat`
- `for_each`
- `while`

Nested blocks are allowed as long as the resulting YAML remains structurally valid.

## 6. Natural-language summaries

Structural blocks should be summarized in a human-readable form in the editor.

Examples:

```text
「次へ」が存在する間、繰り返す
検索結果が存在する場合
一覧の各行について繰り返す
3回繰り返す
```

The UI is not required to expose raw YAML syntax for every editing operation, though a YAML view/editor may exist separately.

## 7. Target naming

When a recorded operation creates a new target, FlowTape should propose a logical name automatically.

Possible sources include:

- associated label
- accessible name
- visible text
- aria-label
- nearby meaningful heading/context

Examples:

```text
メールアドレス
ログイン
注文を確定
プロフィール/保存
```

The user must be able to rename the logical target.

Machine-generated names such as `button_2` should be avoided when a meaningful name can be inferred.

## 8. Target collision handling

When a page contains multiple elements with the same human-facing label, FlowTape should prefer contextual naming rather than numeric suffixes where practical.

Preferred:

```text
プロフィール/保存
通知設定/保存
```

Less desirable:

```text
保存
保存_2
```

Numeric fallback may still be used temporarily when no meaningful context can be inferred, but the UI should make the ambiguity visible.

## 9. Element Picker

Element Picker mode allows a user to register one target without recording a whole scenario.

Typical flow:

```text
Activate picker
    -> hover highlights page elements
    -> click desired element
    -> FlowTape analyzes element
    -> proposed target name appears
    -> user confirms/renames
    -> target written to elements.yaml
```

The browser-side highlight must not itself be recorded as an application operation.

The same picker mechanism should also be callable from structural editing when a condition or loop depends on a DOM element.

Example:

```text
Select a while block
    -> choose condition "element exists"
    -> click "select from browser"
    -> browser enters element-pick mode
    -> user clicks "次へ"
    -> FlowTape binds the condition to logical target "次へ"
```

DOM-dependent control-flow configuration should therefore reuse the same Element Capture Engine as Recorder/Picker/Bind rather than introducing a separate selector-entry workflow.

## 10. Bind missing targets

Hand-written scenarios may contain unresolved names.

Example:

```yaml
- action: click
  target: 注文を確定
```

Bind mode scans the scenario and reports unresolved targets.

Conceptual UI:

```text
未登録 target: 3

- メールアドレス
- パスワード
- 注文を確定
```

For each target, the user can navigate the browser into the correct state and select the corresponding element.

The same Element Capture Engine used by Recorder generates the registry entry.

Normal execution should not unexpectedly enter interactive binding mode. Binding is a deliberate editing workflow.

## 11. Existing target rebinding

The user should be able to select an existing logical target and reassign it to a current DOM element.

Use cases:

- target DOM changed
- old locator became fragile
- recorded wrong element
- better semantic element became available

Rebinding should regenerate locator candidates and replace/update the target definition while preserving the logical name unless the user also renames it.

## 12. Diagnostic view

Debugging a target should make at least the following visible:

- logical target name
- expected kind
- saved locator candidates
- match count for each candidate
- which locator was selected
- rejected-candidate reason
- fragile marker
- relevant context such as iframe/shadow root

Candidate elements should be highlightable in the browser.

## 13. Recorder target normalization

The UI must display/record the normalized actionable element, not necessarily the deepest DOM node under the pointer.

Example:

```html
<button aria-label="保存">
  <svg><path /></svg>
</button>
```

Clicking the `path` should normally appear as a click on `保存`, not as a click on an SVG path.

## 14. Recorder and editor separation

Recording and structural editing should be conceptually separate operations:

- Recorder: captures what happened and which real DOM targets were involved
- Scenario Editor: describes when/how often recorded or manually added operations happen

This separation is intentional and should remain even though both features share one FlowTape application window.

A typical edit cycle is therefore:

```text
record a normal linear path
    -> stop recording
    -> select a step/range
    -> wrap or edit structure
    -> if the structure needs a DOM-dependent condition, invoke browser picker
    -> validate
    -> play back
```

## 15. Manual YAML editing

Manual YAML editing is a supported workflow.

The GUI should therefore not assume every valid scenario was produced by Recorder.

After an external/manual edit, FlowTape should be able to:

- reload the scenario
- validate it
- identify unbound targets
- display its structural blocks
- allow binding/repair through the GUI

## 16. Scope of first implementation

The first usable Recorder should prioritize:

- reliable capture of common click/input/select operations
- target creation
- vertical step list
- two-pane FlowTape editor layout (scenario/structure + properties)
- target rename/rebind
- missing-target binding
- simple range wrapping for conditions/loops
- invoking Element Picker from DOM-dependent condition/loop properties

Advanced visual editing can follow after these core semantics are stable.

## 17. Recorder interaction modes

The initial UI should distinguish three browser-interaction intents:

- Record: normal browser operations are converted into scenario steps
- Pick: browser clicks indicate an element for a target/condition/source without recording the click as a normal step
- Rebind: browser selection replaces the DOM definition for an existing logical target

These modes may share internal picker/capture machinery, but the user-facing intent should remain explicit.

Recording is controlled by an explicit start/stop action. Stopping recording does not close the Selenium browser; the browser remains available for editing, picking, rebinding, validation, and resumed recording.

## 18. Step selection and structural editing

The scenario list should support conventional desktop selection behavior:

- normal click: select one step/block
- Shift-click: select a contiguous range
- Ctrl-click: may select multiple items for generic operations

Control-flow wrapping operations require one contiguous range. Discontiguous selections must not be silently converted into a block.

After selecting a contiguous range, the UI should offer operations such as:

```text
条件付きにする
繰り返しにする
削除
```

The user should not be required to draw block brackets manually.

v1 has no persisted `GroupNode`. A future visual-only grouping affordance must not be serialized as an unsupported scenario node unless the schema is explicitly extended.

For `if`, the `else` branch is added deliberately through an action such as `それ以外を追加`; an empty `else` branch is not created automatically.

For loops, user-facing choices should use natural language:

```text
各対象について      -> for_each
条件を満たす間      -> while
指定回数            -> repeat
```

DSL terminology may still be shown secondarily for advanced users.

## 19. For-each source selection

`for_each` requires collection semantics rather than merely one uniquely resolvable element.

The preferred authoring flow is:

```text
choose "各対象について"
    -> choose "ブラウザから繰り返し対象を指定"
    -> user selects one representative row/item
    -> FlowTape derives candidate collection selectors
    -> browser highlights all current members
    -> UI shows detected count/examples
    -> user confirms or chooses another candidate
```

The collection definition must remain distinct from a normal single-target definition even if both reuse capture/scoring infrastructure.

## 20. Step insertion and resumed recording

Existing scenarios must support insertion recording.

Between steps, the editor may expose an insertion affordance such as `+`. From that position the user may:

- add a step manually
- start recording from this insertion point

Existing later steps remain intact. Newly recorded steps are inserted at the chosen position when recording stops.

The same concept applies to extending a partially completed scenario: FlowTape can play the existing scenario to its current end, stop there, and switch to recording so the user can demonstrate the continuation.

## 21. Playback control

Execution semantics (`実行` / `確認` / `デバッグ`) and playback pacing are separate dimensions.

The UI should support at least:

- normal continuous playback
- slow playback with a configurable observation delay after each completed step
- single-step playback, waiting for the user after each step
- execute until a selected position and pause
- pause/resume/stop
- play to current scenario end and continue recording

Slow playback adds an observation delay after the normal step completion/wait logic; it must not replace proper Selenium waits with fixed sleeps.

A typical control surface may expose:

```text
モード: [実行 ▼]
再生:   [通常 / 1秒 / 2秒 / 5秒 / ステップ ▼]

[最初から実行]
[選択位置まで]
[1ステップ]
[一時停止]
[停止]
[ここから記録]
[続きを記録]
```

Breakpoint-style stopping may be added later, but selected-position execution is sufficient for the first implementation.

## 22. Editing while paused

Editing while playback is paused is supported.

If the user edits only not-yet-executed steps, execution may continue normally after validation.

If the user edits a step that has already contributed to the current browser state, FlowTape must warn that the live browser state reflects the old scenario. The UI should offer at least:

- restart from the beginning
- continue from the current browser state anyway

The application must not silently pretend that retroactive edits have changed the already-established browser state.

## 23. Playback failure and repair

When execution fails, FlowTape should stop at the affected step instead of reducing the failure to a terminal modal error.

The failed step should be visibly marked and its details shown in the properties/diagnostics pane.

Useful recovery actions include:

```text
Targetを再指定
このStepを再試行
次のStepへ
先頭から再実行
```

The availability of `次のStepへ` does not imply that skipping is safe; the UI may warn when the failed operation is likely to affect later state.

## 24. Recording-event normalization

Raw DOM/browser events must not map one-to-one to scenario steps.

Examples:

- `mousedown` + `mouseup` + `click` normally becomes one `click`
- text entry is accumulated and becomes one `input` step when the value is committed, focus leaves the field, Enter commits it, or another meaningful boundary is reached
- internal hover/highlight/picker events never become application steps

The Recorder should preserve the user's semantic action, not the browser's low-level event stream.

A normal link/button click that causes page navigation remains primarily the click step. The resulting navigation should not normally create a second redundant `open` step.

Explicit navigation actions such as direct URL opening, back, forward, refresh, or meaningful window/tab context changes are separate scenario operations.

Detailed event normalization, IME handling, double-click coalescing, and navigation snapshot rules are defined in `08-recorder-protocol.md`.

## 25. Tabs, windows, frames, and context

The first implementation should support ordinary new-tab/new-window workflows sufficiently to record and replay them.

When a user operation opens or selects another browser window/tab, the scenario/UI should represent the context change in human-readable form such as:

```text
新しいタブへ移動
元のタブへ戻る
```

Exact DSL action names may remain conventional English internally.

iframe and Shadow DOM context normally belong to target definitions. The UI should show relevant context such as `iframe内` in target details/diagnostics without requiring the user to hand-write frame selectors.

## 26. Save, external edits, and recovery

Normal scenario editing uses explicit save rather than unconditional autosave.

The application should visibly indicate unsaved changes, for example near the scenario title.

A private crash-recovery/autosave mechanism may maintain temporary recovery state, but it must not silently replace the user's scenario file.

If the scenario or registry file changes externally while open, FlowTape should detect the change and ask the user whether to reload/reconcile it. Unsaved GUI state must not be silently overwritten.

## 27. Step identity, numbering, and descriptions

Visible step numbers are presentation-only and are recalculated from current execution order.

Scenario nodes should have stable internal/persisted identities where needed for GUI state, undo/redo, diagnostics, and edit tracking. A visible number such as `05` is not the identity of the step.

Steps and structural blocks may carry an optional human-readable description/note for procedure-document purposes.

## 28. Undo/redo and block manipulation

The Scenario Editor should maintain an undo/redo stack for editing operations such as:

- add/delete/move step
- wrap/unwrap block
- edit condition/loop properties
- rename target references where applicable

Undo/redo operates on the scenario/editor model. It does not undo side effects already performed in the real browser or remote application.

Unwrapping a condition/loop preserves its contained steps in place rather than deleting them.

Drag-and-drop step reordering is allowed, including movement across block boundaries when the resulting structure is valid. Invalid structural moves must be rejected rather than producing malformed YAML.

There is no fixed semantic nesting-depth limit, but the UI may warn when deep nesting harms readability.

## 29. Risk UI

Risk metadata remains independent from playback mode.

For `risk: 破壊的`, the UI should support confirmation or execution gating before the operation. Whether confirmation is required every time should be configurable rather than permanently hard-coded.

Risk warnings should not be used as a substitute for correct target validation.

## 30. Search, YAML view, shortcuts, and theme

The scenario view should eventually support filtering/search by at least:

- target name
- action type
- optional description/note

Direct YAML access is supported, but the initial UI may place it in a separate tab/view or open the file externally. Real-time two-way editing between raw YAML and the structural GUI is not required for the first implementation.

Common keyboard shortcuts such as save, playback/pause, and single-step execution are desirable but may follow after the core button-driven workflow is stable.

The initial desktop UI may use the platform/default Qt appearance. Dedicated light/dark theming is not required for the first implementation.
