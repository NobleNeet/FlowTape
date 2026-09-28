# FlowTape v1 実装・仕様照合

`AGENTS.md` と `docs/00`〜`11` を基準とした実装監査です。仕様そのものは変更していません。

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

- 最終 pytest: **43 passed in 63.43s**。schema、semantic locator、曖昧・ゼロ件、frame / shadow、Recorder、loops、outputs、taint、UI 編集、再生カーソル、window tracking、保存 failure / 中断復旧、writer 競合、診断 log を検証。
- Edge 154.0.4258.37 と対応する user-cache WebDriver を使用。HTTP fixture は VM 内の `127.0.0.1` / `localhost` のみ。別オリジンと OOP iframe を含む。
- 画面表示ありの Edge と PySide6 で 1 Step → 続行 → click / read / append、picker の抑止と採取要素の一致を確認。
- PyInstaller 配布物から外部 scenario / registry / config を使った localhost 再生と UI 起動を確認。配布物の `doctor` でも、隔離した data fixture への Recorder 注入・picker・イベント配送・採取要素への再解決を確認（`capture_verified: true`）。
- 再現コマンド: README と `scripts/smoke_desktop.py`。画面と結果は `build/desktop-smoke/`。

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
