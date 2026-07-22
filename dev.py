"""canary リリース用の version bump スクリプト。

pyproject.toml の [project] version を対象に、`.devN` を +1 する
(なければ次のマイナー版に `.dev0` を付ける)。
更新後 uv sync を実行し、git commit + tag + push まで行う。
"""

import argparse
import re
import subprocess

PYPROJECT_TOML = "pyproject.toml"
# pyproject.toml の `version = "..."` 行を対象にする正規表現。
# [project] セクションの静的 version 指定を差し替えるため、行頭マッチで最初の 1 件のみ扱う。
VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def read_version(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    match = VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"'version = \"...\"' が {path} に見つからない")
    return match.group(2)


def bump(current: str) -> str:
    # 既に .devN が付いていれば N を +1 する。
    if ".dev" in current:
        base, dev = current.rsplit(".dev", 1)
        return f"{base}.dev{int(dev) + 1}"
    # stable リリース (X.Y.Z) からの再開時は次のマイナー版に .dev0 を付ける。
    parts = current.split(".")
    if len(parts) != 3:
        raise ValueError(f"pyproject.toml の version 形式が X.Y.Z ではない: {current}")
    major, minor, _patch = map(int, parts)
    return f"{major}.{minor + 1}.0.dev0"


def write_version(path: str, new_version: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # 最初にマッチした version 行だけを差し替える (依存指定の version 文字列は無視される)
    replaced = VERSION_RE.sub(rf'\g<1>"{new_version}"', text, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(replaced)


def run_uv_sync(dry_run: bool) -> None:
    if dry_run:
        print("Dry-run: Would run 'uv sync' and add 'uv.lock' to git")
    else:
        subprocess.run(["uv", "sync"], check=True)
        subprocess.run(["git", "add", "uv.lock"], check=True)


def git_operations(new_version: str, dry_run: bool) -> None:
    if dry_run:
        print(f"Dry-run: Would run 'git add {PYPROJECT_TOML}'")
        print(f"Dry-run: Would run 'git commit -m [canary] Bump version to {new_version}'")
        print(f"Dry-run: Would run 'git tag {new_version}'")
        print("Dry-run: Would run 'git push && git push --tags'")
    else:
        subprocess.run(["git", "add", PYPROJECT_TOML], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"[canary] Bump version to {new_version}"], check=True
        )
        subprocess.run(["git", "tag", new_version], check=True)
        subprocess.run(["git", "push"], check=True)
        subprocess.run(["git", "push", "--tags"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump pyproject.toml version, run uv sync, commit and tag."
    )
    parser.add_argument("--dry-run", action="store_true", help="変更を加えず実行内容だけ表示する")
    args = parser.parse_args()

    current = read_version(PYPROJECT_TOML)
    new_version = bump(current)
    print(f"Current version: {current}")
    print(f"New version: {new_version}")
    confirmation = input("Do you want to update the version? (Y/n): ").strip().lower()
    if confirmation != "y":
        print("Version update canceled.")
        return

    if args.dry_run:
        print(f"Dry-run: Would update {PYPROJECT_TOML} to {new_version}")
    else:
        write_version(PYPROJECT_TOML, new_version)
        print(f"Version updated in {PYPROJECT_TOML} to {new_version}")

    run_uv_sync(args.dry_run)
    git_operations(new_version, args.dry_run)


if __name__ == "__main__":
    main()
