# __version__ が importlib.metadata に強依存し未インストール環境で import が失敗する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-version-metadata-dependency
- Polished: {YYYY-MM-DD}

## 目的

`python/mp4/__init__.py` の `__version__ = version("mp4-py")` が importlib.metadata に強依存しており、パッケージがインストールされていない環境 (ソースツリー直実行など) で `import mp4` 自体が `PackageNotFoundError` で失敗する問題を解消する。

## 現状

`python/mp4/__init__.py` はモジュール読み込み時に `version("mp4-py")` を呼ぶため、ビルド済み拡張モジュールを PYTHONPATH で参照するソースツリー直実行の運用では import 時点で例外になる。`maturin develop` / wheel インストールの公式フローでは動作するため実害は限定的だが、フォールバック (環境変数や例外時の既定値) がない。

## 設計方針

- `version("mp4-py")` の失敗時 (PackageNotFoundError 等) にフォールバックする処理を追加する
- フォールバック値は実装のバージョンと整合するものを選ぶ (例: ソースから取得するか、開発版を示す文字列)

## 完了条件

- 未インストール環境で `import mp4` が成功する
- インストール環境では従来どおり正しいバージョンが返る
- 既存テストが全通過する
