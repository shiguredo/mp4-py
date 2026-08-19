# Demuxer のショートリードでコアのパースエラーが握りつぶされ破損 MP4 が無エラーで通る

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-short-read-error-swallowing
- Polished: {YYYY-MM-DD}
- Milestone: 2026.2.0

## 目的

`Mp4FileDemuxer` が、moov が途中で切れた破損ファイルを「トラック 0 本の正常終了」として無エラーで処理してしまう経路を解消する。破損データの検出は `Mp4Exception` で報告する方針と矛盾しないようにする。

## 現状

`src/lib.rs` の `Mp4FileDemuxer::feed_required_input` は、ストリームが要求サイズに満たないショートリードを返すと、コアの `handle_input` が `handle_input_error` を設定した後も、バインディング側が `Ok(true)` (真の EOF 到達) を返して正常終了扱いにする。

コア (shiguredo_mp4 2026.4.0) の `Mp4FileDemuxer::handle_input` は、`RequiredInput::is_satisfied_by` が false になる入力 (要求サイズ未満の読み込み) を渡されると `handle_input_error` を設定する (demux_mp4_file.rs)。つまりショートリードの時点でコアは既に回復不能なエラー状態にあるが、バインディングはこれを EOF と誤認する。

実害: 有効な ftyp を読めたが moov が途中で切れているファイルが「トラック 0 本」としてエラーなく静かに処理される。ユーザーは空ファイルと途中で切れたファイルを例外で区別できない。

## 設計方針

- ショートリード時にコアの `handle_input_error` を取り出して `Mp4Exception` 化する経路を追加する
- 破損データ検出の型分類 (issue 0053 で検討中のパースエラー一律 `Mp4Exception` 化) と整合する形で実装する
- 真の EOF (サイズ 0 の読み込み) との区別を明確にする

## 完了条件

- moov 途中で切れた破損ファイルが `Mp4Exception` で報告される
- 空ファイル (バイト 0) は従来どおり「トラック 0 本の正常終了」で通る
- 既存テストが全通過する
