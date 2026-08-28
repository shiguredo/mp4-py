# fMP4 (fragmented MP4) をサポートする (デマクサー・マルチプレクサー・種別検知を全部バインドする)

- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Branch: feature/add-fmp4-support
- Polished: 2026-08-15
- Milestone: 2026.2.0

## 目的

fragmented MP4 (fMP4) 関連のコア API を全てバインドして、Python 側から fMP4 の読み書き・種別検知ができるようにする。fMP4 はストリーミング・ライブ配信で広く使われるフォーマットだが、現状は fMP4 を読むとエラーもなく「サンプル 0 個の正常終了」として静かに終わるため、ユーザーが非対応を検知できない。コア (`shiguredo_mp4`) 側には fMP4 関連の API が全て揃っており、未実装なのはバインディング側だけである。

なお、既存の `Mp4FileDemuxer` は fMP4 に非対応のままとする (対応するのは新設の fMP4 用 API)。`Mp4FileDemuxer` に fMP4 を渡した場合は従来どおり「サンプル 0 個の正常終了」になるが、種別検知 API で fMP4 を検知できるため、誤認は回避できる。

## 現状

`Mp4FileDemuxer` はコアの `Mp4FileDemuxer` (非フラグメント用) をバインドしており、moof / trun を読まない (コアの Phase は ftyp / moov のみ)。fMP4 の init segment を渡すと、空のサンプルテーブル (sample_count=0) を含む形式ではエラーにならず、トラックは返るがサンプル 0 個になる (エラーなし)。

コアには以下が存在するが、`src/lib.rs` には 1 つもバインドされていない (確認済み):

- **`Fmp4FileDemuxer`** (demux_fmp4_file.rs): fMP4 ファイル全体をデマクスする。既存 `Mp4FileDemuxer` と同じ入力駆動パターン (`required_input` / `handle_input` / `tracks` / `next_sample`) のため、既存の `feed_required_input` ループと互換
- **`Fmp4SegmentDemuxer`** (demux_fmp4_segment.rs): init segment と media segment を個別に渡してデマクスする (`handle_init_segment` / `tracks` / `handle_media_segment`)。セグメント単位の入力に特化
- **`Fmp4SegmentMuxer`** + **`SegmentMuxerOptions`** (mux_fmp4_segment.rs): fMP4 セグメントを生成する (`init_segment_bytes` / `create_media_segment_metadata` / `create_media_segment_metadata_with_sidx` / `mfra_bytes`)。`SegmentMuxerOptions` は `creation_timestamp` / `audio_track` / `video_track` / `subtitle_track` で、既存の `Mp4FileMuxerOptions` と同構造。既知の制限として、同一 TrackKind は 1 本まで、1 track = 1 traf = 1 trun 形式のみ対応。なお `create_media_segment_metadata` 系は moof + mdat ヘッダーのみを返し、payload の配置・init との連結・mfra の付加は呼び出し側の責務
- **`Mp4FileKindDetector`** + **`Mp4FileKind`** (demux_mp4_file_kind_detector.rs): mvex の有無で `Mp4` / `FragmentedMp4` を判定する (`required_input` / `handle_input` / `file_kind`)

既知の制限: コアの `Fmp4FileDemuxer` は、tfhd の `base_data_offset` フィールドを含む形式 (ファイル先頭からの絶対オフセットが記録されている形式) には対応していない (DecodeError になる)。対応対象は `base_data_offset` フィールドを含まない形式 (Fmp4SegmentMuxer が出力する形式) であり、この制限を README に明記する。`Fmp4SegmentDemuxer` 側の制限 (単一 moof + mdat ペアのみ、mdat 末尾の追加データはエラー) も README に明記する。

README.md の「使い方（基本 API）」冒頭一覧に「非対応: fragmented MP4 (fMP4)」が明記されている (`Mp4FileDemuxer` は fMP4 を読み取れず、stbl が空の典型的な init segment ではエラーなく「サンプル 0 個の正常終了」になる、という記載)。本 issue の実装時にはこの記述を「対応」側へ書き換える。

## 設計方針

- 対応範囲はコアの fMP4 関連 API の全バインド:
  - `Mp4Fmp4FileDemuxer` (コアの `Fmp4FileDemuxer` のバインド): fMP4 ファイル全体のデマクス。既存 `Mp4FileDemuxer` と同じパターン (遅延読み込み + stream_lock による I/O 直列化、lock_py_attached) を踏襲
  - `Mp4Fmp4SegmentDemuxer` (コアの `Fmp4SegmentDemuxer` のバインド): init segment / media segment の個別入力デマクス
  - `Mp4Fmp4SegmentMuxer` + `Mp4Fmp4SegmentMuxerOptions` (コアの `Fmp4SegmentMuxer` + `SegmentMuxerOptions` のバインド): fMP4 セグメント生成。`Mp4FileMuxer` / `Mp4FileMuxerOptions` のパターンを踏襲
  - `detect_mp4_file_kind(source) -> Literal["mp4", "fragmented_mp4"]` (コアの `Mp4FileKindDetector` のバインド): 種別検知関数。source は `Mp4FileDemuxer` と同じ入力形式 (path / bytes / ストリーム)
- エラー報告は既存の `Mp4FileDemuxer` と同じ方式に揃える。コア由来のエラーは `map_err` 経由で `RuntimeError` (`mp4 error: ...`) とし、破損データの検出ガードは `Mp4Exception` を返す。破損データ由来エラーの型統一を扱う issue の結果には後から追従する
- fMP4 セグメントのサンプル入出力は、既存の `Mp4MuxSample` / `Mp4DemuxSample` を再利用しない (コアの `Sample.data_offset` はセグメント payload 先頭からの相対オフセットであり、既存クラスの絶対オフセット + ストリーム前提と互換性がないため)。fMP4 用にサンプルクラスを新設するか、既存クラスを拡張するかは実装時に確定する
- fMP4 の roundtrip テストは、`Mp4Fmp4SegmentMuxer` でセグメントを生成し、`Mp4Fmp4FileDemuxer` / `Mp4Fmp4SegmentDemuxer` でデマクスして検証する

## 完了条件

- `Mp4Fmp4FileDemuxer` で fMP4 ファイル (base_data_offset 相対形式) をデマクスでき、サンプルが取得できる
- `Mp4Fmp4SegmentDemuxer` で init segment + media segment をデマクスでき、サンプルが取得できる
- `Mp4Fmp4SegmentMuxer` で fMP4 セグメントを生成でき、デマクスとの roundtrip が成立する (サンプルデータの整合性)
- `detect_mp4_file_kind` で fMP4 を検知できる (通常 MP4 が `"mp4"` と検知されることも検証する。moov 発見前に EOF になる不正なファイルは `RuntimeError` になる)
- 非 fMP4 の従来動作が変わらない (既存テストが全通過する)
- README に fMP4 対応と既知の制限 (base_data_offset フィールドを含む形式の非対応、同一 TrackKind 1 本まで、単一 moof + mdat ペアのみ、セグメント生成の使い方) が明記される
- README.md の「非対応: fragmented MP4 (fMP4)」の記述が、実装した fMP4 対応の内容と整合している

## 解決方法

1. コアの各 API (`Fmp4FileDemuxer` / `Fmp4SegmentDemuxer` / `Fmp4SegmentMuxer` + `SegmentMuxerOptions` / `Mp4FileKindDetector`) の詳細を読み、バインド方針 (公開クラス名・入力形式・トラック/サンプル取得) を確定する
2. `src/lib.rs` に `Mp4Fmp4FileDemuxer` を追加する (既存 `Mp4FileDemuxer` のパターン: 遅延読み込み + stream_lock による I/O 直列化を踏襲。エラー報告はパースエラー表面化 (0036) の設計に合わせる)
3. `src/lib.rs` に `Mp4Fmp4SegmentDemuxer` を追加する (init segment / media segment の個別入力)
4. `src/lib.rs` に `Mp4Fmp4SegmentMuxer` + `Mp4Fmp4SegmentMuxerOptions` を追加する (既存 `Mp4FileMuxer` / `Mp4FileMuxerOptions` のパターンを踏襲)
5. `src/lib.rs` に `detect_mp4_file_kind(source)` 関数を追加する
6. `python/mp4/__init__.py` の import と `__all__` に新 API を追加する
7. fMP4 の roundtrip テストを追加する (`Mp4Fmp4SegmentMuxer` でセグメントを生成し、`Mp4Fmp4FileDemuxer` / `Mp4Fmp4SegmentDemuxer` でデマクスしてサンプルデータの整合性を検証)
8. README.md に fMP4 対応と既知の制限を明記する
9. CHANGES.md の `## develop` に「[ADD] fMP4 対応 (デマクサー・マルチプレクサー・種別検知)」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
10. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
