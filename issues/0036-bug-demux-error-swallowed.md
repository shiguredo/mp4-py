# Demux のパースエラーが StopIteration / 空リストに隠蔽され破損データの検知が不能

- Priority: Medium
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-demux-error-swallowed
- Polished: 2026-08-15

## 目的

`Mp4FileDemuxer` が破損 MP4 / 対応外フォーマットをパースできなかったときに、エラーを報告せず「トラック 0 本」「サンプル 0 個の正常終了」として振る舞う問題を解消する。ユーザーがデータ破損を見逃さないようにする。

## 優先度根拠

Medium。

- 破損データのパースエラーが検知不能で、ユーザーは「正常終了」と誤認する
- 修正コストは中 (エラーパスの例外化 + 既存テストの調整 + 関連 issue との整合)

## 現状

`src/lib.rs` の `Mp4FileDemuxer` はコアのエラーを以下のように隠蔽する:

- `ensure_tracks` 内の `Err(_)` (InputRequired 以外の全エラー) → `tracks_cache = Vec::new()` + `ended = true`。`tracks` が空リストになる
- `__next__` 内の `Err(_)` (InputRequired 以外の全エラー) → `PyStopIteration`。`for` ループが静かに終わる

この結果、以下は全て「正常終了」に見える:

- 破損データのパースエラー (コアの `DemuxError::DecodeError` / `SampleTableError` 系。Display は `Failed to decode MP4 box: ...` / `Sample table error: ...` 等)
- moov が見つからない不正なファイル
- **fragmented MP4 (fMP4)**: コアの `Mp4FileDemuxer` は moof / trun を読まない (Phase は ftyp / moov のみ)。init segment 形式の fMP4 では、空の stbl がエラーにならないため、トラックは返るがサンプル 0 個になる (エラーなし)。fMP4 対応自体は別 issue で扱う (本 issue では非対応の明記のみ)

既存テストのうち、この握りつぶしの影響を受けるもの:

- `tests/test_fuzzing.py` の全テスト: `except (ValueError, RuntimeError, StopIteration): pass` で例外を許容 (修正は別 issue で予定)
- `tests/prop_error.py` の `prop_demuxer_handles_garbage_data` / `prop_demuxer_handles_truncated_mp4`: `except RuntimeError: pass` で例外を許容 (エラー表面化後も成立する)
- `tests/test_mp4.py` の `test_demuxer_with_invalid_data`: 16 バイトの無効データで空リストになることを assert しているが、この入力は EOF 経路 (32 バイトの読み込み要求を満たせず EOF になる) のため、エラー表面化後も失敗しない (変更不要)

## 設計方針

- デマクサーが回復不能なエラー (コアの `DemuxError::DecodeError` / `SampleTableError` 等) に遭遇した場合、`RuntimeError` を Python 側に伝える (エラーメッセージはコアの Display をそのまま `mp4 error: ...` 形式にする)
  - 例外の型分類 (カスタム例外) は、破損データ検出エラーの分類を扱う別 issue が demux パースエラーをスコープ外としているため、現状は分類先が存在しない。本 issue では `RuntimeError` のままとする
- エラーを返した後のデマクサーは `ended = true` + `tracks_cache = Some(Vec::new())` を設定する (`ensure_tracks` のエラー経路と同じ状態遷移にする。現在の `__next__` のエラー経路は `ended` のみを設定しており、`tracks_cache` を空にする点は変更になる)。以後の `__next__` は `StopIteration`、`tracks` は空リストを返す。`StopIteration` は常に正常終了のみを意味し、エラーは例外で伝える
- 完了条件の対象は「パースエラー (DecodeError / SampleTableError) が発生する破損ファイル」に限定する。moov 発見前に EOF に達するファイル (ftyp のみ・moov が途中で切れたファイル等) は EOF 経路のためエラーにならず「トラック 0 本の正常終了」のまま残る (この挙動は既存テスト `test_demuxer_with_empty_data` / `prop_demuxer_empty_file` の仕様でもある。EOF 経路のエラー化は本 issue のスコープ外)
- fMP4 対応 (コアの `Fmp4FileDemuxer` のバインド追加) は機能追加のため別 issue (0047) に分離済み。本 issue では README に「fMP4 非対応」を明記する (0047 が先に実装された場合は、その対応記述と矛盾しないよう明記を調整する)
- 関連する fuzzing テストの握りつぶし修正 (0017) とは実装順序を定める: 本 issue を先に実装し、0017 側のホワイトリストに新たに表面化するエラーメッセージ (DecodeError / SampleTableError 系) を追加する (0017 に注記済み)

## 完了条件

- パースエラー (DecodeError / SampleTableError) が発生する破損データが `RuntimeError` として Python 側に届く (SampleTableError 経路は可能な範囲で検証する)
- エラー後のデマクサーは `tracks` が空リスト・以後の反復が `StopIteration` で終わる
- 正常な MP4 のデマクスは従来どおり動作する
- README に fMP4 非対応が明記される (fMP4 対応の別 issue が先に実装された場合は、その対応記述と矛盾しない形で明記する)
- `RuntimeError` を検証するテストが追加される (32 バイト以上の不正データを使用)

## 解決方法

1. `src/lib.rs` の `ensure_tracks` / `__next__` の `Err(_)` アームを、エラー種別を確認して `RuntimeError` を返す形に変更する (メッセージはコアの Display を `mp4 error: ...` 形式で伝える)
2. エラーを返したら `ended = true` + `tracks_cache = Some(Vec::new())` を設定して以後 `StopIteration` / 空リストにする
3. README.md に fMP4 非対応を明記する
4. `tests/test_mp4.py` に、32 バイト以上の不正データ (例: ftyp 型不一致になるデータ) で `RuntimeError` になること、およびエラー後の `tracks` が空リスト・反復が `StopIteration` で終わることを検証するテストを追加する (既存の `test_demuxer_with_invalid_data` は EOF 経路のため変更不要)
5. fMP4 対応は別 issue (0047) に分離済みのため、本 issue で対応しない
6. CHANGES.md の `## develop` に「[FIX] Demux のパースエラーを Python 側に報告する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
7. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
