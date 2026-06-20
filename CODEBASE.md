# mp4-py

## C/C++

- `make format` でフォーマットすること

## ビルド

- `make develop` でビルドすること

## Python

- Python の命名規則に従うこと
- `pip` を使わず `uv` を使うこと
- `uv run ruff format` でコードをフォーマットすること
- `uv run ruff check` でコードを静的解析すること

### 型アノテーション

- `Optional` ではなく `| None` を使うこと

### Free-Threading

- Free-Threading 環境では GIL は存在しない
- GIL の取得と解放という表現は使わないこと
- nanobind の `gil_scoped_release` は「Python ランタイムからデタッチ」として使用する
- nanobind の `gil_scoped_acquire` は「Python ランタイムにアタッチ」として使用する

### pytest

- モックやスタブは利用禁止
- テストは pytest のみを利用すること
- タスクを完了する前に全てのテストを実行して、全てのテストが通ることを確認すること
- pytest 実行時長くても 60 秒以内にすること
- pytest のタイムアウトは pytest-timeout を利用すること
  - `pytest --timeout=10` のように指定すること
- テスト実行時は `NO_UV_SYNC=1` を指定すること
  - `NO_UV_SYNC=1 uv run pytest` のように指定すること
- テストを削除してテストを通したりしないこと
- テストを無効にしてテストを通したりしないこと
- テストがタイムアウトしたら重大な問題が発生していると考えること
  - デッドロックが発生している可能性がある
- 明確な理由がない限りは try/expect をテストでは利用しないこと
- class を使わないこと
- lambda は使わないで def を使うこと

### hypothesis

- hypothesis の database (.hypothesis/examples/) をクリアしてテストを通すことは禁止
  - database には failing case が保存されている
  - バグを修正すること
