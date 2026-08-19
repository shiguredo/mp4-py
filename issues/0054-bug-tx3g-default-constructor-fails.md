# Mp4SampleEntryTx3g がデフォルト引数でコンストラクタ失敗する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-tx3g-default-constructor
- Polished: {YYYY-MM-DD}

## 目的

2026.2.0 で新規公開する `Mp4SampleEntryTx3g` が、デフォルト引数を使った呼び出しで必ず `ValueError` になる不具合を解消する。引数省略時の既定値で字幕トラックを mux できるようにする。

## 現状

`src/lib.rs` の `Mp4SampleEntryTx3g::new` は `background_color_rgba` のデフォルトを `None` としているが、`unwrap_or_default()` で空の `Vec` に展開される。直後に 4 バイト長チェックがあるため、引数省略時は必ず `ValueError: background_color_rgba must be exactly 4 bytes` になる。

再現手順:

```python
from mp4 import Mp4SampleEntryTx3g

entry = Mp4SampleEntryTx3g()  # ValueError が発生する
```

同コンストラクタの `default_text_box` / `default_style` / `font_table` は正しい既定値 (`unwrap_or((0, 0, 0, 0))` 等) を持つため、`background_color_rgba` のみが破損している。

テスト (`tests/conftest.py` の `st_tx3g_sample_entry`) は常に明示的に 4 バイトを渡すため、PBT ではこの経路は決して実行されない。

## 設計方針

- `background_color_rgba` の既定値を 4 バイトの初期値 (`vec![0, 0, 0, 0]` 相当) にする
- 既定値経路を固定する特性化テストを追加する (他の SampleEntry コンストラクタのデフォルト引数経路も同様に未テストのため、あわせて確認する)

## 完了条件

- `Mp4SampleEntryTx3g()` がエラーなく構築できる
- 既定値で構築したエントリで mux → demux が成功する
- デフォルト引数経路を検証するテストが追加されている
