# remux サンプルプログラムが composition_time_offset を引き継がず A/V 同期が崩れる

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-remux-composition-time-offset
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`examples/remux.py` が ctts (composition time offset) を持つコンテンツ (B フレーム入り H.264 等) をリマルチプレックスする際、プレゼンテーションタイムスタンプが黙って失われる不具合を解消する。サンプルプログラムの目的 (「すべてのサンプルを新しい MP4 ファイルに書き直す」) に対してデータ影響のある欠落である。

## 現状

`examples/remux.py` の `Mp4MuxSample` 構築は `duration` と `data` までしか渡しておらず、`composition_time_offset` を引き継いでいない。

`Mp4DemuxSample` は `composition_time_offset` を公開しており (`src/lib.rs` の Mp4DemuxSample)、`Mp4MuxSample` も `composition_time_offset` 引数を受け付ける (2026.2.0 で追加) ため、引き継ぎは実装可能な状態にある。

実害: B フレームを持つ H.264 等を remux すると PTS (プレゼンテーションタイムスタンプ) が失われ、A/V 同期が崩れた出力ファイルが生成される。

## 設計方針

- `Mp4MuxSample` 構築時に `composition_time_offset=sample.composition_time_offset` を渡す
- remux の roundtrip で composition time offset が保持されることを検証するテストを追加する

## 完了条件

- remux 後も composition_time_offset が保持される
- 既存テストが全通過する
