# FlowTape Primary User Flows and UI Hierarchy

Status: specification

This document defines the primary desktop user flows, visible command hierarchy, and progressive-disclosure rules for the FlowTape GUI.

It complements the functional interaction model in `03-recorder-ui.md`, the application/scenario/browser lifetime rules in `12-application-scenario-lifecycle.md`, and the configuration/credential authoring rules in `13-credential-and-authoring-ux.md`.

For subjects explicitly covered here, this document is authoritative for **which actions are visible, where they are placed, how representative workflows are entered, and how many concepts the ordinary user must understand at once**.

This document does not change persisted YAML/schema semantics, Recorder protocol semantics, DOM resolution semantics, or Player execution semantics.

When an older document shows a large representative toolbar or several equivalent commands side by side, treat that as a list of supported capabilities, not as a requirement to expose every capability simultaneously. The UI hierarchy defined here takes precedence.

## 1. UX objective

A normal user must be able to perform the two representative workflows below without consulting external documentation or asking another person/tool how to operate FlowTape:

1. first launch -> configure Edge/WebDriver -> create a linear scenario -> record -> play it back
2. open a saved scenario -> replay it to its end -> automatically continue recording from that live browser state

If either workflow requires the user to understand internal concepts such as `bind`, `rebind`, collection picking, raw playback-controller states, or YAML structure before reaching the intended result, the GUI is considered too exposed.

The ordinary GUI should be organized around **user intent**, not around a flat list of internal functions.

## 2. Global UI hierarchy principles

### 2.1 Primary commands

When a scenario is open and the application is idle, the normal top-level command surface should expose approximately these actions:

```text
[● 記録]   [▶ 再生 ▼]   [▶| 続きを記録]          [保存]   [⋯]
```

The exact iconography may vary, but the conceptual primary actions are:

- record a normal browser operation
- play the scenario
- replay the scenario to its current end and continue recording
- save
- open secondary/advanced commands

These commands should visually dominate the normal scenario screen.

### 2.2 Do not expose the implementation inventory as a toolbar

The ordinary top-level toolbar must not present every supported editing/runtime operation at the same visual level.

Commands such as the following are required capabilities but are not ordinary always-visible primary commands:

- picker
- collection picker
- bind / rebind
- bind missing targets
- target diagnostics
- `if` / `else` / `repeat` / `while` / `for_each`
- read / append / output authoring
- move up / move down
- unwrap
- target rename
- retry / skip playback
- explicit insertion-record command
- raw playback-controller commands that are irrelevant in the current state

These belong in one of:

- selected-item properties
- contextual menus
- an insertion affordance
- a playback-state-specific surface
- a secondary `⋯` menu
- an advanced dialog

### 2.3 Progressive disclosure

FlowTape should reveal controls only when the user has the context needed to understand them.

Examples:

- target rebinding belongs near the selected target
- structural wrapping belongs near the selected step range
- insertion recording belongs at the insertion position
- retry/skip belongs in playback failure state
- pause/stop belongs in playback state
- credential selection belongs when a secret input requires resolution

Disabled controls may still be used where useful for discoverability, but the default should not be a permanently visible wall of disabled commands.

### 2.4 State-dependent command replacement

Related commands should reuse the same visual position when their meaning changes with state.

Preferred model:

```text
Idle recording state:       [● 記録]
Recording:                  [■ 記録を終了]

Idle playback state:        [▶ 再生 ▼]
Playing:                    [⏸ 一時停止] [■ 停止]
Paused:                     [▶ 再開]     [■ 停止]
Playback failure:           [↻ 再試行]   [スキップ] [■ 停止]
```

The user should not see separate permanent buttons for all of these states simultaneously.

## 3. Main scenario screen

The normal scenario-open screen retains the two-pane model from `03-recorder-ui.md`:

- left: scenario/structure
- right: selected-item properties/details

Recommended conceptual layout:

```text
+------------------------------------------------------------------+
| FlowTape   シナリオ: 社内申請                     Browser ● 接続済み |
+------------------------------------------------------------------+
| [● 記録] [▶ 再生 ▼] [▶| 続きを記録]       [保存] [⋯]             |
+--------------------------------+---------------------------------+
| シナリオ                       | 選択項目                         |
|                                |                                 |
| 01  ページを開く               | Click: ログイン                 |
| 02  IDを入力                   | Target: ログイン                |
| 03  パスワードを入力           |                                 |
| 04  ログインをクリック         | [ブラウザで再指定]              |
|                                | [診断を見る]                    |
+--------------------------------+---------------------------------+
| 準備完了                                                         |
+------------------------------------------------------------------+
```

Browser readiness should remain persistently understandable, but it need not consume a large command strip when healthy.

## 4. Representative workflow A: first launch to first playback

### 4.1 First launch when browser configuration is unavailable

If a usable browser configuration does not yet exist, the start view should prioritize browser setup before scenario authoring.

Preferred conceptual start state:

```text
FlowTape

ブラウザを使えるように設定します

Microsoft Edge     ● 検出済み
WebDriver           未設定

[セットアップを開始]

すでに設定済みの場合
[既存 config.yaml を使用]
```

The user should not initially be confronted with all application settings merely because one required WebDriver path is missing.

### 4.2 First-use browser setup

First-use setup should use progressive disclosure.

Step 1: Edge

```text
ブラウザ設定  1 / 2

Microsoft Edge

Edge:
● 自動検出
○ 実行ファイルを指定

検出結果:
Microsoft Edge 154.x
/path/to/microsoft-edge

[次へ]
```

Step 2: WebDriver

```text
ブラウザ設定  2 / 2

Microsoft Edge WebDriver

WebDriver:
[ /path/to/msedgedriver ] [参照]

Edge        154.x
WebDriver   154.x

[接続テスト]
```

After success:

```text
✓ Edgeを起動できました

[設定を保存して開始]
```

FlowTape must continue to obey the external-driver rule: it must not silently download or provision WebDriver.

### 4.3 Defaults versus advanced settings

The first-use path should ask only for settings needed to reach a usable browser and a reasonable default authoring environment.

Settings such as the following should normally receive defaults and remain editable later in application settings:

- logs directory
- downloads directory
- outputs directory
- credentials path
- timeout defaults
- loop limits
- playback observation delay
- logging level
- destructive-operation confirmation policy

The complete settings editor required by `13-credential-and-authoring-ux.md` remains available. The distinction is that **the complete editor is not the preferred first-run onboarding surface**.

### 4.4 Start view after browser setup

Once browser setup is usable, the start view should be phrased in terms of the user's task:

```text
FlowTape

何をしますか？

[＋ 新しい操作を記録する]

[既存シナリオを開く]

最近使ったシナリオ
- ...
```

`＋ 新しい操作を記録する` is the preferred primary label for the ordinary New Scenario entry point. Internally it still creates a scenario package according to `12-application-scenario-lifecycle.md`.

Menus may continue to use the more formal `新規シナリオ` wording.

### 4.5 New scenario dialog

The normal creation dialog asks only for the information required by the scenario lifecycle specification:

```text
新しい操作を記録

名前
[ Google検索テスト ]

保存先
[ ~/FlowTape/scenarios ] [変更]

作成場所:
~/FlowTape/scenarios/Google検索テスト/

[キャンセル] [作成して記録へ]
```

The package path must remain visible before creation.

The preferred primary button is `作成して記録へ`, because the ordinary user goal is to begin recording rather than merely to create empty files.

Creating the package still does not itself fabricate browser actions. The resulting screen enters an explicit ready-to-record state.

### 4.6 Empty scenario state

A newly created empty scenario should make the next action self-evident:

```text
Google検索テスト

まだ操作はありません。

Edgeを普段どおり操作してください。
クリックや文字入力をFlowTapeが記録します。

[● 記録を開始]
```

Secondary structural-authoring commands should not dominate an empty scenario.

### 4.7 Recording

After recording begins, the primary recording command changes to `■ 記録を終了`.

The scenario list updates as semantic operations are accepted:

```text
● 記録中

01  https://www.google.com を開く
02  検索欄に「FlowTape」と入力
03  Google検索をクリック

[■ 記録を終了]
```

The FlowTape window must show an unmistakable recording state. A non-interfering browser overlay/status indication may additionally show that recording is active.

While recording, the interface should minimize unrelated editing controls so that the user can concentrate on the browser demonstration.

### 4.8 End of first recording

After recording stops, the UI should immediately expose the natural next action:

```text
3個の操作を記録しました。

[▶ 動作確認する]
```

The ordinary path should not require the user to understand that they must separately select a playback controller mode.

### 4.9 Playback choice

The main `▶ 再生` control may have a drop-down containing:

```text
▶ 再生
  ├ 通常
  ├ ゆっくり
  ├ 1ステップずつ
  └ 選択位置まで
```

`通常` is the default.

Slow playback and single-step playback remain semantically distinct as defined in `03-recorder-ui.md` and `09-runtime-semantics.md`.

The old concept of displaying separate permanent buttons for `最初から`, `再開`, `1ステップ`, `選択位置まで`, `一時停止`, `停止`, `再試行`, and `スキップ` is not the preferred normal layout. These remain supported actions surfaced according to current state and context.

## 5. Representative workflow B: open existing scenario and continue recording from its end

### 5.1 Open existing scenario

From the start view the user chooses:

```text
[既存シナリオを開く]
```

Package selection and validation/recovery follow `12-application-scenario-lifecycle.md` and `13-credential-and-authoring-ux.md`.

After activation, the scenario appears in the normal scenario screen.

### 5.2 Continue-record command is first-class

The normal top-level screen exposes:

```text
[● 記録]   [▶ 再生 ▼]   [▶| 続きを記録]
```

`続きを記録` means exactly:

```text
play the current scenario from its normal beginning
    -> reach the current scenario end successfully
    -> keep the resulting controlled-browser state
    -> automatically switch into recording
    -> append subsequently recorded operations to the scenario end
```

This is one user command, not a sequence the user must manually coordinate.

A tooltip/help text may say:

```text
シナリオを末尾まで再生し、その状態から記録を開始します。
```

The previous longer wording such as `最後まで再生して記録` describes the implementation accurately but should not be the primary concise command label.

### 5.3 Playback phase of continue-record

During the playback portion, ordinary playback-state controls are shown:

```text
▶ 再生中  4 / 6

04  新しいチケットをクリック
05  件名を入力
06  保存

[⏸ 一時停止] [■ 停止]
```

The user does not need to press Record at the end.

### 5.4 Automatic transition to recording

When playback reaches the scenario end successfully, the application automatically changes state:

```text
✓ 末尾まで再生しました

● 続きを記録中

Edgeで続きを操作してください。
```

The transition must preserve the live browser state established by playback.

The scenario list then appends the newly demonstrated steps after the existing final step.

### 5.5 Stop continuation recording

The same recording-state action ends the continuation:

```text
[■ 記録を終了]
```

The appended operations remain ordinary scenario steps and follow the same validation, credential-resolution, target-capture, undo/redo, and save rules as other recorded steps.

## 6. Insertion recording is contextual, not a permanent top-level button

FlowTape still supports recording into an arbitrary insertion point as required by `03-recorder-ui.md`.

The preferred interaction is an insertion affordance between steps:

```text
04  Click ログイン
        ────── ＋ ──────
05  Click メニュー
```

Activating `＋` exposes contextual choices such as:

```text
ここに追加

＋ 手動で操作を追加
● ここから記録
```

The user should not need to interpret a permanent toolbar command named `選択後に記録`.

The insertion position remains explicit and later existing steps remain intact.

## 7. Structural editing placement

Structural editing remains supported exactly as required by the scenario model, but is contextual to the selected range.

For a selected contiguous range, a contextual menu or nearby action surface may expose:

```text
編集
├ 上へ移動
├ 下へ移動
├ 削除
├────────────────
├ 条件付きにする >
│   ├ ～の場合
│   └ それ以外
├ 繰り返しにする >
│   ├ 指定回数
│   ├ 条件を満たす間
│   └ 各対象について
├────────────────
├ この位置から記録
└ 詳細設定
```

Exact menu structure may evolve, but `if`, `else`, `repeat`, `while`, and `for_each` should not all require independent always-visible top-level buttons.

Natural-language wording remains preferred over DSL terminology for ordinary users.

## 8. Target operations placement

Target operations belong primarily in the selected-item properties pane.

Example:

```text
対象
────────────────
ログイン ボタン

状態: ✓ 正常

[ブラウザで再指定]
[診断を見る]
```

This surface may additionally expose rename and advanced locator information.

Ordinary users should not need to distinguish `bind` from `rebind` before acting. The UI may present one context-sensitive action such as `ブラウザで指定` / `ブラウザで再指定` while preserving the different internal semantics.

A scenario-wide unresolved-target workflow remains available through a secondary/advanced command.

## 9. Manual step/data/output authoring placement

Manual step creation should begin from one conceptual `＋ 操作を追加` entry point rather than one permanent toolbar button per action type.

A representative hierarchy is:

```text
＋ 操作を追加

ブラウザ操作
├ Click
├ Input
├ Select
├ ...

データ取得
├ 値を読み取る
└ 出力へ追加

制御
├ 条件
└ 繰り返し
```

Read/append/output capabilities remain fully available, but advanced data-authoring terminology should not compete visually with Record and Play in the normal screen.

## 10. Secondary menu

A `⋯` or equivalent secondary menu may collect commands that are valid but not continuously primary.

Representative organization:

```text
シナリオ
├ 検証
├ 未登録Targetを確認
├ 出力設定
└ YAMLを開く

編集
├ 元に戻す
└ やり直す

ブラウザ
├ URLを開く
├ 再起動
└ 診断

高度な操作
├ Element Picker
├ Collection Picker
└ ...
```

Common keyboard shortcuts remain allowed and should not force the corresponding command to occupy permanent visual space.

## 11. Playback failure state

Playback failure is a distinct contextual state.

The failed step is selected/marked and the relevant properties/diagnostics are displayed.

Only then should recovery actions become prominent, for example:

```text
[Targetを再指定] [↻ このStepを再試行] [次のStepへ] [■ 停止]
```

`次のStepへ` may require a warning according to the existing playback semantics.

These failure actions are not ordinary idle-state toolbar commands.

## 12. No-scenario state

The `No Scenario` state remains defined by `12-application-scenario-lifecycle.md`.

Its ordinary visual priority is:

1. resolve required browser setup if browser configuration is missing
2. start a new recording/scenario
3. open an existing scenario
4. recent scenarios
5. secondary settings/management commands

Browser failure after a previously usable configuration should continue to offer recovery actions such as Retry and Settings without preventing non-browser scenario inspection.

## 13. Settings hierarchy

FlowTape has two distinct settings experiences:

### 13.1 Guided first-use setup

Purpose: reach a working Edge/WebDriver environment with the minimum required decisions.

This is the preferred first-launch path described in section 4.

### 13.2 Complete application settings

Purpose: expose all application-level configuration required by `06-runtime-platform.md`, `12-application-scenario-lifecycle.md`, and `13-credential-and-authoring-ux.md`.

This includes paths, timeouts, loop limits, logging, safety, profile/window preferences, credentials path, and other supported runtime defaults.

The existence of the complete settings editor does not imply that every field belongs in first-run onboarding.

## 14. Command count and visual-priority rule

The primary idle scenario toolbar should target roughly **five visible command groups or fewer**, excluding passive status indicators.

The preferred baseline is:

```text
Record | Play | Continue Recording | Save | More
```

A design that permanently places dozens of individual function buttons in one toolbar violates this specification even if every button corresponds to a valid FlowTape capability.

This is a hierarchy rule, not a hard prohibition against temporary/contextual controls.

## 15. Terminology rules

Prefer task-oriented labels for ordinary users:

```text
新しい操作を記録する
記録を開始
記録を終了
再生
続きを記録
ブラウザで再指定
値を読み取る
出力へ追加
```

Internal/DSL terms may appear secondarily where useful:

```text
if
while
for_each
bind
rebind
collection
```

The GUI must not require prior knowledge of those internal terms for the two representative workflows in this document.

## 16. Acceptance criteria for the GUI redesign

The redesign is acceptable only if all of the following are true:

- first launch with no config leads directly to a comprehensible Edge/WebDriver setup path
- full advanced configuration is not required before the user can understand what to do next
- after setup, a user can identify how to create and record a new scenario from the start screen without documentation
- after creating an empty scenario, the next action (`記録を開始`) is visually obvious
- recording visibly changes the command surface to a recording state
- after stopping a first recording, playback is the obvious next action
- a saved scenario exposes one clear `続きを記録` command that handles replay-to-end and automatic recording transition
- insertion recording is discoverable at a step boundary without requiring a permanent top-level button
- target repair is discoverable from the selected target/step
- structural editing is discoverable from the selected range
- playback failure exposes retry/repair actions only when relevant
- the ordinary idle toolbar does not present the internal feature inventory as dozens of equal buttons
- all advanced capabilities from the prior specifications remain reachable through contextual or secondary surfaces

## 17. Relationship to existing specifications

This document intentionally changes the interpretation of several older UI examples:

- `03-recorder-ui.md` section 21 lists many playback controls. They remain required capabilities, but they should be surfaced contextually/drop-down/state-dependently rather than as a permanent row of buttons.
- `03-recorder-ui.md` section 20 remains authoritative for insertion-record semantics; this document defines the preferred `＋` interaction for discovering that capability.
- `12-application-scenario-lifecycle.md` remains authoritative for application/scenario/browser lifetime and safe switching. Its start-view sketches are conceptual; this document defines the preferred visual priority and labels.
- `13-credential-and-authoring-ux.md` remains authoritative for which application settings and credential operations must be possible. This document makes the first-use setup a smaller guided subset and leaves the complete settings editor available separately.

No change in this document permits FlowTape to weaken schema validation, browser safety, credential secrecy, conservative target resolution, save/recovery boundaries, or explicit WebDriver ownership rules.

## 18. Concrete v1 desktop choices

The following choices apply the hierarchy above without introducing persisted fields or changing runtime semantics:

- Guided setup uses two pages (Edge, then an explicitly supplied WebDriver). Its connection test runs off the GUI thread, opens `about:blank` in an isolated temporary profile, reports the browser/driver versions, and closes that test browser. Saving is enabled only after a successful test of the current inputs. The normal controlled browser starts after explicit config persistence. Advanced settings and an existing config remain available separately.
- New setup saves `config.yaml` beside private application preferences. Scenario/log/download/output roots default to `Documents/FlowTape/` (home directory fallback when Documents is unavailable); shared credentials default beside the config. Other defaults come from the existing config schema. Existing configurations retain their paths and settings. The dedicated profile can be changed in complete settings; the probe never opens the configured persistent profile concurrently.
- Creating a package enters an explicit record-ready state and does not automatically capture actions. An optional `開始するページを開く` action uses the existing application URL command to add an ordinary `open` step. Users can also begin from the current Edge state, as permitted by the runtime/platform specification.
- First-page registration presents a readable page name and URL matching rule with an explicit registration button. General page conditions remain available through optional YAML details. Page confirmation and conservative uniqueness checks remain unchanged.
- Step-boundary `＋` affordances and the first-position insertion control represent insertion positions without creating fake scenario nodes or changing step identities. They offer a basic manual-operation dialog or insertion recording. Structural editing lives in the step/range context menu.
- The right pane presents the selected operation, logical target names, registration status, browser specification/repair, and diagnostics. Registration status does not claim the target currently resolves; live diagnosis uses the existing resolver. YAML properties are revealed on request and retain their existing validation/apply workflow.
- The main playback button retains the chosen pacing while resuming. The drop-down selects normal, configured slow observation (one second when the configured delay is zero), one executable action at a time, or pause before the selected node. Execution mode and exact observation delay remain in the dedicated playback settings dialog.
- `続きを記録` starts a fresh playback cursor from the beginning with no single-step budget or selected-position stop. It clears any insertion position and automatically begins appending recording only after successful completion. Failure, stop, or startup failure cancels the automatic recording transition. Edge remains alive.
