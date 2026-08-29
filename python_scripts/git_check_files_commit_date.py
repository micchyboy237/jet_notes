"""Check per-file last commit dates in a Git repository.

Automatically detects shallow clones and falls back to the GitHub REST API
to retrieve accurate per-file commit dates without requiring full history.

Usage:
    python git_check_files_commit_date.py <target_directory>
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _run_git(args: list[str], cwd: str) -> tuple[int, str]:
    """Run a git command and return (returncode, stdout)."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout.strip()


def _find_repo_root(path: str) -> Optional[str]:
    """Find the git repository root from a given path."""
    rc, output = _run_git(["rev-parse", "--show-toplevel"], cwd=path)
    if rc == 0 and output:
        return output
    return None


def _is_shallow(repo_root: str) -> bool:
    """Check if the repository is a shallow clone."""
    shallow_file = os.path.join(repo_root, ".git", "shallow")
    return os.path.exists(shallow_file)


def _get_remote_url(repo_root: str) -> Optional[str]:
    """Extract owner/repo from the git remote URL."""
    rc, url = _run_git(["remote", "get-url", "origin"], cwd=repo_root)
    if rc != 0 or not url:
        return None

    # Handle SSH: git@github.com:owner/repo.git
    if url.startswith("git@"):
        parts = url.split(":")[-1]
        return parts.removesuffix(".git")

    # Handle HTTPS: https://github.com/owner/repo.git
    if "github.com" in url:
        parts = url.split("github.com/")[-1]
        return parts.removesuffix(".git")

    return None


def _github_api_get_file_commit_date(
    owner_repo: str, file_path: str, token: Optional[str] = None
) -> Optional[dict]:
    """Query GitHub REST API for the last commit touching a specific file.

    Returns dict with 'date' (str) and 'sha' (str), or None on failure.
    Docs: https://docs.github.com/rest/commits/commits#list-commits
    """
    api_url = (
        f"https://api.github.com/repos/{owner_repo}/commits?path={file_path}&per_page=1"
    )

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    req = Request(api_url, headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data and isinstance(data, list):
                commit = data[0]
                return {
                    "date": commit["commit"]["committer"]["date"],
                    "sha": commit["sha"][:7],
                }
    except HTTPError as e:
        print(
            f"\n  ⚠️  GitHub API error for {file_path}: HTTP {e.code}", file=sys.stderr
        )
    except URLError as e:
        print(f"\n  ⚠️  GitHub API unreachable: {e.reason}", file=sys.stderr)
    except Exception as e:
        print(
            f"\n  ⚠️  GitHub API unexpected error for {file_path}: {e}", file=sys.stderr
        )

    return None


def _get_local_file_commit_info(repo_root: str, rel_path: str) -> Optional[dict]:
    """Get last commit date/sha for a file using local git log."""
    rc, output = _run_git(
        ["log", "-1", "--format=%ai|%h", "--", rel_path],
        cwd=repo_root,
    )
    if rc == 0 and output and "|" in output:
        date_str, sha = output.split("|", 1)
        return {"date": date_str.strip(), "sha": sha.strip()}
    return None


def _get_tracked_files(repo_root: str, path_filter: str) -> list[str]:
    """List tracked files under the given path filter."""
    rc, output = _run_git(
        ["ls-files", "--", path_filter],
        cwd=repo_root,
    )
    if rc != 0 or not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def _print_progress(current: int, total: int, label: str, width: int = 40) -> None:
    """Print an inline progress bar that overwrites the current line."""
    pct = current / total if total > 0 else 1
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    sys.stderr.write(f"\r  [{bar}] {current}/{total} ({pct:.0%}) {label}")
    sys.stderr.flush()


def _clear_progress_line() -> None:
    """Clear the progress bar line after completion."""
    sys.stderr.write("\r" + " " * 80 + "\r")
    sys.stderr.flush()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <target_directory>", file=sys.stderr)
        sys.exit(1)

    target_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(target_dir):
        print(f"Error: '{target_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    repo_root = _find_repo_root(target_dir)
    if not repo_root:
        print(f"Error: '{target_dir}' is not inside a git repository", file=sys.stderr)
        sys.exit(1)

    # Compute the path filter relative to repo root
    rel_filter = os.path.relpath(target_dir, repo_root)
    if rel_filter == ".":
        rel_filter = ""

    shallow = _is_shallow(repo_root)
    owner_repo = _get_remote_url(repo_root) if shallow else None
    github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    print(f"Repository root : {repo_root}")
    print(f"Target directory: {target_dir}")
    print(f"Git path filter : {rel_filter or '(root)'}")
    print(f"Shallow clone   : {'Yes (using GitHub API fallback)' if shallow else 'No'}")
    if shallow and not owner_repo:
        print(
            "⚠️  Could not detect GitHub remote; falling back to local git (dates may be inaccurate)"
        )
    print("-" * 60)

    tracked_files = _get_tracked_files(repo_root, rel_filter)
    if not tracked_files:
        print("No tracked files found matching the path filter.")
        sys.exit(0)

    total = len(tracked_files)
    print(f"Found {total} tracked file(s). Scanning...\n")

    results: list[tuple[str, str, str]] = []
    api_calls = 0
    local_fallbacks = 0
    failures = 0
    start_time = time.monotonic()

    for idx, rel_path in enumerate(sorted(tracked_files), start=1):
        info: Optional[dict] = None
        source = ""

        # Update progress bar
        short_name = Path(rel_path).name
        _print_progress(idx, total, short_name)

        if shallow and owner_repo:
            # Primary: GitHub API for accurate per-file dates
            info = _github_api_get_file_commit_date(owner_repo, rel_path, github_token)
            if info:
                api_calls += 1
                source = "api"
            else:
                # Fallback: local git (will show shallow commit date)
                info = _get_local_file_commit_info(repo_root, rel_path)
                if info:
                    local_fallbacks += 1
                    source = "local-fallback"
                else:
                    failures += 1
        else:
            # Non-shallow: local git log is accurate
            info = _get_local_file_commit_info(repo_root, rel_path)
            if info:
                source = "local"
            else:
                failures += 1

        if info:
            results.append((info["date"], info["sha"], rel_path))
        else:
            results.append(("UNKNOWN", "???????", rel_path))

    # Clear progress line before printing results
    _clear_progress_line()

    elapsed = time.monotonic() - start_time

    # Print results sorted by date descending
    for date_str, sha, rel_path in sorted(results, key=lambda r: r[0], reverse=True):
        print(f"{date_str} | {sha} | {rel_path}")

    # Summary
    print("\n" + "-" * 60)
    print(f"Completed in {elapsed:.1f}s")
    if shallow:
        print(
            f"Mode: GitHub API ({api_calls} calls) + local fallback ({local_fallbacks}) + failures ({failures})"
        )
        if not github_token:
            print(
                "💡 Tip: Set GITHUB_TOKEN env var to increase API rate limit (60→5000/hr)"
            )
    else:
        print(f"Mode: Local git log ({len(results)} files, {failures} failures)")


if __name__ == "__main__":
    main()
