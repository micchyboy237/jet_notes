#!/usr/bin/env python3
"""
Fast Git Repo Cleaner with clean progress logging.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List


def find_git_repos(base_dir: Path, max_depth: int = None) -> List[Path]:
    """Fast discovery using native find."""
    try:
        cmd = ["find", str(base_dir.resolve()), "-name", ".git", "-type", "d"]
        if max_depth is not None:
            cmd.extend(["-maxdepth", str(max_depth)])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        git_dirs = [
            Path(line.strip()) for line in result.stdout.splitlines() if line.strip()
        ]

        repos = []
        for gd in git_dirs:
            repo = gd.parent
            if (repo / ".git" / "HEAD").exists() or (repo / ".git").is_file():
                repos.append(repo)

        return sorted(set(repos))
    except Exception:
        # Fallback
        pattern = "**/.git" if max_depth is None else f"{'*/' * (max_depth or 10)}.git"
        return sorted({p.parent for p in base_dir.glob(pattern) if p.is_dir()})


def clean_repo(repo: Path, dry_run: bool = False) -> dict:
    """Clean one repo and return summary."""
    start = __import__("time").time()

    try:
        if not dry_run:
            subprocess.run(
                ["git", "reflog", "expire", "--all", "--expire=now"],
                cwd=repo,
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["git", "gc", "--aggressive", "--prune=now"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
        duration = __import__("time").time() - start
        return {"repo": repo, "success": True, "duration": duration}
    except Exception as e:
        duration = __import__("time").time() - start
        return {"repo": repo, "success": False, "error": str(e), "duration": duration}


def main():
    parser = argparse.ArgumentParser(
        description="Fast Git repository cleaner with clean progress",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "base_dir",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Base directory (default: current)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show per-repo details"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Only final summary")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel workers (4-8 recommended on M1/M2/M3)",
    )
    parser.add_argument("--max-depth", type=int, default=None, help="Max search depth")

    args = parser.parse_args()

    if args.quiet and args.verbose:
        args.verbose = False

    base = args.base_dir.resolve()
    print(f"🔍 Searching in: {base}")

    repos = find_git_repos(base, args.max_depth)
    total = len(repos)
    print(f"Found {total} repositories.\n")

    if not total:
        return 0

    if args.dry_run:
        print("DRY RUN mode — no changes will be made.\n")

    success = 0
    total_time = 0.0
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_repo = {
            executor.submit(clean_repo, repo, args.dry_run): repo for repo in repos
        }

        for future in as_completed(future_to_repo):
            completed += 1
            result = future.result()
            total_time += result["duration"]

            if result["success"]:
                success += 1

            # Smart logging
            if not args.quiet:
                status = "✓" if result["success"] else "✗"
                name = result["repo"].name
                duration_str = f"{result['duration']:.1f}s"

                if args.verbose:
                    print(f"{status} {completed:3d}/{total}  {name:40}  {duration_str}")
                else:
                    # Progress line (overwrite)
                    print(
                        f"Progress: {completed:3d}/{total}  |  Success: {success:3d}  |  Last: {name[:35]:35} {duration_str}   ",
                        end="\r",
                        flush=True,
                    )

    # Final clean summary
    print("\n" + "=" * 60)
    print(f"✅ Finished! {success}/{total} repositories cleaned successfully.")
    print(f"   Total estimated wall time: {total_time:.1f}s")
    if total > 0:
        print(f"   Average per repo: {total_time / total:.1f}s")
    print("=" * 60)

    return 0 if success == total else 1


if __name__ == "__main__":
    sys.exit(main())
