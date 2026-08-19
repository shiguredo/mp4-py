# CHANGES.md の 2026.2.0 リリースノート文言を実装と一致させる

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/doc-fix-changes-release-notes
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

2026.2.0 のリリースノートとなる CHANGES.md の develop セクションを、実装の実態と一致させる。誤情報を公開しないようにする。

## 現状

CHANGES.md の develop セクションに、実装と食い違う記述・古い記述が複数残っている:

### 1. `reserved_moov_box_size` の「uint32」表記

CHANGES.md は「`Mp4FileMuxerOptions.reserved_moov_box_size` を `uint32` で受け取るようにする」と記載するが、実装 (`src/lib.rs` の Mp4FileMuxerOptions) は `usize` で受け取る。コア (shiguredo_mp4 2026.4.0) も `usize`。`C API 型変更 (u64 → u32) に追従` の記述は nanobind 時代 (C API 経由) の名残であり、PyO3 移行後は意味をなさない。

### 2. `Mp4Exception` の説明が実態より広い

「破損 MP4 データの検出エラーを `mp4.Mp4Exception` として型分類できるようにする」とあるが、パースエラー (DecodeError / SampleTableError) は素の `PyRuntimeError` のままである。`Mp4Exception` になるのは feed 系とサンプルデータ系のみ。このままリリースすると「`except mp4.Mp4Exception:` で破損データ由来を一律捕捉できる」誤情報が載る。

### 3. `.pyi` 型スタブ同梱の記述が実態より先行

「.pyi 型スタブを wheel に自動同梱する」とあるが、pyo3-introspection の `--generate-stubs` が `create_exception!` 由来の `Mp4Exception` を .pyi に含めない問題が確認されている。pyproject.toml のコメント「型スタブの同梱は別途検討する」と矛盾する。

### 4. リリース日形式のタイポ

2026.1.0 節の `**リリース日**:: 2026-01-07` はコロンが 2 つ。shiguredo-changelog 規約は `**リリース日**: YYYY-MM-DD` (コロン 1 つ)。2026.2.0 節を新設する際に同形式をコピーすると typo が再発する。

### 5. 凡例の種別順

冒頭の凡例は `CHANGE → UPDATE → ADD → FIX` の順だが、規約と develop セクション本体の並びは `CHANGE → ADD → UPDATE → FIX`。

## 設計方針

- 各エントリを実装の実態に合わせて修正する (文言の限定・修正・該当エントリの調整)
- 2026.2.0 節を新設する際のテンプレートとして、`**リリース日**: YYYY-MM-DD` の形式を正しく使う
- 凡例の順序を規約に合わせる
- この issue は文言修正のみ扱う。実装側の変更 (パースエラーの Mp4Exception 化等) は別 issue (0053 等) に委ねる

## 完了条件

- 2026.2.0 のリリースノートに誤情報・古い記述が含まれない
- リリース日形式が規約どおり
- 凡例の順序が規約どおり
