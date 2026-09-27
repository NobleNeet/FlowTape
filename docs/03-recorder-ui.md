# FlowTape Recorder and Scenario Editor UI

Status: initial specification before implementation

## 1. Overall UI concept

The expected desktop implementation uses PySide6 for the FlowTape application UI and Selenium to control a separate browser window.

The conceptual UI has two physical windows:

1. FlowTape application window
2. Selenium-controlled browser window

Inside the FlowTape application, the workflow is organized logically around three areas:

- recording / step list
- structural editing
- target/element information

Exact widget placement may evolve, but these responsibilities should remain separated.

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
03  Input     パスワード = ${PASSWORD}
04  Click     ログイン
05  Click     次へ
06  Click     次へ
07  Click     完了
```

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

- Recorder: captures what happened
- Scenario Editor: describes when/how often it happens

This separation is intentional and should remain even if both features share one application window.

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
- target rename/rebind
- missing-target binding
- simple range wrapping for conditions/loops

Advanced visual editing can follow after these core semantics are stable.
