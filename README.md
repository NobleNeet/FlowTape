# FlowTape

FlowTape は、ページ上の操作を意味のある YAML Step として扱う Edge/Selenium ツールです。`scenario.yaml` は操作の順序と論理 target 名を保持し、`elements.yaml` はページごとの DOM 解決を保持します。

## 開発環境

Python 3.11 以降、Microsoft Edge、Edge と互換の `msedgedriver` が必要です。依存関係は一般ユーザーの仮想環境へインストールできます。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[ui,test]'
.venv/bin/python -m pytest -q
```

`config.yaml` の `driver.path` に WebDriver の絶対パスを指定してください。FlowTape 自体は WebDriver を自動取得しません。シナリオと設定は実行ファイルの外部に置きます。

```yaml
version: 1
driver:
  path: /absolute/path/to/msedgedriver
```

## 使い方

GUI は既存の YAML なしで起動できます。初回は「セットアップを開始」から Edge と外部 WebDriver を指定し、接続テスト後に設定を保存します。設定後は「＋ 新しい操作を記録する」または「既存シナリオを開く」から始めます。

```bash
flowtape validate /path/to/scenario-directory
flowtape run /path/to/scenario-directory --config /path/to/config.yaml
flowtape ui
flowtape ui --config /path/to/config.yaml
flowtape ui /path/to/scenario-directory --config /path/to/config.yaml
flowtape doctor --config /path/to/config.yaml --headless
```

CLI 再生は `scenario.yaml` の `mode` に従います。画面の「⋯ → 再生・実行の詳細設定」では `実行` / `確認` / `デバッグ` と再生速度を別々に選べます。`risk: 破壊的` の実行には、設定された確認ポリシーを適用します。

`doctor` は外部サイトを使わず、設定された Edge / WebDriver と Recorder の注入・選択・要素一致を確認します。

### 2つの基本フロー

- **新しく記録する:** 「＋ 新しい操作を記録する」→ 名前・保存先を確認して「作成して記録へ」→ 必要なら開始するページを開く → 「● 記録を開始」→ Edgeを操作 → 「■ 記録を終了」→ 「▶ 動作確認する」→ 保存。
- **続きを記録する:** 保存済みシナリオを開く → 「▶| 続きを記録」→ 先頭から末尾まで自動再生 → 同じEdgeの状態から自動で録画開始 → Edgeで追加操作 → 「■ 記録を終了」→ 保存。失敗や停止では自動録画へ移りません。

通常画面の主要操作は記録・再生・続きを記録・保存・「⋯」です。「▶ 再生 ▼」から通常／ゆっくり／1ステップずつ／選択位置までを選べます。再生中は一時停止・停止、停止位置では再開、失敗時は再試行・スキップ・停止へ切り替わります。

### アプリ起動とシナリオの切り替え

- 起動時に Edge の起動を試みます。設定がない場合やブラウザ起動に失敗した場合も、シナリオ作成・読込・編集・保存ができます。初回の小さなセットアップでは Edge／外部 WebDriver を確認し、他の保存先・待機時間などには既定値を生成します。「設定 → アプリ設定を作成・編集」で後からすべての設定を編集できます。「設定」メニューから既存 config の選択もできます。WebDriver の自動取得は行いません。
- ファイルメニューから新規・開く・閉じる・保存・終了を操作できます。新規作成では名前と親フォルダーを指定し、作成先パッケージを事前に確認します。既存のフォルダーを上書き・併合しません。開く操作の主対象はパッケージフォルダーです（CLI／最近の項目では scenario.yaml も扱えます）。
- 切り替え・閉じる・終了時には記録／再生を停止するか確認し、未確定記録の破棄、未保存変更の保存／破棄／キャンセルを明示的に選択します。保存が失敗した場合は切り替えません。
- 「シナリオを閉じる」はブラウザを維持して開始画面へ戻ります。新規／別パッケージを開いてもブラウザ状態は継続し、再生進行・undo・記録の挿入位置などは引き継ぎません。
- 最近のシナリオ（最大10件）と設定ファイルのパスは Qt のユーザー用 AppConfigLocation 配下の `FlowTape/preferences.json` に保存します。シナリオ YAML や credential 値はここへ保存しません。最近の項目も開くたびに検証し、存在しない項目は確認して削除できます。
- ブラウザ／driver／profile／download directory の設定変更は、明示的な再起動確認が必要です。ログ・待機など他の runtime defaults の変更ではブラウザを維持します。

### Recorder / Editor

- Edge のクリック、入力、select、キーボード操作を記録します。パスワード値は取得せず、既存 credential グループ／キーの選択または新規グループの明示登録で参照を作ります。新規登録では GUI でパスワードを再入力します。
- 右ペインの「ブラウザで指定／再指定」または「⋯ → 高度な操作 → ブラウザから対象を登録」では対象操作を抑止し、同じ採取要素に一意に戻れる locator を検証します。既存 target が同じ要素を表す場合は再利用します。
- 「⋯ → 高度な操作 → 繰り返し対象を登録」は代表行から集合候補を作り、件数・例・ハイライトを確認して登録します。
- Step／範囲を右クリックして「条件付きにする」「繰り返しにする」を選べます。それ以外への移動、解除、上下移動も同じメニューにあります。元に戻す／やり直すは「⋯ → 編集」または Ctrl+Z / Ctrl+Shift+Z です。
- Step間の「＋」から「手動で操作を追加」または「ここから記録」を選び、後続Stepを残して挿入できます。「⋯ → 操作を追加」に値を読み取る／出力へ追加／YAMLで追加、「⋯ → シナリオ」に出力設定があります。
- 対象の名前変更は右ペインの「対象の詳細」にあります。ページ別に参照を解析し、ページを確定できない参照は明示的に確認します。
- 保存は明示操作です。外部編集を検出したら再読込・GUI 保持・保留を選べます。保存途中の I/O エラーでは両ファイルを元に戻します。

保存途中のプロセス終了は package 内の `.flowtape-save.json` で検出します。パッケージを開くときの選択、または `flowtape recover /path/to/package --choice rollback` / `--choice complete` で、保存前へ戻すか保存を完了するか明示的に決めます。未復旧の package は実行しません。

同じ package の同時保存は writer lock で拒否します。run の診断は `paths.logs` 配下へ `logging.level` に従って保存します。展開済みの入力値・取得値は記録せず、credential 値は redaction します。

### 共有認証情報

「設定 → 共有認証情報を管理」はシナリオなしでも利用できます。グループ名の一覧、追加、明示的な更新、確認付き削除を提供します。既存値をフォームへ表示せず、入力欄は masked 表示です。更新時の空欄は変更なしとして扱います。任意の既存キーも更新できます。

認証情報はアプリ設定の `credentials.path` にだけ保存し、複数シナリオで再利用します。記録中に違う値を入力しても、選んだ既存グループを上書きしません。関連が確認できる直前の ID 入力についてのみ、同じグループの username 参照へ変更するか確認します。キャンセルや保存失敗では password 操作を未確定のまま保持します。

config／credential 保存は外部変更・writer 競合を検出し、一時ファイルからの置換で行います。認証情報の一時ファイルと保存ファイルは Linux では user-only permission です。v1 の認証情報はディスク上では平文なので、保存先のアクセス権・運用ポリシーで保護してください。削除・更新でシナリオの参照を黙って書き換えません。

### Player

1 Step、選択位置まで、一時停止・再開、停止、再試行、明示的なスキップに対応します。失敗した Step は保持し、再試行時は DOM を再解決します。実行済み部分の編集は再開始または現在の状態で続行を選択します。変数・outputs・モードの変更には再開始が必要です。

記録中に対象 DOM が消えた場合、操作は未確定のまま保持します。操作前ページを再表示して対象を再選択し、元の操作に紐付けます。同期エラーが起きた区間は黙ってつながず、新しい記録境界を明示的に開始します。

## ビルドとデスクトップ確認

```bash
.venv/bin/python -m pip install -e '.[ui,test,build]'
.venv/bin/pyinstaller FlowTape.spec
.venv/bin/python scripts/smoke_desktop.py --driver /absolute/path/to/msedgedriver --executable dist/FlowTape/FlowTape
.venv/bin/python scripts/smoke_authoring.py --driver /absolute/path/to/msedgedriver
.venv/bin/python scripts/smoke_primary_flows.py --driver /absolute/path/to/msedgedriver
```

Linux 配布物は `dist/FlowTape/FlowTape` です。Windows 用の配布物は Windows 上で同じ spec からビルドしてください。ユーザーの YAML・設定・WebDriver は配布物の外部に置きます。

スモーク確認は画面表示ありの Edge とローカル HTTP fixture を使い、`build/desktop-smoke/` に画面と結果を保存します。仕様照合結果と未確認事項は [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) を参照してください。

`smoke_authoring.py` は実際の Qt 設定／New／認証選択ダイアログと headed Edge で、未作成の保存先への初回設定・登録、認証選択のキャンセルと対象を再選択しない再試行、別シナリオでの再利用、再生、安全な終了を確認します。認証待ちは「⋯ → 高度な操作 → 認証情報の選択を再試行」で再開できます。結果と設定／New 画面は `build/authoring-smoke/` に保存します。

`smoke_primary_flows.py` は実際の Qt ボタン・セットアップ・作成・パッケージ選択・ページ登録と headed Edge / localhost を使い、上記2フローを最初から保存まで確認します。画面と結果は `build/primary-flow-smoke/` に保存します。

### Select の実サイトテスト

[examples/select](examples/select/scenario.yaml) は UI Testing Playground のトップページで「Select」を開き、Python／New York／Release 2.1、色 Red・Blue、果物 Banana・Date を選択します。`select.value` は単一項目の表示テキスト、`select.values` は複数選択欄の完全な選択集合です。事前選択された果物も解除し、指定した2項目だけを残します。

```bash
flowtape run examples/select --config /path/to/config.yaml
PYTHONPATH=. .venv/bin/python scripts/smoke_select.py --driver /absolute/path/to/msedgedriver
```

スモーク確認は画面表示ありの Qt／Edge で選択操作を記録・保存し、トップページから2回再生して5つの選択結果を検証します。実行用設定・記録済みパッケージ・画面・結果は `build/select-smoke/acceptance/` に保存します。公開サイトのテストは通常の少数回の操作に限ります。

### RecorderのOS入力による検証

`scripts/smoke_select.py` はSelenium経由の選択操作の統合確認です。実ユーザー入力の受入条件には使いません。Linux X11のマウス／キーボード入力からStep追加までの確認は次で行います。

```bash
.venv/bin/python -m pip install -e '.[ui,test,native-test]'
PYTHONPATH=. .venv/bin/python scripts/smoke_recorder_native.py \
  --driver /absolute/path/to/msedgedriver --case navigation --count 10 \
  --artifacts build/native-recorder/new-navigation-run
```

通常クリック、文字入力、checkbox（labelも含む）、single select、Ctrl+multi select、リンク遷移を各10回連続入力し、値・順序・信頼済み入力と各配送段階を照合します。radioは公式Seleniumサンプルで補足します。入力のリトライやDOM直接操作での補正は行いません。IBusは英字の直接入力へ一時切替し、終了時に元のengineへ戻します。詳細は [実入力試験の監査と結果](docs/testing/recorder-native-input.md) を参照してください。

通常起動でも `FLOWTAPE_RECORDER_TRACE=/absolute/path/trace.jsonl` を指定すると、値を含まないRecorderの段階別診断を有効にできます。診断は通常のシナリオやregistryへ入りません。
