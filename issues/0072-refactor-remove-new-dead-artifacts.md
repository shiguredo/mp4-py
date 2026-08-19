# 新規に検出した残骸コードと冗長な記述を削除する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/refactor-remove-new-dead-artifacts
- Polished: {YYYY-MM-DD}

## 目的

コードベース内に残る死にコード・無意味な記述を削除し、可読性を高める。issue 0040 (open) の対象 (`.clang-format` 残骸、nanobind 言及コメント、`let _ = py;`、MuxerState の Option) は 0040 に委ね、本 issue は新規に検出されたもののみを扱う。

## 現状

新規に検出した削除候補:

1. `.github/workflows/wheel.yml` の `wc -l release_files.txt` — 出力がログに残るだけで後のステップに渡らず、動作に寄与しないデバッグ出力
2. `dev.py` の `git add uv.lock` — `[tool.uv] package = false` のためバージョン bump では uv.lock が変化せず、実質 no-op
3. `examples/demux.py` の `get_sample_entry_description` 内の関数内 import — 遅延 import の理由が見当たらず、ファイル冒頭に移せる
4. `tests/prop_moov_size.py` の `assert size >= 0` — `estimate_maximum_moov_box_size` が `usize` を返すため常に真
5. `tests/prop_error.py` の `assert isinstance(samples, list)` — `list(demuxer)` の結果が list であることは自明
6. `tests/prop_edge_cases.py` の `@given` なし非 PBT 関数 (prop_minimum_sample_size 等) — pyproject.toml の「prop_ prefix は PBT に使用」規約と不整合。`test_` prefix へ移すか PBT 化する
7. `examples/remux.py` の「マルチプレックサー」等の用語タイポ — 表記ゆれの統一

## 設計方針

- 各候補を削除・整理する。テストの機能を損なわないこと (削除する assert が実質的な検証でないことを確認してから)
- 残骸の削除と同時に、用語・表記の統一も行う (ドキュメント類は issue 0041 と重複しない範囲に留める)

## 完了条件

- 上記の削除候補が削除・整理される
- 既存テストが全通過する
