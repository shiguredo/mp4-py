# append_sample 失敗時に write 済みバイトがストリームに残って以降破綻する

- Priority: Medium
- Created: 2026-07-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-append-sample-stream-rollback-on-error
- Polished: 2026-08-12

## 目的

`Mp4FileMuxer::append_sample()` (src/lib.rs) は「(1) 出力ストリームに `sample.data` を書き込む → (2) `core.append_sample()` を呼ぶ」の順序で処理する。ステップ (2) 以降で失敗した場合、Muxer 側は「サンプル未追加」の状態のままだがストリーム位置だけが進んでしまい、以降の `append_sample()` は必ず `MuxError::PositionMismatch` (shiguredo_mp4 の mux モジュール) で失敗し続ける。この不整合を解消する。

## 優先度根拠

Medium。

- 失敗ケースは異常系だが、ユーザー入力が原因 (timescale=0、先頭サンプルの sample_entry 未指定等) の場合に発生し、リカバリ不能な状態に陥る。
- 現状はドキュメント上の記載もなく、ユーザーは「例外を catch して次のサンプルを試す」流儀で書きたくなるが、それが破綻する。
- shiguredo_mp4 の `append_sample` は「エラーを返した場合も内部状態は変わらない。呼び出し側は内容を補正したうえで再呼び出しできる」と契約している (shiguredo_mp4 の mux モジュールの doc コメント)。ストリームを巻き戻せば retry が成立する。

## 現状

`src/lib.rs` の `Mp4FileMuxer::append_sample` は以下の順序で処理する:

1. `stream.tell()` で書き込み位置を取得
2. `stream.write(sample.data)` でデータを書き込む
3. `sample.timescale` の NonZeroU32 検証 (timescale=0 なら `PyValueError`)
4. `sample.track_kind` の検証 (`str_to_track_kind`)
5. `sample.sample_entry` のコア変換
6. `core.append_sample()` を呼ぶ (失敗時は `map_err` で `RuntimeError`)

ステップ 2 の write 後にステップ 3〜6 のいずれかが失敗すると、`output_stream` には `sample.data` が書き込まれたままで、次の `append_sample()` 呼び出しでは `tell()` が実位置を返すが Muxer は元の位置を期待し、`MuxError::PositionMismatch` で失敗し続ける。

append_sample 時に実際に失敗する入力 (検証済み):

- `timescale=0` (ステップ 3 の `PyValueError`)
- 先頭サンプルで `sample_entry=None` → `MuxError::MissingSampleEntry`
- 同一トラックで timescale を変える → `MuxError::TimescaleMismatch`

なお、`composition_time_offset` の範囲検証は shiguredo_mp4 の finalize 時 (ctts ボックス生成) のみで、append_sample では検証されず失敗しない。

## 設計方針

### 方針 A: seekable なストリームでは truncate + seek で巻き戻す

- `append_sample` 内の write 以降の全エラー経路で、書き込んだバイトを巻き戻す
- `stream.seekable()` / `stream.truncate()` が使えるか判定し、使える場合は `seek(data_offset)` + `truncate()` で巻き戻す
- 巻き戻せない場合 (パイプ等) は例外メッセージに「Muxer は使用不能状態になった。破棄すること」を英語で付加する
- 巻き戻し自体が失敗した場合も同様に「使用不能」の案内を英語で付加してから、元のエラーを優先してそのまま伝播する
- `stream.tell()` 自体が失敗するストリーム (例: 実パイプ) は `data_offset` を取得できないため、write に進む前にエラーを返し、「使用不能」の案内を英語で付加する (パイプでは write 後の巻き戻しも不可能なため、使用不能状態)
- ロールバック実装は `append_sample` 内で write 前に `stream.tell()` で取得した `data_offset` を記録し、write 以降の全エラー経路 (timescale 検証、track_kind 検証、sample_entry 変換、`core.append_sample()`、write 自体の失敗) で実行する
  - 実装構造は write 以降をクロージャ等にまとめ、エラー時にロールバックを実行してから伝播する 1 箇所集約とする

## 完了条件

- `append_sample()` 中のエラー発生時に、seekable なストリームならストリーム位置が呼び出し前に戻り、書き込まれたバイトが除去される (`stream.getvalue()` の長さで確認)
- seekable でないストリームの場合 (または巻き戻しに失敗した場合)、例外メッセージに「Muxer は使用不能状態になった。破棄すること」が英語で明記される
- README.md の「MP4 ファイルの作成」節と `Mp4FileMuxer` の class docstring に「append_sample が失敗した場合の挙動」を明記:
  - seekable ストリームで巻き戻しに成功した場合は、入力の補正後に retry 可能であること
  - 非 seekable ストリーム (または巻き戻しに失敗した場合) は Muxer が使用不能状態になるため、close() を呼ばずに破棄すること (close() は finalize を実行し破損ファイルを書き出すため)
  - `with` 構文では例外発生時も `__exit__` が close() → finalize を実行してしまうため、非 seekable ストリームでは with 構文を使わず、失敗時の破棄を考慮した使用方法を取ること
- 追加テスト: `timescale=0` で append_sample を失敗させ、その後 `tell()` の位置が変わらず、`getvalue()` の長さが write 前のままであることを確認するテスト (seekable ストリームで)
- 追加テスト: 同シナリオを retry パターンで実行し、2 度目の append_sample が成功することを確認
- 追加テスト: 非 seekable ストリーム (例: `os.pipe()` 由来の実パイプ) で失敗させ、例外メッセージに「Muxer は使用不能状態になった。破棄すること」が含まれることを確認 (実パイプでは `tell()` が先に失敗するため、そのエラーに案内が付加されることを確認する)

## 解決方法

1. `src/lib.rs` の `Mp4FileMuxer::append_sample` を修正する:
   - `stream.tell()` で取得した `data_offset` を保持
   - write 以降のエラー経路 (timescale 検証、track_kind 検証、sample_entry 変換、`core.append_sample()`) でロールバック処理を実行してからエラーを返す
   - ロールバック処理: `stream.seekable()` が真かつ `truncate` が使える場合は `seek(data_offset)` + `truncate()` を実行する。それ以外の場合は例外メッセージに使用不能状態である旨を英語で付加する
2. `Mp4FileMuxer` の class docstring に「append_sample が失敗した場合の挙動」を追加 (seekable なら retry 可能、非 seekable なら破棄すること。with 構文の注意含む)
3. README.md の「MP4 ファイルの作成」節に同じ記載を追加
4. `tests/test_mp4.py` に「timescale=0 で失敗 → ストリーム位置と内容が巻き戻る」テスト、「修正後に retry して成功する」テスト、「非 seekable ストリームで使用不能メッセージが付く」テストを追加
5. CHANGES.md の `## develop` に FIX エントリを追記 (shiguredo-changelog スキルの形式に従う)
6. `NO_UV_SYNC=1 uv run pytest tests/` で全テスト通過を確認
