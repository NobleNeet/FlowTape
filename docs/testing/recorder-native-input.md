# Recorder の実入力経路の検証

## 既存 smoke_select.py の範囲

この整理は実入力試験・修正に先立つ監査です。`scripts/smoke_select.py` の成功は実ユーザー入力の受入条件にしません。

| 検証すること | 検証しないこと |
|---|---|
| Qt の実ウィンドウ・記録ボタン・ページ/Target登録・保存 | OSマウス/キーボードからEdgeに入る入力経路 |
| Selenium Select のoption操作で発生したselect changeの正常系 | ネイティブプルダウン、Ctrl/Cmdによる複数選択、入力の信頼性 |
| 事前に記述したopen/clickをPlayerが実行できること | Recorderで記録したページ遷移のStep化 |
| 3つの単一選択と2つの複数選択、保存後の2回の再生 | 各種類10回の連続入力、入力値/順序の全件照合 |
| 最後のDOM選択状態 | observer/CDP/Transport/Normalizer/UI queueの欠落・重複の所在 |

## 入力と診断の境界

新しい試験は `scripts/smoke_recorder_native.py` と `scripts/native_input.py` を使います。ブラウザへの入力はX11 XTESTのマウスとキーイベントだけです。Selenium Select、WebElement.click/send_keys、JavaScriptによるDOM変更/イベント発火/フォーカス/スクロールは使用しません。読み取り専用のCDP Runtime.evaluateで対象の表示座標・URL・状態を確認し、スクロールもOSのホイール入力で行います。Recorder本体が観測用に注入するJavaScriptは通常製品と同じです。Qt登録ダイアログは実ウィジェットで回答し、警告・未確定記録・記録停止は失敗扱いにします。

試験前にIBusを英字の直接入力に切り替え、終了時に元のengineへ戻して一致を確認します。これは日本語IMEの受入試験ではありません。VMの既存X11/XTEST/IBusを使い、OSパッケージ追加や権限昇格を行いません。`python-xlib` は仮想環境に入れます。

連続操作のループはStep追加を待って次の操作を送るのではなく、通常の間隔で入力します。バッチの後に全期待Stepの個数・順序・値を照合します。ページロードを待つことと、操作失敗をリトライすることは区別します。失敗した操作の再送・DOM直接操作による補正は行いません。再実行は修正後の新規試験として別ディレクトリに証拠を残します。

`FLOWTAPE_RECORDER_TRACE=/absolute/path/trace.jsonl` で診断を有効にします。入力値、認証情報、URL、accessible name、DOM snapshotは診断へ書きません。実行時document/sequence ID、信頼済み入力フラグ、イベント種類、状態、件数、理由、Step IDだけを許可リストで記録します。RawCaptureEventとStage 1情報は引き続きメモリ内にだけ保持します。

| 段階 | 診断 |
|---|---|
| Recorder開始/切替 | recorder_boundary / observer_mode |
| OS入力→observer | observer_input（trusted / type / tag / mode） |
| observer→配送 | observer_emit / observer_delivery / observer_filter |
| CDP binding | cdp_binding / cdp_drain |
| RecorderTransport | transport_poll / transport_merged / transport_operation |
| EventNormalizer | normalizer_receive / normalizer_duplicate / normalizer_operation / normalizer_click_flush |
| UI | ui_enqueue / ui_dequeue / ui_pending / ui_ignored / ui_source_verified / ui_committed / ui_error |

## 再現した問題

- ページ遷移: OSの信頼済みクリックはobserver→CDP→Transport→Normalizer→UI queueまで届く。UIがsource URLとcurrent URLの違いを理由に記録停止し、Step化を保留していた。CDP輸送の欠落ではない。`baseline-navigation4/trace.jsonl` の同じdocument/event sequenceがこの全経路と `ui_pending: source_page_changed` を示す。
- チェックボックスのラベル: ラベルのクリックとブラウザが転送するinputクリックを別Targetとして記録し、同名Targetの再登録確認で停止。チェックボックス本体だけをクリックした旧試験では再現しなかった。`baseline-checkbox-label/` に証拠を保持。

## 修正の原則

遷移前のclick時に候補locatorが元要素へ一意に戻ることを共有DOM意味で同期確認し、その証拠とsourceのPageDefinition照合結果をStage 1へ含めます。UIは証明済みの候補だけを利用し、sourceページの登録/命名を明示的に行って元clickをStep化します。destination DOMをsource Targetの検証に使いません。証拠がない/曖昧/未確認のframe-shadow/ページ条件のケースは従来どおり保留し、推測で登録しません。

checkbox/radio等のlabel activationでは、labelの元イベントを除き、実際にcontrolへ転送されたclickを記録します。独立したリンク/ボタンなどのinteractive descendantは除外しません。

## 実行方法

```bash
.venv/bin/python -m pip install python-xlib
PYTHONPATH=. .venv/bin/python scripts/smoke_recorder_native.py \
  --driver /absolute/path/to/msedgedriver --case navigation --count 10 \
  --artifacts build/native-recorder/navigation-new-run
```

caseはclick/input/checkbox/single_select/multi_select/navigation、補足のradioです。保存先は未作成ディレクトリを指定し、過去の証拠を上書きしません。native操作は同じデスクトップを使うので同時実行しません。


## 最終の実入力結果

画面表示ありのEdgeで `build/native-recorder/verified-*/` に結果を保存しました。OS入力を再送した回数は0。各入力後のブラウザ状態と、バッチ後のStepの個数/順序/値を確認し、同一document/event sequenceをobserverからUIまで照合しています。

| 種類 | サイト/操作 | 連続操作 | 欠落 |
|---|---|---:|---:|
| click | Playground Click / OSマウス | 10 | 0 |
| input | Playground Text Input / 文字入力・Ctrl+A・Tabによる確定 | 10 | 0 |
| checkbox | Playground Auto Wait / 本体5回・label5回 | 10 | 0 |
| single select | Playground Select / ネイティブpopupをマウスで開きキーで選択 | 10 | 0 |
| multi select | Playground Select / Ctrl+マウスで2項目を選択/解除 | 10 | 0 |
| navigation | Playgroundトップ/Text Inputのリンク往復 | 10 | 0 |
| radio（補足） | Selenium公式web-form / 本体・labelによる選択切替 | 10 | 0 |

公開29ページのHTMLを調査したcatalogは `build/native-recorder/control-catalog.json` に保存しました。PlaygroundにはcheckboxがAuto Waitにありますが、radio入力は見当たりません。radioは開発規約で許可された `https://www.selenium.dev/selenium/web/web-form.html` で補足検証し、Playgroundで実施した結果とは分けています。

observerのclick/input/change/keydownはすべて `trusted: true`。意味のあるemitからTransportのOperationまで、さらにUI commit/明示ignoreまで欠落0です。inputケースの50イベントには入力欄クリック・Ctrl+A・Tabが、multi selectの20イベントにはmodifier-onlyキーが含まれ、単なる最終DOM状態だけを合格根拠にしていません。CDPとpollingによる診断コピーは別のtrace identityで重複排除します。値を含まない診断リングをpollingでも回収するため、診断binding単独の故障でobserver admissionが不明になることを防いでいます。

`baseline-navigation4` は修正前のURL差による停止、`fixed-navigation2` はURL確認とlive target参照の間で遷移する競合、`baseline-checkbox-label` はlabel/input二重Targetの問題を示します。修正済みの`verified-*`は新しい実行であり、同じ失敗した操作をその場でやり直して合格にしていません。

WindowsのOS入力・日本語IME経路・PyInstaller配布物は今回の受入試験の範囲外です。Linux X11の英字直接入力とRecorderの製品経路を検証しています。


## 完了条件の証拠対応

| 要求 | 証拠 |
|---|---|
| 旧smokeの範囲を先に整理 | 本文先頭の監査表。旧smokeのdocstring/READMEもSelenium integrationとして訂正 |
| Recorder開始からStep追加までの段階診断 | `flowtape/recorder_trace.py`、observer/bridge/transport/normalizer/UIへの計測。verified各traceと段階identity照合 |
| 失敗再現と原因の特定 | baseline-navigation4、fixed-navigation2、baseline-checkbox-labelの失敗report/trace |
| click/input/checkbox-radio/single/multi/navigation各10回 | Playgroundのverified6ケース各10回。radioはサイトにないため公式サンプルの補足10回を明示 |
| 操作の取りこぼし0 | expected Stepの個数/順序/値、同一document/sequenceの各段階照合、全input/keyのtrusted、missing=0 |
| リトライ/直接DOM補正を禁止 | native_inputのOS入力だけを使う実行loop。Stepを待って次を送る制御なし、retries=0 |
| 保守的な解決を維持 | source proofのdynamic-ID/ambiguity/context拒否、未確認ページ条件での保留、キャンセル時の再prompt防止テスト |
| 機密情報を診断へ出さない | 値非保存allowlist・CDP/poll trace ID dedup・binding不在のpoll fallback回帰テスト |
| 既存テスト一式 | 最終pytest結果をIMPLEMENTATION_STATUSへ記載 |

実入力の最終成果物はGitに含めず、再現スクリプト・原因回帰テスト・仕様をcommitします。元のbrowser profileやOSの設定を永続変更せず、終了時にIBusのengine一致を確認しました。

## 録画開始後のアドレスバーからのURL入力

以前のnavigationケースはリンククリックの記録を検証しており、アドレスバー入力は録画開始前のセットアップでした。そのため、録画開始後にサイトを直接開く操作が抜ける問題を検出できていませんでした。追加した `--case address_open` は、空のブラウザ状態で録画を開始してからOS入力でURLを開きます。

旧コミットを隔離worktreeで実行した `build/native-recorder/address-baseline-normal2/report.json` では、サイトは表示されたのに `open` が0件で失敗しました。ページJavaScriptがアドレスバーを観測できないことに加え、Python側にブラウザのナビゲーションをSemanticNavigationOperationへ変換する実装がありませんでした。

修正はCDPのtop-level navigation lifecycleを配送順のまま観測し、renderer起因ではない確定した `differentDocument` の遷移を `open` へ変換します。元の要求URLを保持し、server redirectは一つの操作にまとめます。リンク・フォーム・scriptによる遷移、iframe、録画外の開始、キャンセル、失敗、分類できないhistory/reloadには直接URL入力の `open` を推測しません。ブラウザへのアドレス入力のためのCtrl/Meta+L・Alt+Dは入力確定だけを行い、不要なDOM key Stepを残しません。FlowTape自身のURLコマンドは前の記録を確定し、明示openとCDP観測の二重記録を防ぎます。

途中の試験では、遷移で消えたcross-origin iframeのCDP sessionへの再設定が録画終了時に失敗する問題も確認しました。対象の消滅を確認して再設定を止め、既に受け取ったStage 1イベントは引き続きdrainします。生存するTargetの設定失敗は握りつぶしません。native試験は録画終了後のrecorder_error/pending/queueも検査し、途中の試験結果を最終合格として扱いません。

| 最終試験 | 結果 | 証拠 |
|---|---|---|
| 録画開始後、アドレスバーでPlaygroundトップ/Text Inputを10回開く | open 10件、余分なkey Stepなし、欠落0・リトライ0 | `build/native-recorder/address-ordered-final/` |
| 保存したopenシナリオを空ページからPlayerで再生 | 成功、最後のURL一致 | 同reportのreplayed=true |
| OSマウスでPlaygroundのリンクを10回往復 | click 10件、重複open 0件、欠落0・リトライ0 | `build/native-recorder/address-link-ordered-final/` |

アドレスバーケースはブラウザchromeを操作するためfullscreenにしません。URL入力自体のキーはページイベントではなくXTEST経路で送り、CDPによるcommit・Normalizer・UI確定のidentityを全件照合します。録画外の入力、renderer遷移、元URL保持、キャンセル、未知分類、applicationコマンド、Ctrl+L時のpending input確定、消滅したcross-origin iframeでの終了をローカルEdge/Qtと単体試験でも検証します。Windowsのネイティブ入力は引き続き未検証です。

最終全回帰テストは **161 passed in 97.54s**。DOM bindingもnavigationと同じ受信順で取り込み、非同期callbackで先行するclickがopenの後へ回らないことを回帰試験に追加しました。
