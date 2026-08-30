# demux した SampleEntry の unknown_boxes と data_reference_index が remux で黙って失われる

- Created: 2026-08-29
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-demux-unknown-boxes-and-dref-loss
- Polished: 2026-08-30

## 目的

外部 MP4 を demux して remux したときに、型付きの子ボックスとして扱われない子ボックスと `data_reference_index` が無言で失われる経路を解消する。無言の劣化をなくすか、非対応であることを明示的に検出する。

## 現状

`src/lib.rs` の各 SampleEntry の `to_sample_entry` は、コア側の `unknown_boxes` を常に `Vec::new()` で再構築している (Vp08 / Vp09 / Avc1 / Hev1 / Hvc1 / Av01 / Opus / Mp4a / Flac / Stpp / Wvtt / Tx3g の全箇所)。逆に `from_box` はコアが復元した `b.unknown_boxes` を参照しない。

コア (`shiguredo_mp4`) 側はデコード時に、型付きの子ボックスとして扱わないものを `unknown_boxes` に集約する。たとえば `Tx3gBox::decode` は `FtabBox::TYPE` に一致しない子ボックスをすべて `unknown_boxes` へ入れ、`StppBox` / `WvttBox` の doc にも「型付き実装を持たない任意の子ボックス (`btrt` / `m4ds` 等)」が保持される旨が書かれている。つまり demux の時点でバインディング側に情報が届いていない。

`data_reference_index` も同様に、`to_sample_entry` は各ボックスの `DEFAULT_DATA_REFERENCE_INDEX` を常に書き、`from_box` は入力値を読まない。

Python 側の SampleEntry クラスに `unknown_boxes` / `data_reference_index` を読む公開属性・getter は存在しないため、利用者側で退避してから書き戻すこともできない。

デマクサー経由のデータ劣化としては「demux 経由のデータ劣化 (channelcount 切り詰め / HEVC array_completeness / avc1 sps_ext) を解消する」issue が open だが、あちらは個別フィールドの喪失が対象で、本 issue の全クラス共通の `unknown_boxes` と `data_reference_index` の喪失は含まれていない。

## 設計方針

各項目の扱いを次のとおり決定する。判断基準は、保持して引き継げるものは保持し (変更履歴の種別は ADD)、保持すると不正な出力になるものは非対応として明示的に検出してエラーにする (変更履歴の種別は FIX) とする。demux 経路 (`from_box`) は入力データ由来の値をそのまま保持する既存方針に従う。

- **unknown_boxes**: 保持して引き継ぐ (ADD)。コアの `UnknownBox` は `box_type` / `box_size` / `payload` (バイト列) を保持しており、`Encode::encode_to_vec` でシリアライズし `UnknownBox::decode` で復元できるため、バイト列のまま無劣化で往復できる。各 SampleEntry クラスに `unknown_boxes` (シリアライズ済み子ボックスの `list[bytes]`) を公開属性として追加し、コンストラクタ引数 (既定は空リスト) で受け取り、`from_box` で `b.unknown_boxes` を保持して `to_sample_entry` で引き継ぐ。構築時に `UnknownBox::decode` で復元できることを検証し、不正なバイト列は `ValueError` にする。未知ボックス (btrt / m4ds / vlab / dprp 等) は実ファイルに普通に存在し得るため、検出してエラーにすると合法な入力の demux / remux を壊す。保持が適切である
- **data_reference_index**: 非 1 を検出してエラーにする (FIX)。コアの muxer は常に `DinfBox::LOCAL_FILE` (1 エントリー、index 1) を書くため、非 1 の値を引き継ぐと出力の `dref` に存在しないエントリーを指す不正なファイルになる。引き継ぎはできない。dref=1 (ローカルファイル参照) は muxer が常に書くため引き継ぎの必要がない。`from_box` (demux 経路) で `data_reference_index` が 1 以外のとき `Mp4Exception` を返す

## 完了条件

- `unknown_boxes` が各 SampleEntry で demux → remux の roundtrip で失われず引き継がれる (roundtrip テストで検証)
- `data_reference_index` が 1 以外の SampleEntry を含む入力が demux で `Mp4Exception` になる (エラーテストで検証)
- 既存テストが全通過する
