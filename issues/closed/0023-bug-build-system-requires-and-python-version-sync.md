# pyproject.toml build-system.requires と .python-version が README / CHANGES と乖離

- Created: 2026-07-22
- Completed: 2026-07-22
- Branch: feature/fix-build-system-requires-and-python-version-sync
- Polished: {YYYY-MM-DD}

## 目的

以下 2 つのビルド環境設定の乖離を修正する。ビルド環境の再現性に関わる問題であり、CI と開発環境で挙動が食い違う可能性がある。

1. `pyproject.toml:35` の `build-system.requires` が `scikit-build-core` にバージョン下限を指定していない (`CHANGES.md:27` の記載と乖離)。記載と実装が乖離しているのは shiguredo-changelog 規約への実質的な違反である
2. `.python-version` が `3.12` になっており、README の対応バージョン先頭 (`3.14`) と乖離。`.python-version` は開発者ローカルのデフォルト Python 版を決めるため、Free-Threading (`3.14t`) や 3.14 系固有の問題が拾えないリスクがある

## 現状

### 1. build-system.requires

`pyproject.toml:34-36`:
```toml
[build-system]
requires = ["nanobind>=2.13.0", "scikit-build-core"]
build-backend = "scikit_build_core.build"
```

`CHANGES.md:27` に「[UPDATE] scikit-build-core を 0.12.2 以上に上げる」と記載されているが、`build-system.requires` では `scikit-build-core` にバージョン下限指定なし。

`[tool.scikit-build] minimum-version = "0.12.2"` (`pyproject.toml:49`) は scikit-build-core 自身の互換性チェック用であり、PEP 517 レベルのビルドフロントエンド (uv build 等) がバージョンを解決する際は `requires` を参照する。nanobind との対称性が失われている。

### 2. .python-version

`.python-version` の内容:
```
3.12
```

`README.md:34-39` の対応バージョン:
```
- 3.14
- 3.14t
- 3.13
- 3.12
```

開発時のデフォルト Python は 3.12 で、Free-Threading (`3.14t`) や 3.14 系固有の問題を検証できない。CI (`.github/workflows/wheel.yml`) では全バージョンをテストしているが、開発者ローカルで検証されないと PR 単位でリグレッションが混入しやすい。

## 設計方針

### 1. build-system.requires

- `scikit-build-core>=0.12.2` を追加

### 2. .python-version

以下のいずれかを採用する。

#### 方針 A: 3.14 を単一指定

- 対応バージョンの先頭を採用
- Free-Threading は個別に確認が必要

#### 方針 B: 複数行で `3.14t` を含める

`.python-version` は uv では複数行指定可能:
```
3.14t
3.14
3.13
3.12
```

- 全対応版をローカルで検証できる
- ただし `pytest` のデフォルト Python は先頭 (`3.14t`) になる

### 推奨

方針 B。Free-Threading が公式サポートなので、開発者ローカルで常時検証できるようにする。

## 完了条件

- `pyproject.toml:35` の `build-system.requires` に `scikit-build-core>=0.12.2` が指定される
- `.python-version` が `3.14t` (先頭) を含む複数行、または `3.14` に更新される
- CI が全バージョンで通ることを確認
- 開発者ローカルで `uv sync && make develop && make test` が通ることを確認

## 解決方法

1. `pyproject.toml:35` を書き換え:
   ```toml
   requires = ["nanobind>=2.13.0", "scikit-build-core>=0.12.2"]
   ```
2. `.python-version` を書き換え (方針 B):
   ```
   3.14t
   3.14
   3.13
   3.12
   ```
3. `uv sync` で `3.14t` が導入されることを確認
4. `make develop && make test` で全テスト通過を確認
5. `CHANGES.md` の `## develop` セクションに以下を追加:
   ```
   - [UPDATE] build-system.requires に scikit-build-core>=0.12.2 を明記する
     - @voluntas
   - [UPDATE] .python-version に 3.14t を含める
     - @voluntas
   ```

## 対応結果

`scikit-build-core` および `pyproject.toml` の `build-system.requires` は maturin ベースに置き換えたため議論そのものが消滅した。`.python-version` は現状リポジトリに存在しない。よって closed とする。
