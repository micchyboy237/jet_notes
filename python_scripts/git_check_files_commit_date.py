import argparse
import os
import subprocess
import time
from functools import partial
from multiprocessing import Pool


def get_repo_root(path):
    """Resolve the git repository root from any subdirectory."""
    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=path, stderr=subprocess.DEVNULL
        )
        return result.decode().strip()
    except subprocess.CalledProcessError:
        raise ValueError(f"'{path}' is not inside a git repository")


def get_file_commit_info(repo_root, rel_path):
    """
    Get the short hash and timestamp of the latest commit for a file.
    Must be at module level so multiprocessing can pickle it.
    """
    args = ["git", "--no-pager", "log", "-1", "--format=%h|%at", "--", rel_path]
    try:
        b = subprocess.check_output(args, cwd=repo_root)
        data = b.decode().strip()
        if not data:
            return None
        h, t = data.split("|")
        return (rel_path, h, time.gmtime(float(t)))
    except (subprocess.CalledProcessError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Get the latest commit date for every file under a target directory in a git repo."
    )
    parser.add_argument(
        "target_dir", help="Any directory under a git repository to scan"
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel workers (defaults to CPU count)",
    )
    args = parser.parse_args()

    # Validate and resolve paths
    target_dir = os.path.abspath(args.target_dir)
    if not os.path.isdir(target_dir):
        parser.error(f"Target directory does not exist: {target_dir}")

    repo_root = get_repo_root(target_dir)
    # Compute the relative path from repo root to target dir
    rel_target = os.path.relpath(target_dir, repo_root)
    # Use "." if target_dir IS the repo root
    git_path_filter = "." if rel_target == "." else rel_target

    print(f"Repository root : {repo_root}")
    print(f"Target directory: {target_dir}")
    print(f"Git path filter : {git_path_filter}")
    print("-" * 60)

    # List only tracked files under the target directory
    ls_args = ["git", "ls-files", "--", git_path_filter]
    files_bytes = subprocess.check_output(ls_args, cwd=repo_root)
    all_files = [f for f in files_bytes.decode().splitlines() if f]

    if not all_files:
        print("No tracked files found in the target directory.")
        return

    print(f"Found {len(all_files)} tracked file(s). Scanning...")

    # Bind repo_root to the worker using partial so multiprocessing can pickle it
    worker = partial(get_file_commit_info, repo_root)

    # Query latest commit per file using multiprocessing
    with Pool(processes=args.jobs) as p:
        filedata = [
            res for res in p.imap_unordered(worker, all_files) if res is not None
        ]

    # Sort by date descending (latest first) and display
    dfmt = "%Y-%m-%d %H:%M:%S UTC"
    filedata.sort(key=lambda a: a[2], reverse=True)

    for name, tag, date in filedata:
        print(f"{time.strftime(dfmt, date)} | {tag} | {name}")


if __name__ == "__main__":
    main()
