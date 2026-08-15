# ドキュメント・コメントの表記と規約違反を修正する

- Priority: Low
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/update-documentation-and-comment-issues
- Polished: 2026-08-15

## 目的

README / CHANGES / ソースコードのコメント・docstring・メッセージに残る表記誤りと規約違反 (全角半角間スペース、コメント言語、ドキュメントと実装の食い違い、エラーメッセージ言語) を一括修正する。

## 優先度根拠

Low。

- 機能への影響はゼロの表記修正のみ
- 修正コストは小〜中 (複数ファイルの横断修正)

## 現状

### README.md

- 「10フレームごとにキーフレーム」: 全角と半角の間に半角スペースがない (AGENTS.md 規約違反)
- テスト実行手順 (`uv run pytest tests/ --timeout=30`) が CODEBASE.md の実行規約 (`NO_UV_SYNC=1` 必須、`--timeout=10` 例) と不整合
- 「mp4-rust」表記 2 箇所 (リンクとライセンス見出し): リポジトリの実体は shiguredo/mp4-rs (2026.2.0 以降にリネーム済み)。リンク行 (21 行目) には全角句点の後に半角スペースがある (shiguredo-doc スキルの「全角句読点の前後に半角スペースを入れないこと」違反) ため併せて修正する

### CHANGES.md

- 「**リリース日**:: 2026-01-07」のコロン 2 つは shiguredo-changelog 規約 (1 つ) に反するが、リリース済み 2026.1.0 セクションの記述であり、shiguredo-doc スキルの「旧文書の扱い」(過去のリリースノートは表記揺れがあってもそのまま残すこと) に従い修正しない
- 「`Mp4FileMuxerOptions.reserved_moov_box_size` を `uint32` で受け取るようにする」エントリ: C API 時代の残骸であり、現実装 (Rust クレート直接バインド、`reserved_moov_box_size: usize`) には該当する変更が存在しないため、エントリ自体を削除する (closed 0015 の対応結果で C API 型整合性の議論は解消済み)
- 「mp4-rust を 2026.4.0 に上げる」エントリ (2026.4.0 追従): 実体のリポジトリ名 (mp4-rs) に統一する

### ソースコード

- `src/lib.rs` のコメント「9 種の SampleEntry」2 箇所 (`Mp4SampleEntryAny` 定義部と `Mp4MuxSample` 定義部): 字幕 3 種 (Stpp / Wvtt / Tx3g) 追加後も 12 種になっていない
- `src/lib.rs` の「PyO3 0.29 では PyBuffer 経由でゼロ経路が短くなる」: 「ゼロ経路」は意味不明な表現。修正文言は実装の経路 (PyBuffer 経由の変換処理) を確認して正確な表現にする
- `src/lib.rs` のセクション見出し「Mp4FileDemuxer (on-demand loading)」: 英語コメント (他セクションは「(遅延読み込み対応)」と日本語化済み)
- `tests/test_mp4.py` の英語コメント 20 箇所 (SPS / PPS の説明文 205 / 228、プロファイル・レベルの注記 234 / 235 / 271 / 272 / 305 / 306 / 339 / 340、SPS ラベル 273 / 307、AAC-LC の説明 445、ビット配置の説明 489 / 491 / 494 / 497 / 500 / 505、MD5 シグネチャの注記 513): AGENTS.md「コメントは全て日本語にすること」違反。技術用語は日本語文に組み込んで日本語化する
- `tests/test_free_threading.py` のスキップ理由に「Python 3.13t」を例示: CHANGES.md で 3.13t 非対応と明記されており誤解を招く (例示を 3.14t のみに修正する)。同ファイルのコメントに「mp4-rust」表記 2 箇所も残る (mp4-rs に統一)
- `tests/test_free_threading.py` の docstring に `uv run -p 3.14t pytest ...` の実行例: `NO_UV_SYNC=1` と `--timeout=10` の指定がない (CODEBASE.md 規約と不整合)
- `build.rs` の `expect` メッセージ 2 箇所が日本語: エラーメッセージは英語にすること (AGENTS.md) 違反
- `python/mp4/__init__.py` の docstring が英語

### その他

- `examples/version.py` の print 出力が日本語 (ログメッセージは英語にすること: shiguredo-python スキル) と「mp4-rust」表記
- `dev.py` のエラーメッセージ 2 箇所が日本語、argparse のヘルプ文言も日本語 (英語にすること)
- `examples/demux.py:135` と `tests/test_mp4.py:67` のコメントに全角半角間スペース違反

なお、`tests/` のテスト内 assert メッセージの言語 (テストのログメッセージは日本語にすること) は本 issue の対象外とする (英語の assert メッセージが多数残存するため、一括修正は別途検討する)。

## 設計方針

- 表記誤りは該当ファイルを直接修正する (ドキュメントとコメント・メッセージのみ、ロジックは変更しない)
- リポジトリ名は実体 (mp4-rs) に統一する (README / CHANGES.md / examples/version.py / tests/test_free_threading.py のコメント)
- README のコード例の消滅 API 参照には変更を加えない (消滅 API 参照の修正は別 issue 0027 の担当。コード例内コメントの表記修正 (96 行目の全角半角等) は本 issue の対象)

## 完了条件

- 上記の全項目が修正される
- コード動作に変更がない (全テスト通過)
- CHANGES.md の `### misc` に追記する

## 解決方法

1. `README.md` の表記・リンク・テスト手順を修正する
2. `CHANGES.md` の `reserved_moov_box_size` のエントリを削除し、mp4-rust 表記を mp4-rs に統一する (リリース済みセクションの「**リリース日**::」は旧文書の扱いにより修正しない)
3. `src/lib.rs` / `tests/test_mp4.py` / `tests/test_free_threading.py` / `build.rs` / `python/mp4/__init__.py` / `examples/version.py` / `examples/demux.py` / `dev.py` のコメント・メッセージを修正する
4. CHANGES.md の `### misc` に「[UPDATE] ドキュメント・コメントの表記と規約違反を修正する」を追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
5. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
