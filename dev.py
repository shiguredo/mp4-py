"""canary リリース用の version bump スクリプト。

Cargo.toml の [package] version を対象に、`.devN` を +1 する
(なければ次のマイナー版に `.dev0` を付ける)。
更新後 Cargo.lock を再生成し、git commit + tag + push まで行う。
"""

import argparse
import re
import subprocess
from typing import Optional

CARGO_TOML = "Cargo.toml"
# Cargo.toml の `version = "..."` 行を対象にする正規表現。
# [package] セクション先頭の 1 個目のみを差し替えるため、非欲張り一致で先頭優先。
VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def read_version(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    match = VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"'version = \"...\"' が {path} に見つからない")
    return match.group(2)


def bump(current: str) -> str:
    if ".dev" in current:
        base, dev = current.rsplit(".dev", 1)
        return f"{base}.dev{int(dev) + 1}"
    parts = current.split(".")
    if len(parts) != 3:
        raise ValueError(f"Cargo.toml の version 形式が X.Y.Z ではない: {current}")
    major, minor, _patch = map(int, parts)
    return f"{major}.{minor + 1}.0.dev0"


def write_version(path: str, new_version: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # 最初にマッチした version 行だけを差し替える (dependencies の version は無視)
    replaced = VERSION_RE.sub(rf'\g<1>"{new_version}"', text, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(replaced)


def update_cargo_lock(dry_run: bool) -> None:
    if dry_run:
        print("Dry-run: Would run 'cargo update -p mp4-py'")
    else:
        subprocess.run(["cargo", "update", "-p", "mp4-py"], check=True)


def git_operations(new_version: str, dry_run: bool) -> None:
    if dry_run:
        print("Dry-run: Would run 'git add Cargo.toml Cargo.lock'")
        print(f"Dry-run: Would run 'git commit -m [canary] Bump version to {new_version}'")
        print(f"Dry-run: Would run 'git tag {new_version}'")
        print("Dry-run: Would run 'git push && git push --tags'")
    else:
        subprocess.run(["git", "add", CARGO_TOML, "Cargo.lock"], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"[canary] Bump version to {new_version}"], check=True
        )
        subprocess.run(["git", "tag", new_version], check=True)
        subprocess.run(["git", "push"], check=True)
        subprocess.run(["git", "push", "--tags"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump Cargo.toml version, update Cargo.lock, commit and tag."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="変更を加えず実行内容だけ表示する"
    )
    args = parser.parse_args()

    current = read_version(CARGO_TOML)
    new_version = bump(current)
    print(f"Current version: {current}")
    print(f"New version: {new_version}")
    confirmation = input("Do you want to update the version? (Y/n): ").strip().lower()
    if confirmation != "y":
        print("Version update canceled.")
        return

    if args.dry_run:
        print(f"Dry-run: Would update {CARGO_TOML} to {new_version}")
    else:
        write_version(CARGO_TOML, new_version)
        print(f"Version updated in {CARGO_TOML} to {new_version}")

    update_cargo_lock(args.dry_run)
    git_operations(new_version, args.dry_run)


if __name__ == "__main__":
    main()
