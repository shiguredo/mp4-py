# Mp4DemuxSample に frozen が付いていない (CODEBASE.md 規約違反)

- Created: 2026-08-15
- Completed: 2026-08-16
- Branch: feature/refactor-add-frozen-to-mp4-demux-sample
- Polished: 2026-08-15

## 目的

`CODEBASE.md` の「Muxer / Demuxer / DemuxSample の pyclass は `frozen, skip_from_py_object` を付ける」という規約に、`Mp4DemuxSample` のみ違反している状態を解消する。Free-Threading 環境では PyCell の borrow が GIL で保護されないため、frozen (borrow 不使用) + Mutex による interior mutability と安全性の観点からも規約どおり揃える。

## 現状

`src/lib.rs` の `Mp4DemuxSample` は:

```rust
#[pyclass(module = "mp4.mp4_ext", skip_from_py_object)]
struct Mp4DemuxSample {
```

`frozen` が付いていない。`Mp4FileMuxer` / `Mp4FileDemuxer` / `Mp4MuxSample` / 全 SampleEntry は `frozen` 付きで、規約対象のクラスではこのクラスだけ欠落している (規約対象外の `Mp4FileMuxerOptions` を除く)。

`frozen` 付与の実現可能性:

- 全フィールドが Sync 要件を満たす: `track: Py<Mp4TrackInfo>` と `sample_entry: Option<Mp4SampleEntryAny>` は参照先クラスが全て frozen のため Sync。`input_stream: Py<PyAny>` + `stream_lock: Arc<Mutex<()>>` は frozen な `Mp4FileDemuxer` が同一構成で成立させている実績がある。`data_cache: Mutex<Option<Py<PyBytes>>>` は Mutex 内包
- `data` getter のキャッシュ書き込みは既に `lock_py_attached(py)` 経由の内部可変 (Mutex 経由) であり、frozen を付与しても無変更で継続できる。frozen は Python 側の属性変更と Rust 側の `borrow_mut` を禁止するが、Mutex 等の interior mutability は禁止しない
- `timestamp_seconds` / `duration_seconds` / `__repr__` の `self.track.borrow(py)` は frozen の `Mp4TrackInfo` に対する読み取り borrow であり変更不要 (frozen は `borrow_mut` のみ禁止)

## 設計方針

- `Mp4DemuxSample` の pyclass 属性に `frozen` を追加する
- 挙動は不変のリファクタリングのため、CHANGES.md の `### misc` に記載する

## 完了条件

- `Mp4DemuxSample` に `frozen` が付与される
- `data` getter の遅延読み込みとキャッシュが従来どおり動作する (既存テストが全通過する)
- CI の Free-Threading (3.14t) ジョブが通る (frozen 付与の検証は 3.14t でのテスト実行を含む macOS ジョブで行う)

## 解決方法

1. `src/lib.rs` の `Mp4DemuxSample` の `#[pyclass]` に `frozen` を追加した (`#[pyclass(module = "mp4.mp4_ext", frozen, skip_from_py_object)]`)
2. `cargo build` / `cargo clippy --all-targets -- -D warnings` が通ることを確認した (全フィールドが Sync 要件を満たす。data getter のキャッシュ書き込みは Mutex 経由の interior mutability で無変更で動作)
3. `tests/test_mp4.py` に 2 テストを追加した:
   - `test_demux_sample_properties` に frozen 固有の挙動検証を追加: `demux_sample.track = None` が `readonly attribute` (Py_READONLY の member_descriptor) で拒否されることを検証
   - `test_demux_sample_data_cached`: data アクセスの 2 回目がキャッシュを返すこと (`is` 同一性) を検証
4. CHANGES.md の `### misc` に「[UPDATE] `Mp4DemuxSample` に frozen を付与する」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (119 passed, 7 skipped) を確認した
6. CI (wheel.yml) の Free-Threading ジョブが通ることを確認した
