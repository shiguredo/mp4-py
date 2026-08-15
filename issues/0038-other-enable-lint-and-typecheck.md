# ruff の lint ルールがデフォルトのみ + CI に lint / typecheck ジョブがない

- Priority: Medium
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/update-enable-lint-and-typecheck
- Polished: 2026-08-15

## 目的

Python 側の静的解析 (ruff) と型検査 (ty) が実質的に機能していない状態を解消し、CI で常に実行されるようにする。

## 優先度根拠

Medium。

- shiguredo-python スキルの参考設定 (`select = ["E", "W", "F", "I", "B", "UP", "SIM", "C4", "PT", "ANN", "RUF"]`) に未準拠で、型注釈必須 (ANN)・pytest 規約 (PT)・import 順 (I)・PEP 604 (UP) が効いていない
- shiguredo-python スキルは prek の最低要件に `ty check` を含んでおり、prek.toml は ty フックが欠落
- ty が 4 diagnostics を出したままどこでも実行されない
- 修正コストは中 (設定 + 既存違反の修正 + CI ジョブ追加)

## 現状

### ruff のルールがデフォルトのみ

`pyproject.toml` の `[tool.ruff]` は:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
```

`select` が未設定のため、ruff はデフォルトの E4 / E7 / E9 / F のみを有効にする (`uv run ruff check .` は 0 件だが、これはルールが効いていないだけ)。参考設定と同じルールセットで実行すると 114 件検出される:

- ANN201 (関数の戻り値型注釈欠落): `tests/test_mp4.py` に 36 件・`tests/test_free_threading.py` に 7 件 (ANN202 を含めると 12 件)・examples に ANN 系 4 件 (ANN201: demux.py 1 / remux.py 1 / version.py 1、ANN001: demux.py 1)
- RUF002 / RUF003 (コメント内の紛らわしい Unicode 文字): 28 件 (全角括弧「（）」の検出。日本語コメント規約との関係は設計方針参照)
- I001 (import 順): 15 ファイル (bench 2 / examples 1 / tests 12)
- B905 / B017 / B011 / PT011 / PT015 / PT017 / E501 / UP015 / RUF022 / RUF005 / ANN001 / ANN202: 少数ずつ (B017 は `tests/prop_error.py` の assert blind exception、B011 は `tests/test_mp4.py` の assert False で 0039 の担当分)

### ty が診断を出したまま未実行

`uv run ty check` は 4 diagnostics:

- `bench/bench_muxdemux.py` / `bench/bench_parallel.py`: `sys._is_gil_enabled` が Python 3.12 の解決で未定義 (修正は別 issue 0043 で対応。本 issue では扱わない)
- `python/mp4/__init__.py`: `.mp4_ext` の import が解決不能 (拡張モジュール未ビルド起因。ビルド済み環境で解決する)
- `tests/prop_complex.py`: `original_samples` の dict に型注釈がないため `bytes | int` に推論され、`expected_timestamp += original["duration"]` の `+=` がエラー (実行時は正しく動くが型検査不能)

`pyproject.toml` に `[tool.ty]` セクションがなく、wheel.yml に lint / typecheck ジョブが存在しない。prek.toml に ty フックがないため、どこでも実行されない。

### 他 issue との関係 (実装順序)

`python/mp4/__init__.py` の `Union[...]` 使用 (UP007) は別 issue (0024)、`tests/test_mp4.py` の try/except + `assert False` (PT015 / PT017 / B011) は別 issue (0039) が修正を担当しており、本 issue では修正しない。

実装順序は以下に従う (pre-commit フックの制約と ty の診断依存のため):

1. **0043** (bench の `sys._is_gil_enabled` ガード) を先に実装する (ty の 4 diagnostics のうち 2 件が解消する)
2. **本 issue (0038) の前半**: `tests/prop_complex.py` の型注釈修正で ty の診断を解消し、`[tool.ty]` セクションを追加する (この時点で ty check が 0 diagnostics になる。`.mp4_ext` はビルド済み環境で解決)
3. **0024** (Union → `|` 記法) を実装する (ty 診断が解消されているため、0024 の完了条件「`uv run ty check`」が成立する)
4. **0039** (try/except → pytest.raises) を実装する
5. **本 issue (0038) の後半**: ruff select の有効化 + 既存違反の修正 (0024 / 0039 の担当分が消えているため 0 件を達成できる) + lint ジョブの追加 + prek フックの追加

ruff select の有効化は 0024 / 0039 の完了後に回す。prek の ruff-check フック (pre-commit) は有効化後は全ルールで全ファイルを検査するため、担当分の違反が残ったまま有効化するとコミットが弾かれる。同様に prek の ty check フックは ty 診断の解消後に追加する (4 diagnostics のまま追加すると pre-commit が失敗する)。

## 設計方針

- `[tool.ruff.lint]` に参考設定と同じ `select` を設定する
- RUF002 / RUF003 (コメント内の紛らわしい Unicode 文字) は `ignore` に追加する。理由: AGENTS.md の「コメントは全て日本語にすること」と両立させるため (日本語コメントの全角括弧「（）」を違反にすると、日本語コメント規約と衝突する)。off にする理由は pyproject.toml のコメントに残す (shiguredo-python スキルの「off にする rule には必ず理由をコメントで残すこと」に従う)
- 検出される既存違反 (ANN 系・I001・B905・B017 等) は本 issue で修正する (0024 / 0039 の担当分を除く)。修正コストの見積もりとして、tests/ の ANN が 48 件と最多
- `[tool.ty]` セクションを追加する
- ty の診断を解消する: `tests/prop_complex.py` は実修正 (`original_samples` の型注釈は、`duration` が int であることを型レベルで保証できる注釈にする。TypedDict の使用等を検討)、`.mp4_ext` はビルド済み環境での実行で解決、bench 2 件は 0043 の修正後に残る診断があれば per-file の除外設定で対処する
- wheel.yml に lint ジョブを追加する (ruff check / ruff format --check / ty check。ty check は拡張モジュールをビルドした環境で実行する)。push トリガーの paths に `bench/` `examples/` `dev.py` を追加する (現状はこれらの変更で CI が起動しないため)。lint ジョブの追加は 0024 / 0039 の実装後に行う (担当分の違反が残っていると CI がレッドになるため)
- prek.toml に ty check フックを追加する (ビルド済み環境での実行を前提とする)。pytest フックは既存の cargo-test と同様に pre-push で追加する (shiguredo-python スキルの最低要件に含まれる)

## 完了条件

- `uv run ruff check` が参考設定のルールセットで 0 件になる (0024 / 0039 の担当分は、それらの実装後に 0 件になることを確認する)
- `uv run ruff format --check` が 0 件になる
- `uv run ty check` が 0 diagnostics になる (maturin develop 済みの環境で確認する。`.mp4_ext` の import はビルド済み環境で解決される)
- wheel.yml で lint ジョブが実行され、違反があればジョブが失敗する
- prek.toml に ty check フックと pytest フックが追加される
- 既存の全テストが通過する

## 解決方法

実装順序は「他 issue との関係 (実装順序)」セクションに従う。ステップ 1〜5 が本 issue の前半 (0043 の後・0024 / 0039 の前)、ステップ 6〜9 が本 issue の後半 (0024 / 0039 の後) である。

前半:

1. `tests/prop_complex.py` の `original_samples` に、`duration` が int であることを型レベルで保証できる型注釈を追加して ty の診断を解消する
2. `pyproject.toml` に `[tool.ty]` セクションを追加する
3. bench の `sys._is_gil_enabled` は別 issue (0043) で対応する (実装順序で先行)。0043 の修正後に ty の診断が残る場合は per-file の除外設定で対処する

後半 (0024 / 0039 の実装後):

4. `pyproject.toml` の `[tool.ruff]` に `[tool.ruff.lint]` を追加し、`select` を設定する。RUF002 / RUF003 は理由コメント付きで `ignore` に追加する
5. 検出された既存違反を修正する (tests/ の型注釈、examples の型注釈、import 順、B905、B017 等。`__init__.py` の Union は 0024、test_mp4.py の try/except は 0039 の担当のため既に解消されている)
6. wheel.yml に lint ジョブを追加し (ruff check / ruff format --check / ty check。ty check はビルド後環境で実行)、push トリガーの paths に `bench/` `examples/` `dev.py` を追加する
7. prek.toml に ty check フック (pre-commit) と pytest フック (pre-push、cargo-test と同様) を追加する
8. CHANGES.md の `### misc` に追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
9. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
