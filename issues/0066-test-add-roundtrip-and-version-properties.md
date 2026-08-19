# roundtrip とバージョン報告 API のプロパティテストを追加する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/test-add-roundtrip-and-version-properties
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

現状テストで一度も検証されていない、mux/demux の基本的な不変条件と公開 API のバージョン報告を PBT / 単体テストで固定する。回帰を早期に検出できるようにする。

## 現状

### 1. トラック情報の検証不足

- mux が 1 起点で採番する track_id と、demux が返す track_id の対応を検証するテストが存在しない。`__next__` のトラック解決は track_id による線形探索 (`src/lib.rs` の Mp4FileDemuxer::__next__) に依存しており、ここが壊れても現行テストでは検出できない
- `Mp4TrackInfo.duration` (トラック総尺) が全サンプル duration の合計に一致することを検証するテストが存在しない
- 複数トラックのインターリーブ時に、demux がグローバルなタイムスタンプ昇順で返すことを検証するテストが存在しない

### 2. 出力の再現性

バインディングは `creation_timestamp = Duration::ZERO` 固定のため、同一入力を 2 回 mux した場合のバイト列一致が原理上保証されるはずだが、これを検証するテストがない。非決定性 (乱数・時刻・順序依存) が混入しても検出できない。

### 3. デフォルト引数経路

各 SampleEntry コンストラクタのデフォルト引数 (例: Vp08 の bit_depth=8、Wvtt の config="WEBVTT") を経由するテストが 1 件もない (issue 0054 の Tx3g デフォルト破損はこのテスト欠落の結果として検出されなかった)。デフォルト経路を固定するテストを追加する。

### 4. バージョン報告 API

`mp4.__version__` / `mp4.native_version()` を検証するテストが存在しない。`build.rs` の env 埋め込み (SHIGUREDO_MP4_VERSION) と importlib.metadata の両経路が壊れても検出できない。

## 設計方針

- prop_roundtrip.py / prop_complex.py に track_id 連番・トラック総尺・タイムスタンプ昇順の検証を追加する
- 同一入力の二重 mux で出力バイト列が一致することを検証するテストを追加する
- 各 SampleEntry のデフォルト引数経路を固定するテストを追加する
- バージョン報告 API の単体テストを追加する (例: バージョン文字列がセマンティックバージョン形式であること、native_version が空でないこと)

## 完了条件

- 上記の不変条件・デフォルト経路・バージョン API がテストで固定される
- 既存テストが全通過する
