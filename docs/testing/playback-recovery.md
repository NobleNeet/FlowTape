# タブ・ブラウザを閉じた後の先頭再生

## 再現

ユーザーが作成したSelectシナリオは、先頭にPlaygroundのURLを開く `open` を持ちます。構文や開始URLの欠落ではありません。scenario/elementsを変更せず、試験専用のコピーと一時ブラウザprofileで、実Qt再生ボタンから検証します。ログ・preferences・credentialsの参照先も試験用ディレクトリに分離します。

修正前の `dcbb48c` で次の失敗を確認しました。

| 開始状態 | 結果 | 証拠（Gitには含めない） |
|---|---|---|
| 新しいblankタブを一つ残し、WebDriverが参照していた元タブを閉じる | 再生開始前に `closed window has no known surviving parent` | `build/playback-recovery/baseline-replacement-blank/` |
| ブラウザ終了をアプリが検出済み | 再生ボタンが無効、再生できない | `build/playback-recovery/baseline-closed-polled/` |

古いRecorderのwindow trackingが再生開始のobserver再設定に使われ、無効になったハンドルをruntimeのpopup復帰として扱っていました。ブラウザ終了については、UIが実driverを必須として再生を無効にし、`_new_playback` もdriverなしではブラウザ起動へ進まない状態でした。

## 修正と境界

- 新規再生の開始境界で、選択中の有効なタブを使うか、現在ハンドルが無効な場合は一つだけ生き残っているタブを初期状態として選択します。複数のタブから位置で選ぶことはありません。
- Recorderのwindow trackingを新しい実行境界に合わせ、閉じたtop-level Targetの輸送・preloadを除いてからobserverを設定します。
- シナリオと設定があるidle状態では、ブラウザ終了後も再生/続きを記録を使用できます。古いsessionが消滅済みならその資源を終了し、既存設定からEdgeを起動して新規Playerを作成します。
- 録画の未確定イベント・同期エラーは引き続き再生を阻止します。paused/failedの実行途中にブラウザを勝手に再起動してcursorを再開しません。runtimeのwindow復帰は既知の親を必要とする従来の規則を維持します。
- `続きを記録` のためのブラウザ起動で、成功後の自動録画というユーザー意図を消さないようにしました。
- ユーザーのシナリオに `open` を追加/書換えません。状態依存のシナリオには初期ページを推測しません。

## 実行方法

```bash
PYTHONPATH=. .venv/bin/python scripts/smoke_playback_recovery.py \
  --scenario /absolute/path/to/scenario-package \
  --driver /absolute/path/to/msedgedriver \
  --case replacement_blank \
  --artifacts build/playback-recovery/new-run
```

caseは `blank`（既存タブをabout:blankへ）、`replacement_blank`（古いハンドルを閉じる）、`closed`（poll検出前のブラウザ終了）、`closed_polled`（検出後）です。保存先は未作成のディレクトリを指定します。既存シナリオはバイト一致とSHA256を確認し、元ファイルは編集しません。実行終了、全Step IDの完了、最後のselect操作で指定した選択集合を照合します。タブ終了のセットアップはWebDriverを使い、再生は実GUIボタン→PlaybackWorker→Playerで行います。

検証サイトはUI Testing Playgroundとlocalhost fixture、ブラウザはLinux Edgeです。Windows実機・配布物は未検証です。OSパッケージ追加や権限昇格、禁止された外部書き込みは行いません。

## 最終結果

ユーザーの9 Stepシナリオのコピーを実Qt再生ボタンから実行し、全Stepの完了と最後のselect操作の値/選択集合を照合しました。元のscenario/elementsとコピーの内容はバイト一致で保持しています。

| 状態 | 完了Step | Edge再起動 | 最終証拠 |
|---|---:|---|---|
| 既存タブをabout:blankへ | 9 / 9 | 不要 | `build/playback-recovery/final-existing-blank/` |
| 新しいblankタブを残し、元のタブを閉じる | 9 / 9 | 不要 | `build/playback-recovery/final-replacement-blank/` |
| ブラウザ終了、pollの検出前 | 9 / 9 | 自動起動 | `build/playback-recovery/fixed-closed-before-poll/` |
| ブラウザ終了、pollの検出後 | 9 / 9 | 自動起動 | `build/playback-recovery/fixed-closed-polled/` |

最終回帰テストは **168 passed in 80.00s**。fresh-windowの一意な初期選択、複数タブの曖昧性拒否、runtimeで未知の親へ復帰しないこと、ブラウザ終了後の実GUI再生・続きを記録、未確定captureでの起動拒否、localhostの閉じたタブ輸送除去を確認しました。no-windowのモデルのみの初期化は維持し、実行時のwindow不在はエラーとします。
