# boxes.rs での panic: スライス範囲外アクセス

## 概要

破損した MP4 データをパースする際、mp4-rust の `src/boxes.rs` で panic が発生する。

## 再現方法

fuzzing テスト (`test_fuzzing_corrupted_mp4`) で max_examples=1000 に設定すると再現する。

## エラーメッセージ

```
thread '<unnamed>' panicked at src/boxes.rs:3004:52:
range end index 22796 out of range for slice of length 12
```

## 原因

`boxes.rs` でサイズをデコードしてからスライスを取得する際、範囲チェックが不足している。

破損データでサイズが巨大な値になると、ペイロード長を超えて範囲外アクセスが発生し panic する。

## 該当箇所

以下の箇所で同様のパターンがある:

```
2435: let sps = payload[offset..offset + size].to_vec();
2447: let pps = payload[offset..offset + size].to_vec();
2474: let sps_ext = payload[offset..offset + size].to_vec();
2734: let nal_unit = payload[offset..offset + nal_unit_length].to_vec();
3004: let codec_initialization_data = payload[offset..offset + codec_init_size].to_vec();
4148: let block_data = buf[offset..offset + length].to_vec();
```

## 修正案

各箇所で範囲チェックを追加:

```rust
// 修正前
let codec_init_size = u16::decode_at(payload, &mut offset)? as usize;
let codec_initialization_data = payload[offset..offset + codec_init_size].to_vec();

// 修正後
let codec_init_size = u16::decode_at(payload, &mut offset)? as usize;
if offset + codec_init_size > payload.len() {
    return Err(Error::invalid_data("codec_initialization_data size exceeds payload"));
}
let codec_initialization_data = payload[offset..offset + codec_init_size].to_vec();
```

または、`get` メソッドを使って安全にスライスを取得:

```rust
let codec_initialization_data = payload
    .get(offset..offset + codec_init_size)
    .ok_or_else(|| Error::invalid_data("codec_initialization_data size exceeds payload"))?
    .to_vec();
```

## 影響

- panic が発生するとプロセス全体が abort する
- Python バインディングでは例外として捕捉できない
- fuzzing テストでプロセスがクラッシュする

## 備考

Rust の FFI 境界では panic は undefined behavior になる可能性があるため、すべてのデコード処理で適切なエラーハンドリングが必要。
