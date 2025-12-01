# mp4-py

[![PyPI](https://img.shields.io/pypi/v/mp4-py)](https://pypi.org/project/mp4-py/)
[![image](https://img.shields.io/pypi/pyversions/mp4-py.svg)](https://pypi.python.org/pypi/mp4-py)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Actions status](https://github.com/shiguredo/mp4-py/workflows/wheel/badge.svg)](https://github.com/shiguredo/mp4-py/actions)

## About Shiguredo's open source software

We will not respond to PRs or issues that have not been discussed on Discord. Also, Discord is only available in Japanese.

Please read <https://github.com/shiguredo/oss/blob/master/README.en.md> before use.

## 時雨堂のオープンソースソフトウェアについて

利用前に <https://github.com/shiguredo/oss> をお読みください。

## mp4-py について

[mp4-rust](https://github.com/shiguredo/mp4-rust) の Python バインディングです。 MP4 コンテナフォーマットの読み書きをサポートしています。

## 対応プラットフォーム

- macOS 26 arm64
- macOS 15 arm64
- macOS 14 arm64
- Ubuntu 24.04 x86_64
- Ubuntu 24.04 arm64
- Ubuntu 22.04 x86_64
- Ubuntu 22.04 arm64

### 対応予定プラットフォーム

- Windows 11 x86_64

## 対応 Python

- 3.14
- 3.13
- 3.12

## インストール

```bash
uv add mp4-py
```

## 使い方（基本 API）

- 提供: `Mp4FileDemuxer`, `Mp4FileMuxer`
- ビデオ/オーディオトラックの読み書きをサポート
- VP8/VP9/AV1、H.264/H.265、Opus/AAC コーデック対応

### MP4 ファイルの読み込み

```python
import io
from mp4 import Mp4FileDemuxer

# ファイルパスから demuxer を作成
with Mp4FileDemuxer("input.mp4") as demuxer:
    # サンプルを走査して処理
    for sample in demuxer:
        print(f"Sample: {sample.timestamp_seconds}s, keyframe={sample.keyframe}")
        print(f"Data size: {len(sample.data)} bytes")

# バイナリストリームから demuxer を作成
with open("input.mp4", "rb") as fp:
    demuxer = Mp4FileDemuxer(fp)
    for sample in demuxer:
        # サンプルを処理...
        pass
```

### MP4 ファイルの作成

```python
import io
from mp4 import (
    Mp4FileMuxer,
    Mp4MuxSample,
    Mp4SampleEntryVp08,
)


# ファイルにマルチプレックス
with Mp4FileMuxer("output.mp4") as muxer:
    # VP8 ビデオサンプルエントリーを作成
    video_entry = Mp4SampleEntryVp08(
        width=1920,
        height=1080,
    )

    # フレームを追加
    for i in range(30):
        is_keyframe = (i % 10) == 0  # 10フレームごとにキーフレーム

        # ビデオデータ（実際のエンコード済みデータに置き換えてください）
        video_data = b'\x00' * 1000

        # サンプルを作成して追加
        sample = Mp4MuxSample(
            track_kind="video",
            sample_entry=video_entry,
            keyframe=is_keyframe,
            timescale=30,
            duration=1,
            data=video_data,
        )
        muxer.append_sample(sample)

    # finalize() を呼んでファイルを完成させる（自動的に呼ばれるが明示的に呼ぶこともできます）

# バイナリストリームにマルチプレックス
with open("output.mp4", "wb") as fp:
    with Mp4FileMuxer(fp) as muxer:
        # マルチプレックス処理...
        pass
```

### トラック情報の取得

```python
from mp4 import Mp4FileDemuxer

with Mp4FileDemuxer("input.mp4") as demuxer:
    for track in demuxer.tracks:
        print(f"Track ID: {track.track_id}")
        print(f"Kind: {track.kind}")  # 'video' または 'audio'
        print(f"Duration: {track.duration_seconds:.2f}s")
```

> [!WARNING]
>
> - 現在は基本的な読み書き機能をサポートしています
> - マルチプレックス時は最初のサンプルで `sample_entry` を必須で指定してください
> - 同じトラック内で同じコーデック設定が続く場合、`sample_entry` に `None` を指定できます

## サンプル

- `examples/demux.py`: MP4 ファイルをデマルチプレックスしてトラックとサンプル情報を表示
- `examples/remux.py`: MP4 ファイルをリマルチプレックス（読み込んで別ファイルに書き込む）

実行例:

```bash
uv run python examples/demux.py input.mp4
uv run python examples/remux.py input.mp4 output.mp4
```

## ビルド

```bash
uv build --wheel
```

## mp4-rust ライセンス

Apache License 2.0

```text
Copyright 2024-2025, Takeru Ohta (Original Author)
Copyright 2024-2025, Shiguredo Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## mp4-py ライセンス

Apache License 2.0

```text
Copyright 2025-2025, Takeru Ohta (Original Author)
Copyright 2025-2025, Shiguredo Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
