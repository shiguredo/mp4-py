# Muxer / Demuxer のデストラクタ・コンストラクタで例外が漏れリソースが破壊される

- Priority: High
- Created: 2026-07-22
- Completed: 2026-07-22
- Model: Opus 4.7
- Branch: feature/fix-nanobind-lifecycle-exception-safety
- Polished: {YYYY-MM-DD}

## 目的

nanobind ラッパーである `PyMp4FileMuxer` / `PyMp4FileDemuxer` のライフサイクル管理で以下 2 系統の欠陥を解消する。

1. デストラクタから C++ 例外が漏れて `std::terminate` を招く経路がある
2. コンストラクタで生ポインタ `muxer_` / `demuxer_` を確保した後に例外が発生すると解放漏れ (メモリリーク) が起きる

Python 側の `with` 文でハンドリングされずに GC 経由で `__del__` が呼ばれた場合や、コンストラクタ中の I/O エラー・破損データ検出時に、プロセスが `abort()` する / mp4-rust 側のリソースが取り残される事象を防止する。

## 優先度根拠

High。

- デストラクタから例外が漏れると **C++11 以降のデフォルトである `noexcept(true)` に反し `std::terminate` 直行**。ユーザーアプリケーションが単なる `RuntimeError` を期待しているだけで、プロセスごと落ちる。
- 一度失敗した Muxer を GC が回収するタイミングでプロセスが落ちるため、原因究明が困難。
- コンストラクタ側のリークは、Muxer 初期化失敗を再試行するアプリケーションで累積するとプロセスメモリを圧迫する。
- 実装は既存の `close()` / `finalize_internal()` を変更するだけで完結し、影響範囲が nanobind ラッパー内に閉じる。

## 現状

### 1. デストラクタから例外が漏れる経路

`src/mp4_ext.cpp:1429` で `~PyMp4FileMuxer()` は `close()` を呼ぶ。`close()` は `finalized_ == false` の場合 `finalize_internal()` (`src/mp4_ext.cpp:1502-1513`) を呼び出し、その中で `mp4_file_muxer_finalize()` の戻り値を `check_error()` に渡す。

```cpp
void finalize_internal() {
  if (closed_)
    throw Mp4Exception("Muxer is closed");
  if (finalized_)
    return;

  Mp4Error error = mp4_file_muxer_finalize(muxer_);
  check_error(error);  // ← Mp4Exception / std::invalid_argument を throw する可能性
  finalized_ = true;

  flush_output();      // ← output_stream_.attr("seek") / attr("write") が Python 例外を投げる可能性
}
```

同じ `close()` 内で `output_stream_.attr("close")()` (1453 行) も Python 例外を投げうる。

`src/mp4_ext.cpp:786` の `~PyMp4FileDemuxer()` も同様に `close()` → `input_stream_.attr("close")()` (807 行) が Python 例外を投げる可能性がある。

### 2. コンストラクタで生ポインタがリークする

`src/mp4_ext.cpp:1409-1427` の `PyMp4FileMuxer` コンストラクタは以下の流れで動く。

```cpp
muxer_ = mp4_file_muxer_new();
if (!muxer_) {
  throw Mp4Exception("Failed to create mp4 muxer");
}

if (options && options->reserved_moov_box_size > 0) {
  Mp4Error error = mp4_file_muxer_set_reserved_moov_box_size(
      muxer_, options->reserved_moov_box_size);
  check_error(error);   // ← throw されると muxer_ が解放されない
}

Mp4Error error = mp4_file_muxer_initialize(muxer_);
check_error(error);      // ← 同上

flush_output();          // ← Python 例外・muxer エラーで同上
```

C++ 標準では、コンストラクタで例外が投げられた場合に「既に構築された非静的メンバのデストラクタ」は走るが、**生ポインタ `muxer_` は解放されない**。`mp4.h:1900-1925` は `mp4_file_muxer_free()` による明示的解放を要求している。

`PyMp4FileDemuxer` (`src/mp4_ext.cpp:765-784`) も `demuxer_ = mp4_file_demuxer_new()` の後に例外を投げる経路はないが、将来の変更に対して同じ RAII 化が望ましい。

## 設計方針

### デストラクタからの例外漏れ対策

- `~PyMp4FileMuxer()` / `~PyMp4FileDemuxer()` の破棄経路は `noexcept` として振る舞わせる
- 内部的にはこれまでの `close()` を再利用してよいが、デストラクタから呼ぶ場合は例外を握りつぶす
- 明示的 `close()` は throw 可能なままにして、ユーザーがエラーハンドリングできる形を残す

擬似コード:

```cpp
~PyMp4FileMuxer() noexcept {
  try {
    close();
  } catch (...) {
    // デストラクタから例外を漏らさない
    // 可能なら PyErr_WriteUnraisable 相当で警告を出す
  }
}
```

### コンストラクタでのリーク対策

- 生ポインタ `Mp4FileMuxer* muxer_` / `Mp4FileDemuxer* demuxer_` を `std::unique_ptr` + カスタムデリータで RAII 化する
- こうすれば以降の例外で自動解放される

擬似コード:

```cpp
using MuxerHandle =
    std::unique_ptr<Mp4FileMuxer, decltype(&mp4_file_muxer_free)>;

class PyMp4FileMuxer {
 private:
  MuxerHandle muxer_{nullptr, mp4_file_muxer_free};
  ...
};
```

`close()` 内での明示的な `mp4_file_muxer_free()` 呼び出しは削除する (デストラクタで自動)。

## 完了条件

- `~PyMp4FileMuxer()` / `~PyMp4FileDemuxer()` から C++ 例外が伝播しない (`noexcept` として振る舞う)
- `PyMp4FileMuxer` / `PyMp4FileDemuxer` のコンストラクタで途中失敗した場合でも `mp4_file_muxer_free()` / `mp4_file_demuxer_free()` が確実に呼ばれる (RAII で保証)
- 既存のユーザー向け `close()` / `finalize()` の throw セマンティクスは変更しない (明示的呼び出しでは今まで通り例外が上がる)
- 追加テスト: コンストラクタ中に `mp4_file_muxer_initialize` が失敗した状況で `mp4_file_muxer_free` が呼ばれることを確認 (mp4-rust 側にテスト用の失敗インジェクションがないなら、少なくとも「破損入力で Demuxer コンストラクタ後 GC される経路がクラッシュしない」テストを追加)

## 解決方法

1. `src/mp4_ext.cpp:31-34` の `Mp4Exception` は据え置き
2. `PyMp4FileMuxer` / `PyMp4FileDemuxer` の `Mp4FileMuxer*` / `Mp4FileDemuxer*` メンバを `std::unique_ptr` + カスタムデリータ (`mp4_file_muxer_free` / `mp4_file_demuxer_free`) に置き換え
3. コンストラクタ本体で生ポインタを手動 free している箇所を削除
4. `close()` メソッドは `unique_ptr` の `reset()` に置き換える
5. デストラクタを `noexcept` として明示し、内部で `try { close(); } catch (...) {}` パターンを採用
6. デストラクタ内 catch では最低限デバッグ性を担保するため、可能であれば nanobind の `nb::gil_scoped_acquire` (Python ランタイムへのアタッチ) 経由で `PyErr_WriteUnraisable` を呼び、致命ではないが Python 側の warning フックに情報を残す
7. `test_free_threading.py` 相当の並行テストで、GC 起因の `__del__` が競合ケースでクラッシュしないことを確認するテストを追加

## 対応結果

バインディングを nanobind から PyO3 に置き換えたため、C++ のデストラクタ / コンストラクタでの例外安全性の議論そのものが消滅した。PyO3 では pyclass の `Drop` が Rust の RAII で自動処理され、コンストラクタ途中失敗時のリソース解放も Rust の所有権システムで保証されている。よって closed とする。
