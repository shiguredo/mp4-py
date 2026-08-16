# Mp4SampleEntryStpp が null 文字入り入力で Rust panic する

- Priority: High
- Created: 2026-08-15
- Completed: 2026-08-16
- Model: Opus 4.7
- Branch: feature/fix-stpp-panic-on-null-characters
- Polished: 2026-08-15

## 目的

`Mp4SampleEntryStpp` に null 文字を含む `namespace` / `schema_location` / `auxiliary_mime_types` を渡すと、`append_sample` 時に PyO3 経由の Rust panic (PanicException) が発生するバグを解消する。ユーザー入力由来のデータでパニックを起こさず、通常の例外として報告する。

## 優先度根拠

High。

- ユーザー入力で到達可能な Rust panic であり、PyO3 の `PanicException` は `BaseException` のため `except Exception` で捕捉できない (通常の例外と挙動が異なる)
- 同一ファイルの `Mp4TrackMetadata::to_core` は `PyValueError` に正しく変換しており、エラー処理が不整合
- 修正コストは小 (new への検証追加 + テスト)

## 現状

`src/lib.rs` の `Mp4SampleEntryStpp::to_sample_entry` は:

```rust
let namespace =
    Utf8String::new(&self.namespace).expect("namespace must not contain null characters");
```

`schema_location` / `auxiliary_mime_types` も同様の `expect` を持つ (計 3 箇所)。

コア (shiguredo_mp4 2026.4.0) の `Utf8String::new` は null 文字を含む文字列に対して `None` を返すため、この `expect` は panic する。`Mp4SampleEntryStpp::new` は入力検証を行わないため、`Mp4SampleEntryStpp(namespace="a\u0000b")` は構築でき、`append_sample` (内部で `to_sample_entry` が呼ばれる) の時点で panic に達する。

なお、panic は `append_sample` のストリーム write 後に発生するため、既存のロールバック処理も実行されず、write 済みバイトがストリームに残る。例外化すれば seekable なストリームではロールバックが効いて retry 可能になる (既存のロールバック設計と整合)。

null 文字入り入力のテストは存在しない (正規入力のテスト `test_subtitle_sample_entry_stpp` と PBT は固定文字列のみ)。

## 設計方針

- `Mp4SampleEntryStpp::new` で 3 フィールドを検証し、null 文字を含む場合は `PyValueError` を返す (構築時検証)。SampleEntry の値域検証をコンストラクタで行う方針 (SampleEntry コンストラクタの値域検証を扱う別 issue で整備中) と方式を統一する
- `to_sample_entry` の `expect` は維持する。`new` で検証済みであり、`from_box` (demux 側) はデコード経由で null 文字を含み得ない (コアの `Utf8String` は null で読み止める) ため到達しない。コメントでその根拠を明記する
- エラーメッセージは英語で、既存の `Mp4TrackMetadata::to_core` と同じ文言形式 (`... must not contain null characters`) にする

## 完了条件

- `Mp4SampleEntryStpp(namespace="a\u0000b")` の構築時に `ValueError` が発生し、panic しない (3 フィールド全て)
- null 文字を含まない正規の入力は従来どおり動作する
- 追加テストで「3 フィールドそれぞれの null 文字入り入力が ValueError になる」ことを検証する

## 解決方法

1. `src/lib.rs` の `Mp4SampleEntryStpp::new` に 3 フィールド (namespace / schema_location / auxiliary_mime_types) の null 文字検証 (`contains('\0')`) を追加し、`PyValueError` (`... must not contain null characters` 形式) を返すようにした
   - 検証条件はコアの `Utf8String::new` の拒否条件 (null バイト) と完全に一致する
   - エラーメッセージは `Mp4TrackMetadata::to_core` と同じ文言形式
2. `to_sample_entry` の expect にコメントを追記した (new で検証済み、from_box はコアの Utf8String が null で読み止めるため null 文字入りにはならない。いずれの経路でも expect は panic しない)
3. `tests/test_mp4.py` に `test_subtitle_sample_entry_stpp_rejects_null_characters` を追加した:
   - 3 フィールドそれぞれの null 文字入り入力で `ValueError` になることを検証
   - null 文字を含まない正規の入力が従来どおり構築できることを検証 (3 フィールドの getter)
4. CHANGES.md の `## develop` に「[FIX] Mp4SampleEntryStpp の null 文字入り入力で panic しないようにする」を追記した (著者表記 `- @voluntas` 付き、shiguredo-changelog スキルの形式に従う)
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過 (115 passed, 7 skipped) を確認した
