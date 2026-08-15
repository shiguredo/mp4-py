# Mp4Exception を Python 側でカスタム例外として捕捉できるようにする

- Priority: High
- Created: 2026-07-22
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/add-mp4-exception-python-registration
- Polished: 2026-08-12

## 目的

破損 MP4 データの検出エラーを Python 側で `mp4.Mp4Exception` として型分類できるようにする。`try: ... except mp4.Mp4Exception:` の形でユーザーアプリが破損データ由来のエラーを捕捉し、その他のエラー (内部状態エラー・入力バリデーション) と区別できるようにする。

## 優先度根拠

High。

- 現状は `src/lib.rs` の `map_err` が shiguredo_mp4 の全エラーを一律 `PyRuntimeError` (`mp4 error: {e}`) に変換しており、破損 MP4 の検出 (`Sample data size too large (corrupted data?)` 等) と内部状態エラー (`muxer/demuxer is closed`、`poisoned_err`) を型で区別できない。
- PyO3 移行前 (nanobind 時代) は C++ 側の `Mp4Exception` を登録する想定だったが、PyO3 完全移行で C++ 実装は消滅し、Python 公開例外は未実装のまま残っている。
- 破損 MP4 の検出と内部バグをアプリで分類したい要求は自然に発生する (破損データの報告と、ライブラリ側の問題の報告を分けたい)。
- 修正コストは小〜中程度 (`create_exception!` による例外定義 + `map_err` の変換分岐 + Python 側 re-export)。

## 現状

`src/lib.rs` の `map_err` 関数が shiguredo_mp4 の全エラーを `PyRuntimeError` に変換する。カスタム例外は定義されておらず (`create_exception!` は 0 件)、Python 側 (`python/mp4/__init__.py`) にも `Mp4Exception` は含まれない。

破損データ検出に関わるエラーメッセージは以下 (src/lib.rs で実在確認済み):

- `Sample data size too large (corrupted data?): ...` (`sample.data` getter / `__next__` の MAX_SAMPLE_SIZE ガード)
- `feed_required_input: too many iterations (possible infinite loop on corrupted data)` (feed ループ上限)
- `Required input position too large (corrupted data?): ...` / `Required input size too large (corrupted data?): ...`
- `Failed to read sample data: expected X bytes, got Y` (`sample.data` getter の読み込みサイズ不一致。破損 MP4 のサンプルサイズが実ファイルサイズを超える場合に発生し、0017 のホワイトリストでも破損データ由来と認定済み)

なお、demux のパースエラー (`DemuxError::DecodeError` / `SampleTableError`) は `src/lib.rs` の `__next__` で `PyStopIteration` に変換され Python 側に例外として届かない。この握りつぶしの解消は本 issue のスコープ外 (Rust 側の `__next__` 実装の変更が必要) であり、本 issue では「Python 側に例外として届く破損データ検出エラー」の型分類に限定する。

## 設計方針

- `pyo3::create_exception!` で `Mp4Exception` を定義し、基底を `PyRuntimeError` にする (既存の `except RuntimeError:` との後方互換性を維持するため必須)
- 例外定義は `#[pymodule]` inline module 内で `#[pymodule_export]` に追加し、`mp4.mp4_ext.Mp4Exception` として公開する (CODEBASE.md の inline module 形式に従う)
- `python/mp4/__init__.py` の import と `__all__` に `Mp4Exception` を追加し、`mp4.Mp4Exception` でアクセスできるようにする
- `map_err` を変更し、破損データ検出エラー (上記 4 種のメッセージを返す経路) だけを `Mp4Exception` に変換する。それ以外のライブラリエラーは従来どおり `PyRuntimeError` のまま
  - 変換はメッセージ文字列一致ではなく、呼び出し箇所ごとに `Mp4Exception::new_err` へ直接振り分ける方式とする (メッセージ一致は将来のエラーメッセージ追加で誤分類しやすいため)
  - 変換対象は破損データ検出の 6 呼び出し箇所: `sample.data` getter の MAX_SAMPLE_SIZE ガードと読み込みサイズ不一致、`feed_required_input` のループ上限と Required input position/size、`__next__` の MAX_SAMPLE_SIZE ガード

## 完了条件

- Python から `import mp4; mp4.Mp4Exception` でクラスにアクセスできる
- `except mp4.Mp4Exception:` で破損データ検出エラーを捕捉できる
- `Mp4Exception` は `RuntimeError` のサブクラスであり、既存の `except RuntimeError:` も引き続き機能する
- 追加テスト: `tests/test_mp4.py` に「破損データ検出エラーが `Mp4Exception` として発火し、`isinstance(e, RuntimeError)` も真」を確認するテストを追加
  - 発火経路の例: `Mp4DemuxSample` を `data_size=2**30+1` で直接構築して `.data` を呼ぶと MAX_SAMPLE_SIZE ガードが確実に発火する (既存の `test_demux_sample_properties` が同パターンの直接構築を行っている)。feed ループ上限・Required input 系は破損 MP4 バイト列の手作りが必要なため、まず `data_size` 超過の経路で検証し、他の経路は可能な範囲で追加する
  - 破損データ検出の 6 呼び出し箇所 (上記設計方針の変換対象一覧) のうち、テストで検証できていない経路がある場合は、その旨を残さず可能な限りカバーする
- 追加テスト: `Mp4Exception.__module__` が `mp4.mp4_ext` であること、pickle ラウンドトリップが動作することを確認するテストを追加 (module 名指定の誤りを検出するため)
- 追加テスト: 破損データ以外のエラー (例: `muxer is closed`。close() 後の append_sample で発火) は `Mp4Exception` ではなく従来どおり `RuntimeError` のままであることを、`type(e) is RuntimeError` で確認するテストを追加
- 型スタブ: pyo3-introspection 0.29 は `create_exception!` の例外を `.pyi` に含めない (実測確認済み)。実行時の動作には影響しないが、型チェッカから `mp4.Mp4Exception` を解決できない。型スタブへの反映は手書き `.pyi` の同梱が必要でビルド構成の変更を伴うため、本 issue の対象外とし別途検討する
- CHANGES.md の `## develop` に「[ADD] `Mp4Exception` を Python 側で捕捉可能にする」を追記 (著者表記付き、shiguredo-changelog スキルの形式に従う)

## 解決方法

1. `src/lib.rs` に `create_exception!` で `Mp4Exception` (基底 `PyRuntimeError`) を定義した。`create_exception!(mp4.mp4_ext, Mp4Exception, PyRuntimeError)` の第 1 引数で module 名を指定し、`__module__` を `mp4.mp4_ext` にした (pickle と repr のため)
2. `#[pymodule]` inline module の `#[pymodule_export]` に `Mp4Exception` を追加した
3. 破損データ検出の 6 呼び出し箇所 (`sample.data` getter の MAX_SAMPLE_SIZE ガードと読み込みサイズ不一致、`feed_required_input` のループ上限と Required input position/size、`__next__` の MAX_SAMPLE_SIZE ガード) を `Mp4Exception::new_err` に直接振り分けた
4. `python/mp4/__init__.py` の `from .mp4_ext import ...` に `Mp4Exception` を追加し、`__all__` にも追加した
5. `tests/test_mp4.py` にテストを追加した:
   - `test_mp4_exception_is_exported`: 公開と `RuntimeError` サブクラス性
   - `test_mp4_exception_module_and_pickle`: `__module__` と pickle ラウンドトリップ
   - `test_mp4_exception_caught_for_corrupted_sample_data`: `data_size` 超過 (MAX_SAMPLE_SIZE ガード)
   - `test_mp4_exception_caught_for_sample_data_size_mismatch`: 読み込みサイズ不一致
   - `test_mp4_exception_caught_for_corrupted_stsz`: stsz の sample_size 書き換えによる `__next__` ガード
   - `test_mp4_exception_caught_for_required_input_size`: largesize 巨大化による Required input size ガード
   - `test_mp4_exception_not_raised_for_other_errors`: muxer is closed / demuxer is closed が `type(e) is RuntimeError` のまま
6. 破損データ検出の 6 呼び出し箇所のうち、テスト未カバーの 2 経路 (`feed_required_input` のループ上限、Required input position ガード) は実質到達不能のため見送った
   - Required input position ガード: position > i64::MAX になる巨大なファイルオフセットを要求する破損データは、先に size ガードか EOF 判定が発火する
   - ループ上限: handle_input がエラーになると required_input() が None を返す設計のため、通常の破損データで 10,000 回連続ループは発生しない
7. CHANGES.md の `## develop` に「[ADD] `Mp4Exception` を Python 側で捕捉可能にする」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
8. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (104 passed, 7 skipped) を確認した
