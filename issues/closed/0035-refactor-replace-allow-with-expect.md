# src/lib.rs の #[allow(...)] を #[expect(...)] に置き換える (発火しない 1 箇所は削除)

- Priority: Low
- Created: 2026-08-15
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/refactor-replace-allow-with-expect
- Polished: 2026-08-15

## 目的

`shiguredo-rust` スキルの「`#[allow(...)]` を使わないこと（例外なし）」「lint 警告を抑制する必要があるときは必ず `#[expect(...)]` を使うこと」という規約に、`src/lib.rs` の 11 箇所が違反している状態を解消する。`#[expect]` にすることで、lint が発火しなくなった (不要になった) ときに検出できるようになる。

## 優先度根拠

Low。

- 規約違反だが機能への影響はゼロ
- 修正コストは小 (属性の置換 10 箇所 + 削除 1 箇所)

## 現状

`src/lib.rs` の `#[allow(...)]` は 11 箇所:

- `#[allow(clippy::too_many_arguments)]` (9 箇所): `Mp4SampleEntryVp08::new` / `Mp4SampleEntryVp09::new` / `Mp4SampleEntryAvc1::new` / `hevc_pyclass!` マクロ内の `new` / `Mp4SampleEntryAv01::new` / `Mp4SampleEntryMp4a::new` / `Mp4SampleEntryTx3g::new` / `Mp4MuxSample::new` / `Mp4DemuxSample::new`
- `#[allow(unused_variables)]` (2 箇所): `Mp4FileMuxer::__exit__` / `Mp4FileDemuxer::__exit__` (exc_type / exc_val / exc_tb の 3 引数が未使用)

このうち **`Mp4SampleEntryTx3g::new` は Rust 引数が 7 個のため `clippy::too_many_arguments` (デフォルト閾値 7、8 以上で発火) が発火しない**。`#[expect]` に置き換えると `unfulfilled_lint_expectations` エラーで clippy が失敗するため、この 1 箇所は属性ごと削除する (lint が発火しないため属性不要)。残りの 10 箇所は lint が現に発火するため `#[expect]` への置換が可能。

## 設計方針

- `Mp4SampleEntryTx3g::new` の `#[allow(clippy::too_many_arguments)]` は削除する (lint 未発火のため)
- 残りの 10 箇所 (too_many_arguments 8 箇所 + unused_variables 2 箇所) は `#[expect(...)]` に置き換える (`hevc_pyclass!` マクロ内の 1 箇所は、マクロが `#[rustfmt::skip]` 指定されていることに注意して同様に置き換える。展開先の Hev1 / Hvc1 の `new` は py 引数を除いて 20 引数のため expect が満たされる)

## 完了条件

- `src/lib.rs` の `#[allow(...)]` が 0 件になる
- `cargo clippy --all-targets -- -D warnings` が通る (`#[expect]` が未達で警告にならないこと)
- `cargo build` が通る
- `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過する
- CHANGES.md の `### misc` に追記する

## 解決方法

1. `src/lib.rs` の `Mp4SampleEntryTx3g::new` の `#[allow(clippy::too_many_arguments)]` を削除した (引数 7 個で lint 未発火のため)
2. 残りの 10 箇所の `#[allow(...)]` を `#[expect(...)]` に置き換えた (too_many_arguments 8 箇所 + unused_variables 2 箇所。`hevc_pyclass!` マクロ内の 1 箇所を含む)
3. `cargo clippy --all-targets -- -D warnings` が通ることを確認した (全 `#[expect]` が現に発火しており、`unfulfilled_lint_expectations` なし)
4. `maturin develop --release` でビルドできることを確認した (cargo build 単体は extension-module feature のためこの環境ではリンクエラーになる既知の挙動)
5. CHANGES.md の `### misc` に「[UPDATE] `src/lib.rs` の `#[allow]` を `#[expect]` に置き換え、発火しない 1 箇所は削除する」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
6. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (119 passed, 7 skipped) を確認した
