# Mp4DemuxSample に frozen が付いていない (CODEBASE.md 規約違反)

- Priority: Medium
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-add-frozen-to-mp4-demux-sample
- Polished: 2026-08-15

## 目的

`CODEBASE.md` の「Muxer / Demuxer / DemuxSample の pyclass は `frozen, skip_from_py_object` を付ける」という規約に、`Mp4DemuxSample` のみ違反している状態を解消する。

## 優先度根拠

Medium。

- `CODEBASE.md` の pyclass 規約違反 (Free-Threading 環境では PyCell の borrow が GIL で保護されないため、frozen (borrow 不使用) + Mutex による interior mutability が安全になる点も関連)
- 修正コストは小 (pyclass 属性への 1 語追加)

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

1. `src/lib.rs` の `Mp4DemuxSample` の `#[pyclass]` に `frozen` を追加する
2. `cargo build` / `cargo clippy --all-targets -- -D warnings` が通ることを確認する
3. CHANGES.md の `### misc` に「[UPDATE] `Mp4DemuxSample` に frozen を付与する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
4. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
5. CI (wheel.yml) の Free-Threading ジョブが通ることを確認する
