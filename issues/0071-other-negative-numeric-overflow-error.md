# 負値の数値引数が OverflowError になる例外型を統一する

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-negative-numeric-overflow-error
- Polished: {YYYY-MM-DD}

## 目的

数値引数に負値を渡したときに OverflowError になる経路を、他の値域検証 (ValueError) に統一する。例外型の使い分けをユーザーが予測できるようにする。

## 現状

`src/lib.rs` の公開 API では、値域系の検証は `validate_range` / `timescale must be non-zero` 等で `ValueError` に統一されている。一方、PyO3 の型変換で負値を unsigned 型に変換する経路は `OverflowError: can't convert negative int to unsigned` になる:

- `estimate_maximum_moov_box_size(-1, 5)` → OverflowError
- `Mp4MuxSample(timescale=-1)` / `duration=-1` → OverflowError

ユーザー視点では、負値の引数は「不正な値」であり ValueError を期待しやすいが、OverflowError が返るため捕捉し分けが必要になる。

## 設計方針

- 公開 API の各引数について、負値が OverflowError になる経路を洗い出し、ValueError に変換する方針を決める
- 全引数で一貫した例外型になるよう統一する
- 負値のテストを追加する

## 完了条件

- 負値の数値引数が ValueError で報告される
- 既存テストが全通過する
