# エラーパス・入力経路のテスト不足を解消する

- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Branch: feature/test-add-error-path-tests
- Polished: 2026-08-15
- Milestone: 2026.2.0

## 目的

公開 API のエラーパス (破損データ検出のガード・コンストラクタの検証・入力変換) と入力経路のテストが欠落している状態を解消し、リグレッションを検出できるようにする。コード本体のバグ修正は各 issue で行い、本 issue はテスト整備のみに絞る。

## 現状

以下がテストされていない (いずれも `src/lib.rs` の実装を確認済み):

### Mp4DemuxSample.data のエラーパス

- `data_size` が `MAX_SAMPLE_SIZE` (1GB) を超える場合のエラー (`Sample data size too large (corrupted data?): ...`)
- read の返却長が `data_size` と不一致の場合のエラー (`Failed to read sample data: expected X bytes, got Y`)

既存の `test_demux_sample_properties` (tests/test_mp4.py) は正常系のみ (`.data` は呼ばずプロパティのみ検証)。`data_size=2**30+1` で `Mp4DemuxSample` を直接構築して `.data` を呼ぶと MAX_SAMPLE_SIZE ガードが確実に発火する (既存テストが同パターンの直接構築を行っている)。

### コンストラクタのバリデーションエラー

- `Mp4SampleEntryTx3g` の `background_color_rgba` / `default_style` の 4 バイト検証エラー (`PyValueError`) のテストがない

### extract_bytes のフォールバック経路

- `bytearray` / `memoryview` を `data` に渡すテストがない (list[int] のフォールバックテストは入力変換の修正を扱う別 issue (0033) の担当)

### ファイルパス / bytes 入力経路

- `Mp4FileMuxer(path)` / `Mp4FileDemuxer(path)` / `Mp4FileDemuxer(bytes)` の入力経路がテストされていない (`should_close_stream = true` の経路。既存テストの入力は BytesIO と socket / GzipFile のストリームのみで、path / bytes 入力はゼロ)

### feed ループ上限と `__next__` の MAX_SAMPLE_SIZE ガード

- `MAX_FEED_ITERATIONS` (10,000 回) 超過時のエラーと、`__next__` 側の `MAX_SAMPLE_SIZE` ガード (stsz 経由) のテストがない。破損 MP4 バイト列の手作りによる決定的な発火は困難で、検証方法の設計が必要 (後述の設計方針)

なお、本 issue の対象外とするエラーパス: `str_to_track_kind` の不正 track_kind による `ValueError`、`Mp4SampleEntryHev1` / `Hvc1` の `nalu_types` と `nalu_data` の長さ不一致による `ValueError` (いずれもテスト未追加だが、本 issue のスコープは上記の列挙に限定する)。

## 設計方針

- 各エラーパスを直接構築 (既存テストと同じパターン) または破損データ生成で発火させる決定的テストを追加する
- モック・スタブは使わない (規約)
- パス入力経路のテストには一時ファイル (`tmp_path` fixture) を使用する。内部で open されたストリームは Python 側からアクセス不能のため「閉じられたこと」の直接検証は行わず、以下で代替する:
  - Muxer: `close()` が正常に動作し、finalize 済みの出力ファイルが読み取り可能であること
  - Demuxer: `close()` 後に `sample.data` が I/O エラーになること (閉じたストリームへのアクセス失敗で間接検証)
- feed ループ上限と `__next__` の MAX_SAMPLE_SIZE ガードは、破損 MP4 バイト列による決定的な発火が困難なため、まず検証方法を設計してから追加する。設計しても決定的なテストを構築できない場合は、テスト対象から除外し、その旨と理由をテストコメントに明記する (テスト整備としての残存経路)
- これらのテストは、パースエラーの表面化 (別 issue 0036) の実装後に実施する (破損データの設計が、0036 実装前後で Err 経路の挙動 (StopIteration → RuntimeError) が変わる影響を受けるため。なお `__next__` の MAX_SAMPLE_SIZE ガード自体は 0036 と無関係に現在でも `RuntimeError` として発火する)

## 完了条件

- 上記のうちテスト追加が可能な全エラーパス・入力経路のテストが追加される (feed ループ上限と stsz 経由ガードは検証方法の設計結果に従う)
- `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過する

## 解決方法

1. `tests/test_mp4.py` に以下を追加する:
   - `Mp4DemuxSample` 直接構築で `data_size` 超過 / read サイズ不一致のエラーテスト (`.data` 呼び出しで発火)
   - `Mp4SampleEntryTx3g` の 4 バイト検証エラーテスト
   - `data` への `bytearray` / `memoryview` 入力のテスト (list[int] は入力変換の修正を扱う別 issue (0033) の担当)
2. `tests/test_mp4.py` に `tmp_path` を使ったパス入力 (Muxer / Demuxer) と bytes 入力 (Demuxer) のテストを追加し、`close()` 後の挙動を検証する (設計方針の代替検証方法による)
3. feed ループ上限と `__next__` の MAX_SAMPLE_SIZE ガードは、破損 MP4 バイト列の手作りによる決定的なテストを設計してから追加する (0036 の実装後)。決定的なテストを構築できない場合は、テスト対象から除外して理由を明記する
4. CHANGES.md の `### misc` に「[UPDATE] エラーパス・入力経路のテストを追加する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
