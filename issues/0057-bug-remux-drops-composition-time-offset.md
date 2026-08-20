# remux サンプルプログラムが composition_time_offset を引き継がず A/V 同期が崩れる

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/fix-remux-composition-time-offset
- Polished: 2026-08-20
- Milestone: 2026.2.0

## 目的

`examples/remux.py` が ctts (composition time offset) を持つコンテンツ (B フレーム入り H.264 等) をリマルチプレックスする際、composition time offset が黙って失われる不具合を解消する。サンプルプログラムの目的 (「すべてのサンプルを新しい MP4 ファイルに書き直す」) に対してデータ影響のある欠落である。

## 現状

`examples/remux.py` の `Mp4MuxSample` 構築は `duration` と `data` までしか渡しておらず、`composition_time_offset` を引き継いでいない。

`Mp4DemuxSample` は `composition_time_offset` を公開しており、`Mp4MuxSample` も `composition_time_offset` 引数を受け付ける (2026.2.0 で追加) ため、引き継ぎは実装可能な状態にある。

実害: MP4 では PTS は直接格納されず PTS = DTS + composition_time_offset で導出される。B フレームを持つ H.264 等を remux すると ctts が失われ、派生する PTS が DTS に縮退して A/V 同期が崩れた出力ファイルが生成される。

## 設計方針

- `Mp4MuxSample` 構築時に `composition_time_offset=sample.composition_time_offset` を渡す
- `examples/remux.py` のデマクサーからマルチプレクサーへの変換ループを関数 (例: `remux(demuxer, muxer)`) に抽出し、`main()` とテストの双方が同じ関数を呼ぶ構成にする。テストは `examples/remux.py` から抽出関数を import して駆動し、修正箇所 (composition_time_offset の引き継ぎ) そのものを検証できるようにする。`examples/` はパッケージではないため、pytest から `import remux` できるよう `pyproject.toml` の `[tool.pytest.ini_options]` に `pythonpath = ["examples"]` を追加する (`from examples.remux import remux` は成立しない。`import remux` の形式になる)
- 既存の mux → demux テスト `test_mux_demux_roundtrip_with_composition_time_offset` (tests/test_mp4.py) を書き換えず、別テストとして remux (mux → demux → mux → demux) の roundtrip で composition time offset が保持されることを検証するテストを追加する。既存テストは mux → demux 単独の検証を担い、新テストは remux 経路の検証を担う
- テストの offset 値は正値だけでなく負値 (ctts version 1) も 1 件含め、version 1 経路の引き継ぎも固定する

## 完了条件

- remux 後も composition_time_offset が保持される (抽出した remux 関数を呼ぶテストで検証される)
- 既存テストが全通過する
