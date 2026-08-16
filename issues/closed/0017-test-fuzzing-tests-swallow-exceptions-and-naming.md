# test_fuzzing.py の全 fuzzing テストが例外を握りつぶす + 命名規則違反

- Priority: High
- Created: 2026-07-22
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/fix-fuzzing-exception-swallowing
- Polished: 2026-08-12

## 目的

`tests/test_fuzzing.py` の 3 種類の問題を同時に解消する。

1. 全 10 fuzzing テストが `except (ValueError, RuntimeError, StopIteration): pass` で例外を握りつぶし、想定外例外の検出に失敗する
2. ファイル名・関数名が `test_` prefix なのに、実質は全て PBT (`@given` 付き) で `prop_` prefix が正しい
3. `tests/prop_error.py` の `prop_append_after_finalize_raises_error` が `pytest.raises(Exception)` で基底クラスを受けている

## 優先度根拠

High。

- CODEBASE.md の「明確な理由がない限りは try/except をテストでは利用しないこと」に違反
- 現状の実装は「クラッシュしなければ OK」しか検証しておらず、想定外の例外も沈黙する
- 命名規則 (pyproject.toml の「Property-Based Testing (PBT) は prop_ prefix を使用する」) に違反
- 修正コストは中程度 (例外処理の書き換え + muxer テストのデータ生成修正 + リネーム)

## 現状

### 例外握りつぶし

`tests/test_fuzzing.py` の全 10 テストが `except (ValueError, RuntimeError, StopIteration): pass` で例外を握りつぶしている。

- 全 10 箇所で `StopIteration` の catch はデッドコード (`for sample in demuxer` / `list(demuxer)` が自動吸収するため)
- `test_fuzzing_muxer_random_data` のみ finalize 後に demux し直してサンプル数の不変条件 (`assert len(demuxed) == sample_count`) を検証しているが、try ブロック内のため例外経路では実行されない
- muxer テストのデータ生成 (サンプルごとにランダムな timescale、keyframe が False になりうる) が muxer の仕様 (Timescale mismatch / No sync samples) に違反しており、「有効入力範囲では非例外」が成立していない

### 例外の実体

PyO3 移行後の現状では、`src/lib.rs` の `map_err` が shiguredo_mp4 の全エラーを `RuntimeError` (`mp4 error: {e}`) に変換する。Python 側に届きうるエラーメッセージは以下のとおり (src/lib.rs と shiguredo_mp4 2026.4.0 のソースで実在確認済み):

- `Sample data size too large (corrupted data?): ...`
- `feed_required_input: too many iterations (possible infinite loop on corrupted data)`
- `Required input position too large (corrupted data?): ...` / `Required input size too large (corrupted data?): ...`
- `Timescale mismatch for Video track: expected X, but got Y` (muxer。テストデータ生成の修正で排除する)
- `Video track has no sync samples` (muxer。テストデータ生成の修正で排除する)

demux 系テストで破損データを渡しても、パースエラーは PyO3 層 (`src/lib.rs` の `__next__`) で `PyStopIteration` に変換され、Python 側に例外として届かない (検証: `src/lib.rs` の `__next__` で `Err(_)` が `PyStopIteration` に変換される実装を確認)。そのため demux 系テストのリグレッション検出の力は限定的であり、パースエラーの例外化は本 issue のスコープ外 (Rust 側の変更が必要)。

### 命名規則違反

全 10 関数が `@given` 付きの PBT だが、ファイル名 `test_fuzzing.py`、関数名 `test_fuzzing_*`。

### pytest.raises(Exception)

`tests/prop_error.py` の `prop_append_after_finalize_raises_error` で `pytest.raises(Exception)` を使用している。`Exception` は基底クラスなので `AssertionError` / `SystemError` / `MemoryError` まで受けてしまう。実装ミスで別種例外が出ても pass する。

## 設計方針

### 例外握りつぶしの解消

- `StopIteration` の catch を削除 (全 10 箇所デッドコード)
- `test_fuzzing_muxer_random_data` はデータ生成を修正して「有効入力範囲では例外が出ない」ことを検証する:
  - timescale をテスト全体で 1 回だけ生成し、サンプル間で統一する
  - 先頭サンプルを keyframe=True に固定する
  - try/except を削除し、想定外の例外が飛んだらテスト失敗とする
- demux 系 9 テストは例外メッセージのホワイトリスト assert に書き換える:
  - 許容するのは破損データ由来の実在メッセージのみ。ホワイトリストは照合時に `str(e).lower()` と比較するため、全て小文字で指定する:
    - `"corrupted data"` (src/lib.rs の `Sample data size too large (corrupted data?)` と `Required input position too large (corrupted data?)` / `Required input size too large (corrupted data?)` の共通サフィックスに対応)
    - `"too many iterations"` (src/lib.rs の `feed_required_input` のループ上限に対応)
    - `"required input"` (src/lib.rs の `Required input position too large` / `Required input size too large` の 2 メッセージに共通する接頭辞に対応)
    - `"failed to read sample data"` (src/lib.rs の `sample.data` アクセス時の読み込みサイズ不一致に対応)
  - ホワイトリスト外の `RuntimeError` が飛んだらテスト失敗とする
  - `sample.data` アクセスも try の範囲に含める (データサイズ検証で例外を投げうるため)
  - 注記: Demux のパースエラーの Python 側への報告 (エラー隠蔽の解消) は別 issue で対応予定。その実装後は、ホワイトリストにコア由来のパースエラーメッセージ (`Failed to decode MP4 box` / `Sample table error` 系、小文字で `failed to decode mp4 box` / `sample table error`) を追加すること。ホワイトリストの追加は本 issue の実装時点でパースエラーが表面化しているかどうかに応じて行う

### 命名規則の統一

- `tests/test_fuzzing.py` → `tests/prop_fuzzing.py`
- 関数名: `test_fuzzing_*` → `prop_fuzzing_*`

### pytest.raises の型指定

- `pytest.raises(Exception)` → `pytest.raises(RuntimeError, match="finalized")` に変更
- 実エラーは `mp4 error: Muxer has already been finalized` (`MuxError::AlreadyFinalized`) で、`finalized` でマッチする

## 完了条件

- `tests/test_fuzzing.py` が `tests/prop_fuzzing.py` にリネームされる
- 全 10 関数の `test_fuzzing_*` が `prop_fuzzing_*` にリネームされる
- 全 10 箇所の try/except から `StopIteration` の catch がなくなる
- `prop_fuzzing_muxer_random_data` はデータ生成修正 (timescale 統一 + 先頭 keyframe=True) により有効入力で例外が出ない
- demux 系 9 テストは実在メッセージのみ (小文字で指定) のホワイトリスト assert に置き換わり、想定外の `RuntimeError` が飛んだら失敗する
- `tests/prop_error.py` の `prop_append_after_finalize_raises_error` が `pytest.raises(RuntimeError, match="finalized")` に変更される
- 全テスト通過

## 解決方法

1. `git mv tests/test_fuzzing.py tests/prop_fuzzing.py` でリネームした
2. `tests/prop_fuzzing.py` 内の全 10 関数の `test_fuzzing_*` を `prop_fuzzing_*` に置換した
3. モジュール docstring を「想定内の破損データ由来エラーは許容し、想定外の例外はテスト失敗として検出する」内容に更新した
4. `prop_fuzzing_muxer_random_data` のデータ生成を修正した:
   - timescale をテスト全体で 1 回だけ生成し、全サンプルで共通使用した
   - 先頭サンプルを keyframe=True に固定した
   - try/except を削除し、有効入力で例外が出ないことを検証するようにした
5. demux 系 9 テストの try/except をホワイトリスト assert に書き換えた:
   - モジュール定数 `ALLOWED_ERROR_PATTERNS` (小文字固定 4 パターン) を定義した
   - `except RuntimeError as e` で捕捉し、ホワイトリスト外のメッセージはテスト失敗とした
   - `StopIteration` / `ValueError` の catch を全箇所から削除した
   - `sample.data` アクセスを try の範囲に含めた (データサイズ検証の例外検出のため)
   - 重複していた ftyp ヘッダーを `VALID_FTYP_BOX` 定数に統合した
6. `tests/prop_error.py` の `prop_append_after_finalize_raises_error` の `pytest.raises(Exception)` を `pytest.raises(RuntimeError, match="finalized")` に変更した
7. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (104 passed, 7 skipped) を確認した
8. ブランチ名を `feature/fix-fuzzing-exception-swallowing` に変更した (当初の `feature/test-` は shiguredo-git の命名規則に該当しないため)
9. CHANGES.md の `### misc` に「[FIX] fuzzing テストの例外握りつぶしを解消し、PBT 命名規則に統一する」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
