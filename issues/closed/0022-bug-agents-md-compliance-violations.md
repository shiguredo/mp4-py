# AGENTS.md / CODEBASE.md 規約違反 3 件を一括で修正 (issues 参照 / Optional / NO_UV_SYNC)

- Priority: High
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/fix-agents-md-compliance-violations
- Polished: {YYYY-MM-DD}

## 目的

以下の 3 つの規約違反を一括で修正する。いずれも変更対象は独立しているが、修正内容が「規約違反の是正」で単純なため 1 issue にまとめる。

1. `src/mp4_ext.cpp:947` が存在しない issue ファイル `issues/infinite-loop-with-corrupted-mp4.md` を参照している (shiguredo-issues 規約違反)
2. `dev.py:3, 7, 89` で `Optional` を使用している (`CODEBASE.md:20` 「`Optional` ではなく `| None` を使う」規約違反)
3. `Makefile` の `test` ターゲットに `NO_UV_SYNC=1` が抜けている (`CODEBASE.md:37-38` 規約違反)

## 優先度根拠

High。

- 3 つとも AGENTS.md / CODEBASE.md の明文規約違反。「一切妥協をしないこと」に反する。
- `mp4_ext.cpp:947` の issue 参照は `issues/` ディレクトリが存在しない (`81dd524` で削除された) にも関わらずコメントが残っており、経緯を追跡できない状態。`AGENTS.md`「Don't live with broken windows」にも該当。
- 修正コストは各項目 1〜数行の変更のみ。

## 現状

### 1. mp4_ext.cpp が存在しない issue ファイルを参照

`src/mp4_ext.cpp:947`:
```cpp
//   詳細は issues/infinite-loop-with-corrupted-mp4.md を参照。
```

`issues/` ディレクトリはリポジトリに存在しない (この issue の作成でようやく再生成される)。shiguredo-issues 規約「ソースコード本体・コメント等に issue ファイル名を残さない」に違反。

### 2. dev.py の Optional 使用

`dev.py:3`:
```python
from typing import Optional
```

`dev.py:7`:
```python
def update_version(file_path: str, dry_run: bool) -> Optional[str]:
```

`dev.py:89`:
```python
new_version: Optional[str] = update_version(version_file_path, args.dry_run)
```

`CODEBASE.md:20`「型アノテーション: `Optional` ではなく `| None` を使うこと」に違反。

### 3. Makefile の NO_UV_SYNC 抜け

`Makefile` の `test:` ターゲット:
```makefile
test: develop
	uv run pytest tests/ --timeout=10
```

`CODEBASE.md:37-38`「テスト実行時は `NO_UV_SYNC=1` を指定すること」「`NO_UV_SYNC=1 uv run pytest` のように指定すること」に違反。`.github/workflows/wheel.yml` は 3 箇所で `NO_UV_SYNC: 1` を指定しており、Makefile だけが規約に反している。

## 設計方針

3 件とも独立した単純修正なので、1 コミット (または関連する 3 コミット) でまとめて対応する。

- mp4_ext.cpp:947: コメント行を削除、あるいは mp4-rust 側の GitHub Issue URL / コミットハッシュに置き換え (後述)
- dev.py: `Optional[str]` → `str | None`、`from typing import Optional` を削除
- Makefile: `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10`

## 完了条件

- `src/mp4_ext.cpp:947` から `issues/infinite-loop-with-corrupted-mp4.md` への参照が削除される
- `dev.py` の `Optional` が使われなくなる (`from typing import Optional` も削除)
- `Makefile:test` に `NO_UV_SYNC=1` が付く
- `make test` で `NO_UV_SYNC=1 uv run pytest` が実行され、全テスト通過

## 解決方法

### 1. mp4_ext.cpp の issue 参照削除

`src/mp4_ext.cpp:944-948` のコメントブロック:
```cpp
// 本来の修正箇所:
//   mp4-rust 側で同じ入力要求が繰り返されたらエラーにすべき。
//   詳細は issues/infinite-loop-with-corrupted-mp4.md を参照。
```

以下に置き換え:
```cpp
// 本来の修正箇所:
//   mp4-rust 側で同じ入力要求が繰り返されたらエラーにすべき。
//   (upstream: mp4-rust)
```

または upstream の GitHub Issue URL が存在するならそれに置き換える (要確認)。

### 2. dev.py の Optional 修正

```python
# Before
from typing import Optional

def update_version(file_path: str, dry_run: bool) -> Optional[str]:
    ...

new_version: Optional[str] = update_version(version_file_path, args.dry_run)

# After
def update_version(file_path: str, dry_run: bool) -> str | None:
    ...

new_version: str | None = update_version(version_file_path, args.dry_run)
```

`from typing import Optional` は削除。他に typing の import が必要なければ import 文自体を削除。

### 3. Makefile 修正

`Makefile:test:` ターゲット:
```makefile
test: develop
	NO_UV_SYNC=1 uv run pytest tests/ --timeout=10
```

## コミット構成の推奨

1 issue = 1 branch (`feature/fix-agents-md-compliance-violations`) 上で、以下の 3 コミットに分割:

1. `fix(cpp): mp4_ext.cpp から存在しない issues/ 参照を削除する`
2. `fix(dev): dev.py の Optional を | None に置き換える`
3. `fix(build): Makefile test ターゲットに NO_UV_SYNC=1 を追加する`

または単一コミット `fix: AGENTS.md 規約違反 3 件を修正する` にまとめても可 (shiguredo-git スキルで判断)。

## 対応結果

3 件全て解消済み: (1) `src/mp4_ext.cpp` そのものが削除された (2) `dev.py` は Cargo.toml 対応の版に置き換えられ Optional 表記は残っていない (3) `Makefile` そのものが削除された。よって closed とする。
