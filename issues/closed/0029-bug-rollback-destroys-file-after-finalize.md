# finalize 後の append_sample 失敗時にロールバックがファイル全体を破壊する

- Created: 2026-08-15
- Completed: 2026-08-16
- Branch: feature/fix-rollback-destroys-file-after-finalize
- Polished: 2026-08-15

## 目的

`Mp4FileMuxer` で `finalize()` を実行した後に `append_sample()` を呼ぶと、エラーが返るだけでなく、出力ファイル全体が破壊されるバグを解消する。エラーパスが出力物を静かに壊す (データ損失) 状態を放置できないため。破壊は `reserved_moov_box_size` の値に依存せず、既定値 0 でも発生する。

## 現状

`src/lib.rs` の `Mp4FileMuxer::append_sample` は write 以降の失敗時に `rollback_append` でストリームを巻き戻す。`rollback_append` は `seek(data_offset)` + `truncate(data_offset)` で `data_offset` (append 前のストリーム位置) まで切り詰める。

問題は `finalize()` 後のストリーム位置にある。コア (shiguredo_mp4 2026.4.0) の `FinalizedBoxes::offset_and_bytes_pairs` は head → moov (非 faststart 時のみ) → **mdat ヘッダー** の順で返し、mdat ヘッダーが最後に書かれる。このため finalize 直後のストリーム位置は mdat ヘッダー末尾 (`mdat_box_offset + 16`) となり、ファイルにはその後方に mdat ペイロード (および非 faststart では末尾の moov) が残っている。

finalize 後に `append_sample` を呼ぶと:

1. `tell()` で得た位置 (mdat ヘッダー末尾) に write を実行 → mdat ペイロード先頭を上書き
2. コアの `append_sample` が `AlreadyFinalized` を返す (finalize 済みのため)
3. `rollback_append` が `truncate(mdat_box_offset + 16)` を実行 → mdat ペイロード全体が消え、ファイルが破損する (faststart 時は moov が先頭予約領域に残るが、ペイロード消失でファイルは破損する)

この破壊は `reserved_moov_box_size` の値に依存しない。`finalized` フラグが立っているため、以後 `finalize()` を呼び直しても修復されない。

既存テスト `tests/prop_error.py` の `prop_append_after_finalize_raises_error` は例外が発生することだけを検証しており、ファイルの内容破壊を検出しない。`tests/test_mp4.py` のロールバック関連テストは全て finalize 前の失敗経路のみを対象としている。

## 設計方針

- `append_sample` 冒頭 (write 実行前) で `state.finalized` をチェックし、finalize 済みなら write に進む前にエラーを返す
  - `state.closed` チェックは既に存在する (`muxer is closed`) ため、追加が必要なのは `finalized` のみ
  - エラーは既存のコア経路と同じ `RuntimeError` とし、コアの `MuxError::AlreadyFinalized` と同じ文言 `Muxer has already been finalized` をそのまま使う。後述の整合性のため
- ロールバックを「しない」方式は採らない。write が mdat ペイロード先頭を上書きした後にロールバックを省略しても、破損ファイルは残るため完了条件を満たせない
- なお、`finalize_locked` のストリーム書き込み失敗で `state.finalized` が false のままコア側が finalize 済みになる中間状態 (別の経路) は、本 issue のスコープ外 (API のエラーハンドリング一貫性を扱う別 issue のスコープ)

## 完了条件

- finalize 後に `append_sample` を呼ぶと `RuntimeError` (メッセージに "finalized" を含む) が発生し、出力ファイルの内容が破壊されない
- finalize 前の `append_sample` 失敗 (既存のロールバック経路) は従来どおり巻き戻し後に retry できる
- 追加テストで「finalize 後 append の失敗時、出力バッファの内容が finalize 直後の内容と一致する」ことを検証する

## 解決方法

1. `src/lib.rs` の `Mp4FileMuxer::append_sample` 冒頭 (write 実行前) で `state.finalized` をチェックし、finalize 済みなら `PyRuntimeError` (コアの `MuxError::AlreadyFinalized` と同じ文言 `Muxer has already been finalized`) を返すようにした
   - チェック順は lock → closed → finalized → tell/write で、write および tell より前に finalized を検知する
   - コメントに `FinalizedBoxes::offset_and_bytes_pairs` が mdat ヘッダーを最後に返すため finalize 直後のストリーム位置が mdat ヘッダー末尾になる、という根拠を明記した
2. `tests/test_mp4.py` に 2 テストを追加した:
   - `test_append_sample_after_finalize_preserves_output`: 通常レイアウトで finalize 後の append_sample が `RuntimeError` (match="finalized") になり、出力バッファの内容が finalize 直後と一致すること (ロールバックによる truncate が実行されないこと) を検証
   - `test_append_sample_after_finalize_preserves_output_with_faststart`: `reserved_moov_box_size` 指定時 (faststart) でも同様に出力が破壊されないことを検証
3. CHANGES.md の `## develop` のメインセクションに「[FIX] finalize 後の append_sample が出力ファイルを破壊しないようにする」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
4. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (106 passed, 7 skipped) を確認した
