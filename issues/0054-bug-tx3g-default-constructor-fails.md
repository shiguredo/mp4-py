# Mp4SampleEntryTx3g がデフォルト引数でコンストラクタ失敗する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-tx3g-default-constructor
- Polished: 2026-08-20
- Milestone: 2026.2.0

## 目的

2026.2.0 で新規公開する `Mp4SampleEntryTx3g` が、デフォルト引数を使った呼び出しで必ず `ValueError` になる不具合を解消する。引数省略時の既定値で字幕トラックを mux できるようにする。

## 現状

`src/lib.rs` の `Mp4SampleEntryTx3g::new` は `background_color_rgba` のデフォルトを `None` としているが、`unwrap_or_default()` で空の `Vec` に展開される。直後に 4 バイト長チェックがあるため、引数省略時は必ず `ValueError: background_color_rgba must be exactly 4 bytes` になる。

再現手順:

```python
from mp4 import Mp4SampleEntryTx3g

entry = Mp4SampleEntryTx3g()  # ValueError が発生する
```

同コンストラクタの `default_text_box` / `default_style` は `unwrap_or` で適切な既定値を持ち、`font_table` は `unwrap_or_default()` でも空 `Vec` が妥当な既定値のため、`background_color_rgba` のみが 4 バイトを満たさない空 `Vec` に展開されて破損している。

テスト (`tests/conftest.py` の `st_tx3g_sample_entry`) は常に明示的に 4 バイトを渡すため、PBT ではこの経路は決して実行されない。

## 設計方針

- `background_color_rgba` の既定値を 4 バイトの初期値 (`vec![0, 0, 0, 0]`) にする。透明背景 (RGBA 全ゼロ) は既存テスト `test_subtitle_sample_entry_tx3g` が `b"\x00\x00\x00\x00"` を使用しており、`default_style` のテキスト色既定とも整合する
- `tests/test_mp4.py` に Tx3g の既定値経路を固定する単体テストを追加する (構築 + mux → demux ラウンドトリップを含む)
- 他 SampleEntry コンストラクタのデフォルト引数経路の包括的な固定テストは 0066 のスコープのため、本 issue では Tx3g 単体に限定する

## 完了条件

- `Mp4SampleEntryTx3g()` がエラーなく構築できる
- 既定値で構築したエントリで mux → demux が成功する
- `tests/test_mp4.py` に Tx3g のデフォルト引数経路を検証するテストが追加されている
