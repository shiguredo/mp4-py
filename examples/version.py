#!/usr/bin/env python3
"""
バージョン情報表示
"""

import mp4


def main():
    """バージョン情報を表示"""
    print("=== バージョン情報 ===")
    print(f"mp4-py: {mp4.__version__}")
    print(f"mp4-rust:    {mp4.native_version()}")


if __name__ == "__main__":
    main()
