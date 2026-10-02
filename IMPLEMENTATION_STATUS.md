# FlowTape v1 実装・仕様照合

`AGENTS.md` と `docs/00`〜`14` を基準とした実装監査です。アプリの起動・シナリオのライフサイクルは `12` に従い、`03` / `06` / `08` の関連記述と README を更新しました。

## 実装範囲

| 仕様 | 実装 |
|---|---|
| `00`, `01`: 構成と意味的 YAML | capture / model / registry / resolver / Player / playback controller / UI を分離。scenario は論理名と操作順序を持ち、DOM 定義は registry に保持 |
| `02`, `07`, `10`: DSL・persisted schema | version 1 の strict validation、未知フィールド・重複 YAML key・不正型・ULID 重複・名前空間衝突・output path の拒否。UTF-8、日本語、順序、ID を保持して保存。optional null と `enabled: true` を正規化 |
| `04`, `05`, `09`: DOM 解決 | 一意な page、候補順 fallback、kind / expectation / action の判定、frame と open shadow、relative の descendant / row / dialog / form。曖昧・ゼロ件・context 不整合は明示的なエラー |
| `05`, `08`: capture engine | 短命の weak element ref と採取要素の一致検証。test 属性・安定 ID・role/name・label・name・placeholder・text・purpose 属性・relative・短い CSS を評価。スコアは診断だけに保持。最後の位置依存 CSS は fragile として明示確認 |
| `08`: Recorder | document / seq による順序と重複排除、double-click、確定 input、password value 抑止、IME commit、select、意味のある key。全 window / frame の再注入、OOP iframe の CDP binding、Python メモリへの Stage 1 配送。raw event は disk / sessionStorage に保存しない |
| `08`: picker と同期 | hover overlay、click 抑止、Escape、bind / rebind、collection 候補・件数・例・ハイライト。未確定操作は保持。protocol / queue / unsupported エラーで停止し、明示的な新しい記録境界で復旧 |
| `09`: Player | navigation、click / double_click / input / select / read / upload / key / hover / drag_drop、JavaScript dialog、check / wait、if / repeat / while / for_each、三つの mode、変数展開と secret taint、CSV / JSONL / text |
| `09`, `10`: runtime control | pause / resume / stop、1 ActionNode、選択位置の直前で停止、失敗保持、再解決して retry、明示的 skip。for_each は開始時 member を採取し毎回再同定。生成順 newest、既知 parent、popup 自動復帰。デバッグは同じ解決規則と overlay を使用 |
| `03`, `10`: Editor | ネスト範囲の wrap / unwrap、else へ移動、同じブロック内で移動、property YAML、read / append / outputs authoring、挿入記録、再生完了後に記録、undo / redo。実行済み部分の編集では選択を要求し、実行中の action や run 定義変更は再開始を要求 |
| `03`, `06`, `10`: 保存 | ページ別 rename、確定不能な参照の明示確認、外部編集の再読込 / GUI 保持 / 保留。二つのファイルの save に writer lock と durable journal、通常 I/O failure の rollback、中断検出と明示的 rollback / complete。読み込み途中の変更を拒否 |
| `06`, `09`: 診断 | `paths.logs` と `logging.level` に従う run 別 JSONL。step / category / resolution の記録、credential 値の redaction。展開済み入力値や read 値は log に渡さない。log I/O failure は表示し、成功したブラウザ操作の再試行を誘発しない |
| `06`, `11`: 環境 | 設定された絶対 WebDriver path のみ使用。アプリから自動取得しない。Linux PyInstaller build、外部 YAML / config による配布物再生、packaged Qt UI の起動確認 |

## 検証

- docs/14 GUI 再設計後の最終 pytest: **124 passed in 76.65s**。既存100件と GUI hierarchy 24件。失敗・skip なし。
- docs/13 対応後の最終 pytest: **82 passed in 73.94s**。既存64件と authoring UX 18件を含み、失敗・skip はありません。実画面で New の長いパス表示を修正した後の結果です。
- Lifecycle 実装後の最終 pytest: **64 passed in 43.91s**。既存43件と Lifecycle 21件を含み、失敗・skip はありません。
- 初期実装の pytest: **43 passed in 63.43s**。schema、semantic locator、曖昧・ゼロ件、frame / shadow、Recorder、loops、outputs、taint、UI 編集、再生カーソル、window tracking、保存 failure / 中断復旧、writer 競合、診断 log を検証。
- Edge 154.0.4258.37 と対応する user-cache WebDriver を使用。HTTP fixture は VM 内の `127.0.0.1` / `localhost` のみ。別オリジンと OOP iframe を含む。
- 画面表示ありの Edge と PySide6 で 1 Step → 続行 → click / read / append、picker の抑止と採取要素の一致を確認。
- PyInstaller 配布物から外部 scenario / registry / config を使った localhost 再生と UI 起動を確認。配布物の `doctor` でも、隔離した data fixture への Recorder 注入・picker・イベント配送・採取要素への再解決を確認（`capture_verified: true`）。
- 再現コマンド: README と `scripts/smoke_desktop.py`。画面と結果は `build/desktop-smoke/`。

## Application / Scenario Lifecycle の仕様照合

`docs/12-application-scenario-lifecycle.md` の各項目を現在の実装に照合しました。既存の Recorder / Player の DSL、capture protocol、resolver、runtime semantics は変更していません。

| 仕様の節 | 実装と確認根拠 |
|---|---|
| 1, 2, 16, 20: 独立した lifetime と neutral startup | scenario / registry が `None` のウィンドウ、開始画面、独立した browser status、`launch` から起動を試行。CLI / neutral state / 起動テストと実 Edge desktop smoke |
| 3, 4, 19: browser unavailable と command prerequisites | browser failure を状態として表示、再試行／設定、scenario のみ必要な編集・保存を許可。ブラウザ断絶を検出し browser 操作を無効化。failure / retry / loss テスト |
| 5: New Scenario | 名前と新規 package directory を指定、schema / cross-file validation、stage と排他的 directory 作成。既存 directory は拒否、I/O failure では activation しない。exclusive / rollback / menu テスト |
| 6, 8: Open と active scenario | directory または scenario.yaml、既存 `package` による YAML / schema / cross-file validation。失敗時に既存 state を保持。invalid registry / invalid cross-file / missing package テスト |
| 7: Recent Scenarios | user-private preferences、最大10件、menu / 開始画面から同じ Open、毎回検証。不存在は報告して削除を確認。reload / stale / revalidation テスト |
| 9, 10, 11: switch / close / exit | 共通の recording / picking / playback / pending / unsaved boundary。保存／破棄／キャンセル、失敗した保存は switch 中止。実行中 worker の停止完了を待ち、停止未完了なら current state を保持。modal 中の capture 再入を防止。boundary / save failure / exit / reentrancy テスト |
| 12, 18: browser retention と既存 Recorder / Editor | Close / New / Open は通常同じ Edge を保持。controller / undo / redo / binding / insertion / pending state は解除。記録開始は明示操作。headed Edge で close → new → record → save → reopen → play → open を確認 |
| 13: Application Configuration | explicit CLI path または remembered config path、Settings から外部 config を選択。browser / driver / profile / download directory の変更は restart 確認、runtime defaults は browser を保持。config / remember / restart / runtime-only テスト |
| 14, 15: File menu と CLI | New / Open / Recent / Close / Save / Exit、`flowtape ui [scenario] [--config CONFIG]`。Save As は optional のため提供しない。menu / CLI テストと配布物の help |
| 17: package-local recovery | 開こうとする package だけ検査し、既存 rollback / complete を再利用。キャンセルで application 継続。scenario file が欠落していても journal から復旧可能。recovery / cancellation / missing-file テスト |

新しい自動テストは `tests/test_lifecycle.py`。既存テストと合わせて回帰検証し、実ブラウザの再現手順は `scripts/smoke_desktop.py` に組み込みました。配布成果物やスクリーンショットは gitignore 対象です。

Lifecycle 実装後の headed desktop smoke は8項目すべて成功しました。開始画面は `build/desktop-smoke/start.png` で実際の表示と command 無効状態を確認。Linux 配布物を再ビルドし、シナリオ引数なし・不存在 WebDriver での GUI 継続、外部 package の CLI 再生、Recorder の capture / 再解決を確認しました。テスト用 preferences は一時ディレクトリへ隔離しています。

## Desktop onboarding / Credential Authoring の仕様照合

`docs/13-credential-and-authoring-ux.md` に従い、既存の Lifecycle / Recorder / Player を維持して次の UX を追加しました。

| 仕様の節 | 実装・確認根拠 |
|---|---|
| 1, 2: 初回設定 | 開始画面／設定メニューから config を作成・更新。Edge / profile / 外部 WebDriver、scenario / log / download / output / credential の保存先、timeouts / loops / playback / logging / safety を編集。schema validation、restart と activity の確認後に明示保存。失敗時は active config と元ファイルを保持。設定画面テストと実 Qt / Edge の初回起動 |
| 3, 4: New / Open UX | New は名前＋親フォルダー、作成先は read-only・コピー／scroll 可能な preview。Open の主選択は package directory。既存の作成・validation / recovery を再利用。New / menu / path preview テストと実画面 |
| 5, 6, 10, 13: 共有 credential と参照 | `CredentialStore` は config の credentials.path だけを使用。グループは page / scenario と独立。既存 DSL namespace を使用し、新しい表現や scenario-local credentials は作らない。既存 YAML の任意キーと文字列値を維持。二つの実シナリオによる共有・再利用・再生 |
| 7, 14: secret boundary | observer の password capture 規則は維持。登録値は application 側の masked fields で再入力。既存値は UI field に表示しない。browser RawCaptureEvent、scenario、run log に password がないことを実 Edge / pytest で確認。taint / output の既存テストも回帰確認 |
| 8: selection / registration | 既存グループ・キーの combo または新規グループ登録を提供。既存値を記録入力で上書きしない。新規名 collision 拒否、保存 failure / changed file / writer conflict では finalize しない。参照のみ生成。store / selector / step tests と実 Qt dialog |
| 9: username pairing | 直前の録画済み input の transient evidence、document / URL / window / frame、login naming / autocomplete / form を確認。search・異なる form / document・手編集済み Step 等は候補にしない。必ず Yes / No で確認し、No は literal を保持。pairing tests と実 Edge |
| 11: management | scenario なしでも共有グループ一覧、追加、既存キーの明示更新、warning 付き削除。フォームへ既存値を入れず、空欄は変更なし、キャンセル／終了時に入力欄を消去。Scenario references は自動変更しない。管理 UI / update cancellation / removal tests |
| 12: failure / cancellation | secret selection のキャンセル・登録 failure は pending 操作を保持し、空または literal password Step を作らない。missing group/key は既存 Player の unresolved credential error。cancel / persistence failure / missing-key tests |
| 15: boundaries | config editor、atomic environment persistence、CredentialStore、selection / registration dialogs、transient pairing、scenario reference insertion を別 module / operations に分離 |

Credential / config は single-file atomic replacement と既存 kernel writer lock による保存です。保存前の bytes を比較して外部変更を拒否し、secret を含む error payload / backup / recovery journal を作りません。Linux では tempfile と置換後のファイルが `0600`。Windows の権限は既存の OS policy に従い、Windows 実機では未検証です。

`tests/test_authoring_ux.py` と更新した lifecycle tests、および `scripts/smoke_authoring.py` で検証。headed Edge と実 Qt Settings / New / credential dialogs による 5 項目は正常終了しました。既存 desktop / frozen CLI / Recorder smoke の8項目も通過。Qt の終了時に native widget cleanup の異常が一度再現したため、main window を close 時に破棄し、smoke では deferred deletion を application cleanup 前に処理するよう修正。修正後の authoring smoke は終了コード0です。

## docs/13 レビューの3点への対応

- 初回の config / credential 保存では保存層が未作成の親ディレクトリを明示的に作成。従来の writer lock による作成にも依存せず、別々の深い保存先、作成失敗、既存ファイルの競合拒否、secret を含まないエラーを検証。
- 既存／新規 credential group の username が存在しない・空・空白のみの場合、ID の関連付け確認を表示せず、記録済み literal を保持。有効な username の場合のみ明示確認を行う。
- 認証待ちを target-rebind / navigation recovery と区別。キャンセル／登録失敗後は timer polling で対象再選択を開始せず、「認証情報の選択を再試行」で確認済み target のまま再試行。完了・破棄・scenario unload の境界で状態をクリア。通常の navigation recovery は維持。
- 最終 pytest: **100 passed in 54.20s**。回帰テストには既存／新規の username 状態、確認 Yes / No、認証キャンセル・保存失敗・再キャンセル・再試行・破棄、navigation recovery を含む。
- 更新した `scripts/smoke_authoring.py` を実 Qt / headed Edge / localhost で実行し **6項目成功、終了コード0**。未作成の独立した config / credential 親ディレクトリへの保存、実ダイアログのキャンセル、対象を再選択しない再試行、共有 credential 再利用と Player 再生、password 非漏洩を確認。結果は `build/authoring-smoke/report.json`（Git 対象外）。今回の修正後の配布物再ビルド・配布物での検証は未実施。

## Primary user flows / UI hierarchy の仕様照合

GUI の可視操作と主要フローは `docs/14-primary-user-flows-and-ui-hierarchy.md` に従います。古い操作インベントリを常設3列から主要1列へ整理し、既存機能は選択文脈・メニュー・専用ダイアログへ移しました。

| 要件 | 実装・確認根拠 |
|---|---|
| 1, 2, 14: 通常画面の5操作と状態切替 | Record / Play / Continue / Save / More。録画では終了ボタン、再生では一時停止／停止、paused では再開、failure では再試行／スキップ／停止。`test_idle_surface_five_groups_and_advanced_features_reachable` と状態テスト。実画面の `07-check-next.png` / `10-auto-recording.png` |
| 3: 再生メニュー | 通常／ゆっくり／1ステップずつ／選択位置まで。slow は既存 observation delay、single-step は1 ActionNode、selected-position は直前停止。実 Qt worker によるメニュー境界テストと既存 Player tests |
| 4: 続きを記録 | 新しい cursor で先頭から末尾まで再生し、成功時だけ同じ Edge の状態から末尾へ録画。挿入位置をクリア、失敗／停止／startup failure では移行しない。Qt worker の成功・実失敗・停止・既存 paused cursor テストと実 flow B |
| 5: 挿入 | Step 間の `＋`、先頭への追加。手動操作ダイアログ／ここから記録。実モデルの行番号・IDを変える偽Stepは作らない。nested insertion、manual-first insertion、gap click、pending insertion の保持を検証 |
| 6, 7: 対象・構造 | 選択項目の右ペインに登録状態／ブラウザで指定・再指定／診断／名前変更。範囲の右クリックに条件・それ以外・回数・条件を満たす間・各対象・解除・上下移動。既存 editor / rename validation と action 到達性テスト |
| 8: 高度な機能 | `⋯` に手動／YAML操作、read／append、outputs、未登録対象、picker／collection、undo／redo、保留認証、検証、再生設定。選択項目の YAML は明示的に展開し既存の適用を維持。全対象 action のメニュー到達性を検証 |
| 9: 初回セットアップ | Edge 検出／指定 → 外部 WebDriver 指定 → 非同期接続テスト → 明示保存。テスト用一時 profile と `about:blank` のみ使用。変更すると接続成功を無効化、成功まで保存不能。schema defaults とユーザー用 data roots を生成。完全設定は設定メニューに維持。実 guided setup / Qt thread tests |
| 10, 11, 12: 次操作の案内 | No Scenario に新規録画／既存を開く／最近の一覧。New は作成先 preview と「作成して記録へ」。空シナリオは明示的な record-ready（自動録画なし）、必要なら開始URLを開く。録画終了後は「動作確認する」を強調。実 flow A と start / New テスト |
| 13: 状態 | シナリオ名と未保存表示、常設の小さな Edge 接続表示、録画／再生／一時停止／失敗・認証待ちの説明。接続不可では setup / retry と非ブラウザ編集を維持。既存 browser failure / retention / lifecycle tests |
| 14〜17: 境界・互換性・検証 | `ui_surface.py` は可視コマンド／メニュー／Step描画、`browser_setup.py` はOS差を含む検出と guided setup、既存 `ui.py` は lifecycle / domain orchestration。schema、Recorder、DOM locator、Player / PlaybackController、credential store の実行・保存規則は変更なし。既存100件すべて回帰成功 |

最終テストは **124 passed in 76.65s**。新しい `tests/test_ui_hierarchy.py` の24件は主要5操作、動的状態、先頭からの continuation と末尾保存、失敗時の非移行、挿入位置、初回設定の成功／失敗／キャンセル／変更、No Scenario・New、対象と高度な操作の配置、再生メニューの実行境界を検証します。UI / lifecycle / authoring group は **84 passed in 3.20s**。

画面表示ありの Qt とインストール済み Edge 154.0.4258.37／明示指定の対応 driver、隔離した user profile、localhost fixture で検証しました。

- `scripts/smoke_primary_flows.py`: **A / B の2フロー成功、終了コード0**。実 setup / connection / 保存、New、ページ登録、実ボタンから open / input / click 録画、終了、動作確認、保存。実 package chooser で再読込後、1操作で先頭から末尾まで再生→同じEdgeで自動録画→追加 input / click を末尾へ保存。YAMLの手書きやRecorder/Playerのmockは使用していません。GUIダイアログへの入力はQtで自動化しています。
- `scripts/smoke_authoring.py`: **6項目成功、終了コード0**。共有credential登録・再利用・キャンセルからの再試行・Player解決・password非漏洩の回帰確認。
- `scripts/smoke_desktop.py`: **5項目成功、終了コード0**。single step / read / append / picker suppression、Close / New / Open とEdge保持の回帰確認。

画面と JSON report は `build/primary-flow-smoke/`、`build/authoring-smoke/`、`build/desktop-smoke/`（Git対象外）です。最終画面を確認し、常設操作の削減、空シナリオの録画案内、録画後の動作確認、continuation の自動録画表示を確認しました。今回の GUI 変更後の配布物再ビルド・Windows実機は未検証です。初見ユーザー本人によるユーザビリティテストは実施していません。

## 未確認事項・残課題

1. **Windows 11** の実機、Windows 用 PyInstaller build、Windows のファイル永続化・Edge / WebDriver 起動・画面配置。Linux build が Windows build の検証を代替するわけではない。
2. **ネイティブ日本語 IME** の OS 入力経路。Edge で composition / input / focusout を送る protocol fixture は検証済み。
3. **全アクセシビリティ境界事例**、各サイト固有の rich text / custom drag-drop / canvas。共有 DOM helper は v1 の基本意味を実装するが、W3C AccName の完全な実装ではない。
4. **観測開始前に作成済みの closed shadow root** と、観測・再注入より速い短命 window / frame の全ケース。通常の UI は Edge 起動直後から observer を準備する。観測できない場合の完全な capture を保証しない。
5. 配布物 UI の起動、CLI 再生、Recorder エンジンの取得と再解決は検証済み。**配布物 UI のボタン操作による Recorder 編集・保存の一連の操作全体**と Windows の企業ポリシー下での CDP 利用は未確認。
6. writer lock と journal は Linux の競合拒否・I/O failure・中断時の rollback / complete を検証済み。**Windows の locking と電源断時の永続化**、network filesystem の全ケースは未確認。

これらの確認・課題が残るため、Windows 向け v1 のリリース完了とはしていません。closed shadow / canvas / native chooser / 表現不能な window switch 等は、fragile な成功に見せず unsupported として扱います。

## 権限・外部操作

Python 依存関係は `.venv` に導入しました。sudo / su / root / OS package installation は行っていません。開発・検証中は GitHub push、PR・Issue・Release の作成・変更、VM 外への書き込みを行っていません。公開テストサイトは利用していません。

実装報告後、ユーザーから今回の変更の commit / push を明示的に指示されました。この指示を今回の GitHub push の許可として扱います。ビルド成果物、仮想環境、Python 配布パッケージ、キャッシュ、実行時データは `.gitignore` で除外します。

その後の Lifecycle 実装では VM 内のソース変更・検証だけを実施しました。検証結果の報告後、ユーザーから Lifecycle 変更の commit / push も明示的に指示されました。この追加指示を今回の push の許可として扱います。PR・Issue・Release 操作は実施していません。

今回の docs/13 対応の開発・検証中は VM 内のソース変更・検証だけを実施しました。検証結果の報告後、ユーザーから今回の commit / push と、今後も実装・テスト成功後の作業完了時に commit / push することを明示的に指示されました。この継続的な許可を `AGENTS.md` と `docs/11-development-environment.md` に記録しました。PR・Issue・Release 操作、権限昇格、OS パッケージ追加は行っていません。


## UI Testing Playground Select の記録・再生

公開サイト `https://www.uitestingplayground.com/` の Select ページで、複数選択が `multiple_select_state` として記録停止する不具合を再現しました。`select.values` を追加し、完全な選択集合（空集合を含む）の記録と再生、事前選択の解除、再実行時の冪等性に対応しました。既存 scalar `value` は保持します。選択済み option を再クリックして解除しないようにし、native select のクリックを重複する click Step として記録しません。NBSP を含む option の表示テキストは Recorder／Player 共通の DOM 正規化に従います。schema／capture／execution の仕様を同時に更新しました。

`scripts/smoke_select.py` は実 Qt GUI と headed Edge 154.0.4258.37 で、Player による指定トップページの表示→Selectリンクのクリック、3つの単一選択・2つの複数選択のRecorder保存、先頭からの2回の再生を検証しました。結果は Python／New York／Release 2.1、色 Red・Blue、果物 Banana・Date。事前選択3項目を解除し、複数選択はそれぞれ指定2項目だけです。記録された12 Stepと画面・JSON結果は `build/select-smoke/acceptance/` に保存し、最後の選択状態へまとめた7 Stepの再利用例は `examples/select/` に置きました。

最終全テストは **140 passed in 58.74s**、実サイトの最終GUIスモークも終了コード0です。ローカル Edge fixture では複数選択／解除のイベント正規化、NBSP、完全な選択集合、事前選択の解除、再実行、既存scalarの保持、確認／デバッグの非変更、ゼロ件／曖昧／重複指定／disabled／単一選択欄への誤用を検証しました。Windows実機と配布物の再ビルドは今回未確認です。sudo／su／root／OSパッケージ追加や禁止された外部書き込みは行っていません。修正・テスト・ドキュメントは継続的な許可に従いproject remoteへcommit／pushします。PR／Issue／Release操作は行いません。


## RecorderのOS入力経路の原因調査・修正

旧 `smoke_select.py` はSelenium-driven integrationであり、Recorderの実ユーザー入力の受入条件には扱いません。[試験範囲の監査・診断・再現・結果](docs/testing/recorder-native-input.md) を追加しました。

修正前のOS入力で、clickの配送はobserver/CDP/Transport/Normalizer/UI queueまで保たれているが、UIのsource/current URL判定で停止してStep化できないことを確認しました。さらにURLチェック後にDOMが遷移する競合と、checkboxのlabel/inputを別Targetへ二重登録する問題を再現しました。click時点の共有DOM意味による一意性・source PageDefinitionの証拠を使って元clickを確定し、label activationは実controlのclickに一本化しました。証拠がない/曖昧/未確認context/未確定ページ条件は保留する境界を維持しています。Normalizerでは同一snapshotの複数イベントのdocument/ref/sequenceを元イベントごとに保持します。

`FLOWTAPE_RECORDER_TRACE` のvalue-free診断でobserver admission・emit・binding・poll/merge・normalize・UI queue/commit/ignoreを追跡できます。診断のCDPコピーとメモリリングのpollコピーはtrace identityで重複排除し、入力値・URL・accessible name・snapshot・credentialsはログへ書きません。

`scripts/smoke_recorder_native.py` はX11 XTESTのみでEdgeへ入力し、Read-only CDPで座標/状態を確認します。input replay/retry/DOM修正はありません。Step追加待ちを次の入力の条件にせず、バッチ後に全件の値・順序・個数と配送identityを照合します。Playgroundのclick/input/checkbox（本体とlabel）/single select/Ctrl+multi select/navigationを各10回、すべて欠落0・trusted入力で確認しました。公開29ページのcatalogではradio入力が見当たらず、許可済みのSelenium公式web-formでradio本体/labelを10回補足検証し、別サイトとして報告しています。

結果とtraceは `build/native-recorder/verified-*/`、集約は `build/native-recorder/summary.json` です。**全149テスト成功**。Stage 1の保守的なlocator/identity、destination DOMを参照しないUI確定、未確認条件での保留、診断の値非保存・CDP/poll重複排除・診断binding欠落時のfallbackを回帰テストで確認しました。

Linuxのheaded Edge 154.0.4258.37・既存X11/XTEST/IBusを使用し、IBusのoriginal engineは終了時に復元・確認しました。`python-xlib` は `.venv` に導入（optional native-test extra）。WindowsのOS入力・日本語IME・配布物再ビルドは未検証です。sudo/su/root/OS package installationや禁止されたVM外への書き込みはありません。ソース・テスト・ドキュメントは継続許可に従いcommit/pushし、実行成果物・依存パッケージを除外します。

## 録画中のアドレスバーからのURLを開く操作

旧navigation試験は録画前に開始URLを開いていたため、録画開始後のアドレスバー入力をカバーしていませんでした。旧コミットの隔離worktreeで、OS入力によりサイトが表示されてもopenが0件になる問題を再現しました。

CDPのtop-level navigation開始・renderer要求・commitを受信順で観測し、録画中にブラウザから直接開始された確定済みdifferentDocumentの遷移をopenへ変換しました。Raw DOM bindingも同じ受信経路で取り込み、先行する操作が遅延callback threadに残ってopenの後へ回る競合を防ぎます。元の要求URLを保持し、リンク・フォーム・script・iframe・録画外・失敗/キャンセル・未知分類は直接URL入力と推測しません。Ctrl/Meta+LとAlt+Dはpending入力を確定し、余分なDOM key Stepを残しません。FlowTapeのURLコマンドは前の記録を確定し、明示openの二重記録を抑止します。遷移で消滅したcross-origin frameへの再設定失敗も修正し、捕捉済みイベントは保持しています。

最終native試験は `build/native-recorder/address-ordered-final/` でアドレスバーから10回開いてopen 10件（余分なkey Stepなし）、保存後の先頭再生成功、欠落0・リトライ0。`address-link-ordered-final/` ではリンク往復10回でclick 10件・重複open 0件です。録画終了後のrecorder_error/pending/queueも検査し、終了コード0とIBusの元engine復元を確認しました。[原因と試験範囲](docs/testing/recorder-native-input.md) に証拠を追記しました。

最終回帰テストは **161 passed in 97.54s**。LinuxのEdge 154.0.4258.37、公開Playgroundとlocalhost fixture、Qtを使用しました。Windowsのネイティブ入力・日本語IME・配布物再ビルドは未検証です。権限昇格・OSパッケージ追加・禁止された外部書き込みは行っていません。継続的な許可に従ってソース・テスト・ドキュメントをcommit/pushし、実行成果物は除外します。

## タブ・ブラウザ終了後の先頭再生

ユーザーが作成した先頭open付きの9 Stepシナリオを、元ファイルを編集せず試験用コピーで検証しました。旧dcbb48cでは、blankタブだけを残して元ハンドルを閉じた際にRecorderの古いwindow trackingがobserver再設定を阻止し、ブラウザ終了検出後はPlayボタンとdriver必須の開始guardで起動できないことを再現しました。

新規再生の境界で有効なcurrent handleまたは一意な生存タブを初期状態とし、閉じたtop-level transportを除いてRecorder境界を揃えます。scenario/configがあるidle状態では再生/続きを記録を使用でき、終了した古いsessionを解放して設定済みEdgeを起動します。起動時に続きを記録する意図を消さないようにしました。複数tabの曖昧性、runtimeの未知親への復帰、未確定captureは引き続き拒否します。状態依存のシナリオにopenを追加しません。

`scripts/smoke_playback_recovery.py` は実Qt再生ボタン・PlaybackWorker・Playerを使用します。既存about:blank、元tabを閉じて新しいblankだけを残す場合、ブラウザ終了のpoll検出前/後の4状態で、すべて9/9 Step完了・最後のselect値/集合一致・元scenario/elementsとコピーのバイト一致を確認しました。結果は `build/playback-recovery/summary.json` と各report、[再現・修正・試験範囲](docs/testing/playback-recovery.md) にあります。

最終全回帰テストは **168 passed in 80.00s**。Linux Edge 154.0.4258.37、公開Playgroundとlocalhost fixture、Qtで検証しました。Windows実機・配布物再ビルドは未検証です。権限昇格・OS package追加・禁止された外部書き込みはありません。ソース・テスト・ドキュメントを継続許可に従ってcommit/pushし、ユーザーのscenario、試験profile、preferences、ログ等の実行時データは含めません。

## Edge終了後の新規シナリオで記録開始

記録開始のdriver必須guardと、起動中のbrowserを前提にしたボタン有効条件を修正しました。設定済みなら主記録ボタン・空シナリオの記録開始・URLを開く操作からEdgeを起動できます。sessionの生存確認を共通の起動処理へ移し、poll検知前の終了にも対応します。未確定記録の起動拒否、起動失敗時の録画停止・再試行、新規作成だけでは録画やopenを追加しない境界を維持しています。

実Qt/Edge試験で、元シナリオのコピーを9 Step再生→Edge終了→新規シナリオ作成→記録開始→アドレスバーへのX11 XTEST入力でopen 1件を記録→保存→1 Step再生完了を、終了のpoll検知前/後で確認しました。証拠は `build/playback-recovery/new-record-before-poll/` と `new-record-polled/`、試験手順は [playback-recovery.md](docs/testing/playback-recovery.md) にあります。元scenario/elementsは変更せずバイト一致を確認し、IBusも元engineへ復元しました。Linux Edgeで検証し、Windows実機・配布物は未検証です。実行成果物はGitへ含めません。

全回帰テストは **174 passed in 120.53s**。権限昇格・OSパッケージ追加・禁止された外部書き込みはありません。継続許可に従いソース・テスト・ドキュメントをcommit/pushします。
