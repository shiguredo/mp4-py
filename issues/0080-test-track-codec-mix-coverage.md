# トラック内のコーデック混在の挙動をテストで固定する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD
- Branch: feature/test-track-codec-mix-coverage
- Polished: {YYYY-MM-DD}

## 目的

同一トラック内でコーデックを切り替えるケース (音声トラック内の opus → mp4a 混在、字幕トラック内の stpp + tx3g 混在) の挙動をバインディング経由のテストで固定する。コア単体のテストしかない経路をカバーする。

## 現状

コア (shiguredo_mp4 2026.4.0) は音声トラック内のコーデック混在を chunk 分割で許容する一方、字幕トラック内の混在は `MixedSampleEntries` エラーで拒否する。しかし、バインディング経由のテストは存在しない。`sample_entry=None` の「前と同じエントリ」継承も、PBT では implicit に通っているだけで assert されない。

## 設計方針

- 音声トラック内の opus → mp4a 混在の mux → demux テストを追加する
- 字幕トラック内の stpp + tx3g 混在がエラーになるテストを追加する
- 音声トラック内のコーデック混在時の chunk 分割の正しさを検証する

## 完了条件

- コーデック混在の許容/拒否の挙動がテストで固定される
- 既存テストが全通過する
