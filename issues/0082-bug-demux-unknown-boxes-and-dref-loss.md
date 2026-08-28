# demux した SampleEntry の unknown_boxes と data_reference_index が remux で黙って失われる

- Created: 2026-08-29
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-unknown-boxes-and-dref-loss
- Polished: {YYYY-MM-DD}

## 目的

外部 MP4 を demux して remux したときに、型付きの子ボックスとして扱われない子ボックスと `data_reference_index` が無言で失われる経路を解消する。無言の劣化をなくすか、非対応であることを明示的に検出する。

## 現状

`src/lib.rs` の各 SampleEntry の `to_sample_entry` は、コア側の `unknown_boxes` を常に `Vec::new()` で再構築している (Vp08 / Vp09 / Avc1 / Hev1 / Hvc1 / Av01 / Opus / Mp4a / Flac / Stpp / Wvtt / Tx3g の全箇所)。逆に `from_box` はコアが復元した `b.unknown_boxes` を参照しない。

コア (`shiguredo_mp4`) 側はデコード時に、型付きの子ボックスとして扱わないものを `unknown_boxes` に集約する。たとえば `Tx3gBox::decode` は `FtabBox::TYPE` に一致しない子ボックスをすべて `unknown_boxes` へ入れ、`StppBox` / `WvttBox` の doc にも「型付き実装を持たない任意の子ボックス (`btrt` / `m4ds` 等)」が保持される旨が書かれている。つまり demux の時点でバインディング側に情報が届いていない。

`data_reference_index` も同様に、`to_sample_entry` は各ボックスの `DEFAULT_DATA_REFERENCE_INDEX` を常に書き、`from_box` は入力値を読まない。

Python 側の SampleEntry クラスに `unknown_boxes` / `data_reference_index` を読む公開属性・getter は存在しないため、利用者側で退避してから書き戻すこともできない。

デマクサー経由のデータ劣化としては「demux 経由のデータ劣化 (channelcount 切り詰め / Flac ブロック種別 / HEVC array_completeness / avc1 sps_ext) を解消する」issue が open だが、あちらは個別フィールドの喪失が対象で、本 issue の全クラス共通の `unknown_boxes` と `data_reference_index` の喪失は含まれていない。

## 設計方針

- 各項目について、値を公開して引き継ぐか、非対応であることを明示的に検出してエラーにするかを判断する
- 引き継ぐ場合、子ボックスの再シリアライズはコアがバイト列を保持しているかどうかに依存するため、コア側の `UnknownBox` が保持する内容を先に確認する
- `data_reference_index` を引き継ぐ場合は、コアの muxer が常にローカルファイルの `dref` を書く点との整合を議論する (入力側が別の `dref` を指している場合に値だけ不整合になり得る)
- 公開フィールドの追加は ADD、検出の追加はバグ修正として扱い、変更履歴の種別を分ける

## 完了条件

- `unknown_boxes` と `data_reference_index` について、保持するか明示的に検出するかの方針が決定し、実装されている
- 失われるままにする場合、そのことが失われないことを検証するテストまたはエラーとして表面化している
- 既存テストが全通過する
