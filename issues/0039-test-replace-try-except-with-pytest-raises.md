# test_mp4.py の try/except + assert False パターンを pytest.raises に置き換える

- Priority: Low
- Created: 2026-08-15
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/fix-replace-try-except-with-pytest-raises
- Polished: 2026-08-15

## 目的

`tests/test_mp4.py` の `test_track_metadata_invalid_language` が `CODEBASE.md` の「明確な理由がない限りは try/expect をテストでは利用しないこと」に違反している状態を解消する。

## 優先度根拠

Low。

- 単一テストのスタイル修正で、機能への影響はゼロ
- 修正コストは小 (1 テストの書き換え)

## 現状

`tests/test_mp4.py` の `test_track_metadata_invalid_language`:

```python
options = Mp4FileMuxerOptions(
    audio_track=Mp4TrackMetadata(language="JPN", name="Invalid"),
)
try:
    Mp4FileMuxer(io.BytesIO(), options=options)
    assert False, "不正な言語コードがエラーにならない"
except ValueError as error:
    assert "invalid language code" in str(error)
```

同じファイル内の他のテスト (例: `test_track_info_zero_timescale_raises_value_error`) は `pytest.raises` を使用しており、このテストだけ不整合。`pytest.raises(ValueError, match="invalid language code")` で置き換え可能であり、try/except を使う理由がない。この置き換えで ruff の PT015 / PT017 / B011 の 3 ルールも同時に解消される (静的解析有効化の別 issue (0038) が 0039 を担当として参照している)。

## 設計方針

- `pytest.raises(ValueError, match="invalid language code")` に置き換える

## 完了条件

- `tests/test_mp4.py` から try/except + `assert False` パターンが消える
- 全テストが通過する

## 解決方法

1. `tests/test_mp4.py` の `test_track_metadata_invalid_language` を `with pytest.raises(ValueError, match="invalid language code"):` 形式に書き換える
2. CHANGES.md の `### misc` に追記する (著者表記付き、shiguredo-changelog スキルの形式に従う)
3. `NO_UV_SYNC=1 uv run pytest tests/ --timeout=10` で全テスト通過を確認する
