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

シナリオディレクトリには `scenario.yaml` と `elements.yaml` を置きます。

```bash
flowtape validate /path/to/scenario-directory
flowtape run /path/to/scenario-directory --config /path/to/config.yaml
flowtape ui /path/to/scenario-directory --config /path/to/config.yaml
flowtape doctor --config /path/to/config.yaml --headless
```

CLI 再生は `scenario.yaml` の `mode` に従います。画面では `実行` / `確認` / `デバッグ` と再生速度を別々に選べます。`risk: 破壊的` の実行には、設定された確認ポリシーを適用します。

`doctor` は外部サイトを使わず、設定された Edge / WebDriver と Recorder の注入・選択・要素一致を確認します。

### Recorder / Editor

- Edge のクリック、入力、select、キーボード操作を記録します。パスワード値は取得せず、credential 参照を指定します。
- picker / bind / rebind では対象操作を抑止し、同じ採取要素に一意に戻れる locator を検証します。既存 target が同じ要素を表す場合は再利用します。
- collection picker は代表行から集合候補を作り、件数・例・ハイライトを確認して登録します。
- ネストした範囲を `if` / `repeat` / `while` / `for_each` で囲み、else への移動、解除、移動、undo / redo ができます。
- read / append と outputs は明示的に作成します。「選択後に記録」で既存の後続 Step を残して挿入できます。
- 名前変更はページ別に参照を解析し、ページを確定できない参照は明示的に確認します。
- 保存は明示操作です。外部編集を検出したら再読込・GUI 保持・保留を選べます。保存途中の I/O エラーでは両ファイルを元に戻します。

保存途中のプロセス終了は package 内の `.flowtape-save.json` で検出します。UI 起動時の選択、または `flowtape recover /path/to/package --choice rollback` / `--choice complete` で、保存前へ戻すか保存を完了するか明示的に決めます。未復旧の package は実行しません。

同じ package の同時保存は writer lock で拒否します。run の診断は `paths.logs` 配下へ `logging.level` に従って保存します。展開済みの入力値・取得値は記録せず、credential 値は redaction します。

### Player

1 Step、選択位置まで、一時停止・再開、停止、再試行、明示的なスキップに対応します。失敗した Step は保持し、再試行時は DOM を再解決します。実行済み部分の編集は再開始または現在の状態で続行を選択します。変数・outputs・モードの変更には再開始が必要です。

記録中に対象 DOM が消えた場合、操作は未確定のまま保持します。操作前ページを再表示して対象を再選択し、元の操作に紐付けます。同期エラーが起きた区間は黙ってつながず、新しい記録境界を明示的に開始します。

## ビルドとデスクトップ確認

```bash
.venv/bin/python -m pip install -e '.[ui,test,build]'
.venv/bin/pyinstaller FlowTape.spec
.venv/bin/python scripts/smoke_desktop.py --driver /absolute/path/to/msedgedriver --executable dist/FlowTape/FlowTape
```

Linux 配布物は `dist/FlowTape/FlowTape` です。Windows 用の配布物は Windows 上で同じ spec からビルドしてください。ユーザーの YAML・設定・WebDriver は配布物の外部に置きます。

スモーク確認は画面表示ありの Edge とローカル HTTP fixture を使い、`build/desktop-smoke/` に画面と結果を保存します。仕様照合結果と未確認事項は [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) を参照してください。
