#!/usr/bin/env python3
"""
Git Repo Cleaner - Aggressively garbage collect all Git repositories under a base directory.

Safely reduces .git folder sizes by running git gc --aggressive --prune=now on each repo.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


def find_git_repos(base_dir: Path) -> List[Path]:
    """Find all Git repositories under the base directory."""
    if not base_dir.exists() or not base_dir.is_dir():
        raise NotADirectoryError(f"Base directory not found: {base_dir}")

    # Find all .git directories and get their parent (repo root)
    git_dirs = list(base_dir.rglob(".git"))
    repos = []

    for git_dir in git_dirs:
        if git_dir.is_dir():
            repo_root = git_dir.parent
            # Verify it's a valid Git repo
            if (repo_root / ".git" / "HEAD").exists() or (repo_root / ".git").is_file():
                repos.append(repo_root)

    return sorted(set(repos))  # Remove any duplicates


def clean_repo(repo: Path, verbose: bool = True, dry_run: bool = False) -> bool:
    """Run aggressive GC on a single repository."""
    if verbose or dry_run:
        print(f"{'[DRY RUN] ' if dry_run else ''}Cleaning: {repo}")

    if dry_run:
        return True

    try:
        # Optional: expire reflogs first
        subprocess.run(
            ["git", "reflog", "expire", "--all", "--expire=now"],
            cwd=repo,
            check=False,  # Don't fail if reflog command has issues
            capture_output=not verbose,
            text=True,
        )

        # Main aggressive GC
        result = subprocess.run(
            ["git", "gc", "--aggressive", "--prune=now"],
            cwd=repo,
            check=True,
            capture_output=not verbose,
            text=True,
        )
        if verbose:
            print(f"  ✓ Success for {repo}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed for {repo}: {e}")
        if verbose and e.stderr:
            print(f"    Error: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        print(f"  ✗ Git not found in PATH while processing {repo}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Aggressively clean .git folders in all repositories under a base directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "base_dir",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Base directory to search for Git repositories (default: current directory)",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed output"
    )

    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress most output (overrides --verbose)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum directory depth to search (None = unlimited)",
    )

    args = parser.parse_args()

    # Handle quiet mode
    verbose = args.verbose and not args.quiet

    print(f"Searching for Git repositories under: {args.base_dir.resolve()}")

    try:
        repos = find_git_repos(args.base_dir)

        if not repos:
            print("No Git repositories found.")
            return 0

        print(f"Found {len(repos)} repository(ies). Starting cleanup...\n")

        success_count = 0
        for repo in repos:
            if clean_repo(repo, verbose=verbose, dry_run=args.dry_run):
                success_count += 1

        print(
            f"\nCleanup complete! {success_count}/{len(repos)} repositories processed successfully."
        )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
