# duration=0 サンプルの受理可否を明確にする

- Created: 2026-08-19
- Completed: {YYYY-MM-DD}
- Branch: feature/other-duration-zero-sample
- Polished: {YYYY-MM-DD}

## 目的

`Mp4MuxSample(duration=0)` を黙って受理して stts に delta 0 のエントリを書く挙動について、仕様判断を行い、方針を確定する。多くのプレイヤーで再生不能な出力の原因になり得るため、許可するなら明示し、拒否するならコンストラクタで検証する。

## 現状

`Mp4MuxSample::new` (src/lib.rs) は `duration` を u32 で受け取り、0 を受理する。コア (shiguredo_mp4 2026.4.0) も 0 を許容する設計のため、stts に delta 0 のエントリが書かれる。

conftest.py の `st_duration` は min 1 のため PBT では 0 が検証されない。timescale=0 はコンストラクタで弾く (issue 0013 で対応済み) のに、duration=0 は弾いていない非対称がある。

## 設計方針

- duration=0 を拒否する場合は `ValueError` で弾く (timescale=0 と同様のコンストラクタ検証)
- 許可する場合はドキュメントとテストで明示する
- コア側の設計意図 (許容する理由) を確認してから方針を決める

## 完了条件

- duration=0 の扱いが決まり、テストとドキュメントで固定される
- 既存テストが全通過する
