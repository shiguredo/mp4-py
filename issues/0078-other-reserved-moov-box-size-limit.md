# reserved_moov_box_size の巨大値でメモリが枯渇する問題を解消する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-reserved-moov-box-size-limit
- Polished: {YYYY-MM-DD}

## 目的

`Mp4FileMuxerOptions.reserved_moov_box_size` に巨大な値が渡された場合に、メモリが枯渇してプロセスが abort する問題を解消する。上限検証を追加して安全に弾く。

## 現状

`src/lib.rs` の `Mp4FileMuxerOptions::new` は `reserved_moov_box_size` を `usize` で受け取り、値域を検証しない。コア (shiguredo_mp4 2026.4.0) の `build_initial_boxes` は `vec![0; reserved_moov_box_size + ...]` で free ボックスを確保するため、`reserved_moov_box_size = 2**60` のような入力で即座に巨大メモリを消費し、OOM abort (プロセス死) に直結する。コア側の検証は飽和加算 (saturating_add) のみで、割り当て前の上限チェックが存在しない。

## 設計方針

- コンストラクタで上限値を設け、超過時は `ValueError` で弾く
- 上限値は実用上必要な最大値 (実ファイルサイズ相当か、明確な定数) を根拠に設定する
- 巨大値のテストを追加する

## 完了条件

- 巨大な `reserved_moov_box_size` が `ValueError` で弾かれる
- 通常の値は従来どおり動作する
- 既存テストが全通過する
