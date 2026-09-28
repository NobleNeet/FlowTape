# FlowTape v1 実装・仕様照合

`AGENTS.md` と `docs/00`〜`13` を基準とした実装監査です。アプリの起動・シナリオのライフサイクルは `12` に従い、`03` / `06` / `08` の関連記述と README を更新しました。

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
