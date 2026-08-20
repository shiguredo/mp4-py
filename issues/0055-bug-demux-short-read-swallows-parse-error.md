# Demuxer のショートリードでコアのパースエラーが握りつぶされ破損 MP4 が無エラーで通る

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-short-read-error-swallowing
- Polished: 2026-08-20
- Milestone: 2026.2.0

## 目的

`Mp4FileDemuxer` が、moov が途中で切れた破損ファイルを「トラック 0 本の正常終了」として無エラーで処理してしまう経路を解消する。破損データの検出は `Mp4Exception` で報告する方針と矛盾しないようにする。

## 現状

`src/lib.rs` の `Mp4FileDemuxer::feed_required_input` は、ストリームが要求サイズに満たないショートリードを返すと、コアの `handle_input` が `handle_input_error` を設定した後も、バインディング側が `Ok(true)` (真の EOF 到達) を返して正常終了扱いにする。

コア (shiguredo_mp4 2026.4.0) の `Mp4FileDemuxer::handle_input` は、`RequiredInput::is_satisfied_by` が false になる入力 (要求サイズ未満の読み込み) を渡されると `handle_input_error` を設定する (demux_mp4_file.rs)。つまりショートリードの時点でコアは既に回復不能なエラー状態にあるが、バインディングはこれを EOF と誤認する。

ショートリードは ftyp ヘッダの読み込み (ReadFtypBoxHeader フェーズ、32 バイト要求) と moov 以降の読み込みの両方で発生しうる。コアは空読み (0 バイト) でも `is_satisfied_by` が false になり `handle_input_error` を設定するため、単純に「ショートリード = エラー」とすると空ファイルまでエラーになる。この区別が現状のバインディングにはない。

再現手順:

```python
import io
from mp4 import Mp4FileDemuxer

# 有効な ftyp (20 バイト) の後に moov ボックスヘッダ (8 バイト) と
# ボックス本体の一部 (4 バイト) だけがあり、途中で切れた 32 バイトのデータ
data = (
    b"\x00\x00\x00\x14ftypisom\x00\x00\x00\x00isom"
    b"\x00\x00\x00\x18moov"
    b"\x00\x00\x00\x00"
)
demuxer = Mp4FileDemuxer(io.BytesIO(data))
samples = list(demuxer)  # エラーにならず [] が返る
tracks = demuxer.tracks  # []
```

実害: 有効な ftyp を読めたが moov が途中で切れているファイルが「トラック 0 本」としてエラーなく静かに処理される。ユーザーは空ファイルと途中で切れたファイルを例外で区別できない。

## 設計方針

- ショートリードのうち、ftyp ボックスのパース成功後 (moov 以降の読み込み要求) に発生するものだけをエラー化する。判定はバインディング側の `required_input()` が返す `position` で行う (コアはフェーズを公開しないため)。`position` が 0 (ftyp の読み込み) のショートリードは正常終了、`position` が 0 より大きい (moov 以降の読み込み) ショートリードはエラー化する
- ftyp パース前のショートリード (空ファイル・ftyp ヘッダ未満の部分データ) は従来どおり真の EOF として正常終了扱いにする
- エラー化は、ショートリード検知後にコアの `tracks()` / `next_sample()` を再呼び出しして取得する `DemuxError` を `Mp4Exception` 化する。コアの `handle_input_error` は外部クレート (shiguredo_mp4) の private フィールドで直接アクセスできないが、ショートリード後は必ず `Err(DemuxError)` が返るためこれを利用する。エラーメッセージは既存の `map_err` と同じ `mp4 error: ...` 形式に合わせる
- 0053 (破損データ由来エラーの Mp4Exception 統一) が未実装の間は、本 issue のショートリード経路のみ `Mp4Exception` になり、通常のパースエラー経路は `RuntimeError` のままとする。パースエラー全体の例外型統一は 0053 の検討 (0046 の設計と併せて) に委ねる
- README の破損データ挙動の記述を実装と一致するよう更新する

## 完了条件

- moov 途中切れ (ftyp パース成功後のショートリード) が `Mp4Exception` で報告される
- 空ファイル (バイト 0) と 32 バイト未満の部分データ (position 0 のショートリードすべて。ftyp ボックス本体が途中で切れた 8〜31 バイトのデータも含む) は従来どおり「トラック 0 本の正常終了」で通る
- README の記述が実装と一致する
- 上記 2 経路 (moov 途中切れのエラー化・32 バイト未満の正常終了) を固定する回帰テストが追加されている
- 既存テストが全通過する
