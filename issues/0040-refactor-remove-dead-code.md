# 死にコードと過去実装の残骸を削除する

- Priority: Low
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-remove-dead-code
- Polished: 2026-08-15

## 目的

コードベースに残る死にコード・到達不能コード・過去実装 (nanobind / C++) の残骸を削除し、読者を誤解させる記述を取り除く。

## 優先度根拠

Low。

- 機能への影響はゼロのリファクタリングのみ
- 修正コストは小 (削除・書き換え + 検証)

## 現状

以下が確認されている:

### 死にコード・到達不能コード (`src/lib.rs`)

- `sample_entry_from_core` 内の `let _ = py;`: `py` は match の各アームで `Py::new(py, ...)` に使用済みのため意味のない文
- `Mp4FileMuxer` の `finalize_locked` / `append_sample` 内の「muxer already dropped」エラーパス: `MuxerState.core` は `new` で `Some` を代入した後どこでも `None` にされないため到達不能。`core` を `Option` でなくすことでエラー分岐自体を消せる

### `examples/demux.py` のデッドロジック

- `keyframe_count` ロジック: `if keyframe_count == 0: keyframe_count += sample.keyframe` は keyframe_count が 0 の間 (最初のキーフレームに達するまで) 実行されるが、その値はどこからも参照されないデッドロジック

### 過去実装の残骸

- `.clang-format`: C++ / ObjC 用の設定。C++ ソースはリポジトリに 0 件 (PyO3 完全移行済み) で、prek / CI からも参照されていない
- `src/lib.rs` のコメントに残る nanobind への言及 7 箇所 (モジュール docstring、`MAX_SAMPLE_SIZE` / `MAX_FEED_ITERATIONS` の定義コメント、`extract_bytes`、`HevcCommon`、`from_hvcc`、`MuxerState`): バインディング実装は nanobind から PyO3 に置き換え済みで、読者が参照できない過去実装との比較コメントは誤解を招く。なお本 issue の nanobind 言及の対象は `src/lib.rs` のみとし、`CODEBASE.md` の「単一スレッド性能は nanobind と同等」のような性能比較の言及は情報として残す (対象外)

なお、`CHANGES.md` の「**祝いリリース**」は削除しない。2026.1.0 は本プロジェクトの初回 stable リリースであり、「エントリ 0 件 + 祝いリリース」は時雨堂の他リポジトリ (libdatachannel-py / webcodecs-py / blend2d-py / libwebm-py / raw-player / sora-archive-uploader) でも初回リリースセクションに使われる標準形式であるため。

## 設計方針

- 到達不能コードは削除し、`Option` が不要になる場合は型を簡素化する
- nanobind 言及コメントは、過去実装との比較のみのものは削除し、値の根拠が重要であるものは「nanobind 版と同じく」の言及を削除して根拠そのものを残す (箇所ごとの扱いは解決方法を参照)
- 残骸 (`.clang-format`) は削除する
- 動作への影響はゼロのリファクタリングのみ

## 完了条件

- 上記の全対象が削除または書き換えされる (「祝いリリース」は削除しない)
- `cargo fmt --all -- --check` が通る
- `cargo build` / `cargo clippy --all-targets -- -D warnings` が通る
- `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過する
- CHANGES.md の `### misc` に追記する

## 解決方法

1. `src/lib.rs` の `sample_entry_from_core` 内の `let _ = py;` を削除する
2. `src/lib.rs` の `MuxerState.core` を `Option<CoreMuxer>` から `CoreMuxer` に変更し、「muxer already dropped」分岐 (2 箇所) を削除する
3. `examples/demux.py` の `keyframe_count` ロジックを削除する
4. `.clang-format` を削除する
5. `src/lib.rs` の nanobind 言及 7 箇所を以下のとおり処理する:
   - モジュール docstring の「nanobind 版と全機能パリティを目指す」の言及を削除する (docstring の冒頭「shiguredo_mp4 の PyO3 バインディング」は残す)
   - `MAX_SAMPLE_SIZE` / `MAX_FEED_ITERATIONS` の定義コメント: 「nanobind 版と同じく」を削除する (値の根拠である破損データ検出のための上限は既にコメントに記載されている)
   - `extract_bytes`: 「nanobind 版は…」の記述を削除する (残る「PyO3 0.29 では PyBuffer 経由で…」の文の表記整理はドキュメント修正の別 issue の担当)
   - `HevcCommon` / `from_hvcc`: 「nanobind 版と同じく」を削除する (並列配列・扁平化の説明は既にコメントに記載されている)
   - `MuxerState`: 「nanobind の ft_mutex 相当の…」を削除し、Free-Threading 対応の説明 (メソッドを &self に統一し内部状態を Mutex で保護する) のみ残す
6. CHANGES.md の「**祝いリリース**」は初回リリースの慣習マーカーのため削除しない (2026.1.0 セクションの「**リリース日**::」修正は別 issue の担当)
7. CHANGES.md の `### misc` に「[UPDATE] 死にコードと nanobind / C++ の残骸を削除する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
8. 全テスト通過を確認する
