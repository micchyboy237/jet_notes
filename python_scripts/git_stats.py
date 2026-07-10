import argparse
import fnmatch
import os
from datetime import datetime
from typing import Dict, List, Literal, Optional

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
from jet.file.utils import save_file
from tqdm import tqdm


def format_macos_modified_time(timestamp: float) -> str:
    """Format timestamp to ISO 8601 for parsability."""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def find_git_repos(base_dir: str) -> list[str]:
    """Find all git repos inside base_dir (non-recursive deeper than one repo)."""
    repos = []
    for root, dirs, _ in os.walk(base_dir):
        if ".git" in dirs:
            repos.append(root)
            dirs[:] = []  # don't descend further once repo is found
    return repos


def check_is_git_repo(base_dir: str) -> bool:
    try:
        repo = Repo(base_dir, search_parent_directories=True)
        if repo.bare:
            return False
        list(repo.iter_commits("HEAD", max_count=1))
        return True
    except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError, ValueError):
        return False


SortKey = Literal[
    "updated_at", "-updated_at", "name", "-name", "path", "-path", "depth", "-depth"
]


def filter_and_sort_results(
    items: List[Dict], since: Optional[str] = None, sort_by: SortKey = "updated_at"
) -> List[Dict]:
    """
    Filter items by minimum date (if provided) and sort them.
    Re-assigns 'rank' after final ordering.
    """
    filtered = items

    if since:
        try:
            # Accept YYYY-MM-DD and assume start of day
            since_dt = datetime.fromisoformat(since.strip() + "T00:00:00")
        except ValueError as e:
            raise ValueError(
                f"Invalid --since date format (use YYYY-MM-DD): {since!r}"
            ) from e

        filtered = [
            item
            for item in items
            if datetime.fromisoformat(item["updated_at"]) >= since_dt
        ]

    # Determine sort direction and field
    reverse = False
    key_field = sort_by
    if sort_by.startswith("-"):
        reverse = True
        key_field = sort_by[1:]

    def get_sort_key(item: Dict):
        if key_field == "updated_at":
            return item["updated_at"]
        if key_field == "name":
            return item["basename"].lower()
        if key_field == "path":
            return item["rel_path"].lower()
        if key_field == "depth":
            return item["depth"]
        raise ValueError(f"Unsupported sort field: {key_field!r}")

    sorted_items = sorted(filtered, key=get_sort_key, reverse=reverse)

    # Re-assign ranks
    for i, item in enumerate(sorted_items, 1):
        item["rank"] = i

    return sorted_items


def get_last_commit_dates_optimized(
    base_dir: str,
    extensions: Optional[List[str]] = None,
    depth: Optional[int] = None,
    output_file: Optional[str] = None,
    mode: Literal["auto", "git", "file"] = "auto",
    type_filter: Literal["files", "dirs", "both"] = "both",
    file_pattern: Optional[str] = None,
) -> tuple[List[Dict], bool]:
    if not os.path.isdir(base_dir):
        raise ValueError(f"{base_dir} is not a valid directory")

    exclude_patterns = {
        ".DS_Store",
        "Icon\r",
        ".Trashes",
        ".Spotlight-V100",
        ".fseventsd",
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".idea",
        "*.pyc",
        "*.pyo",
        "*.swp",
        "stats_results",
    }
    if output_file:
        exclude_patterns.add(os.path.basename(output_file))

    base_depth = len(base_dir.split(os.sep))
    is_git_repo = check_is_git_repo(base_dir)

    effective_mode = (
        "git"
        if mode == "auto" and is_git_repo
        else "file"
        if mode in ["auto", "git"]
        else mode
    )
    results = []

    def is_excluded(path: str, name: str) -> bool:
        if name in exclude_patterns:
            return True
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        rel_path = os.path.relpath(path, base_dir)
        return any(excluded in rel_path.split(os.sep) for excluded in exclude_patterns)

    def calculate_depth(rel_path: str) -> int:
        components = rel_path.split(os.sep)
        return len([c for c in components if c]) or 1

    if effective_mode == "git":
        repo = Repo(base_dir, search_parent_directories=True)

        tracked_paths = set(repo.git.ls_files().splitlines())
        ignored_paths = {
            os.path.join(repo.working_tree_dir, p)
            for p in repo.git.ls_files(others=True, exclude_standard=True).splitlines()
            if repo.ignored(os.path.join(repo.working_tree_dir, p))
        }

        file_paths = []
        dir_paths = []

        for root, dirs, files in tqdm(os.walk(base_dir), desc="Scanning directories"):
            current_depth = len(root.split(os.sep)) - base_depth
            if depth is not None and current_depth > depth:
                continue
            dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d), d)]

            if type_filter in ["files", "both"]:
                for name in files:
                    if is_excluded(os.path.join(root, name), name):
                        continue
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, repo.working_tree_dir)
                    if rel_path in tracked_paths and full_path not in ignored_paths:
                        if extensions:
                            _, ext = os.path.splitext(name)
                            if ext not in extensions:
                                continue
                        if file_pattern:
                            patterns = [p.strip() for p in file_pattern.split(",")]
                            if not any(
                                fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel_path, p)
                                for p in patterns
                            ):
                                continue
                        file_paths.append(rel_path)

            if type_filter in ["dirs", "both"]:
                for name in dirs:
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, repo.working_tree_dir)
                    if rel_path not in [".", ".."] and full_path not in ignored_paths:
                        contains_tracked = any(
                            os.path.relpath(
                                os.path.join(subroot, fname), repo.working_tree_dir
                            )
                            in tracked_paths
                            for subroot, _, fnames in os.walk(full_path)
                            for fname in fnames
                        )
                        if contains_tracked:
                            dir_paths.append(rel_path)

        commit_times = {}

        if file_paths and type_filter in ["files", "both"]:
            for path in tqdm(file_paths, desc="Processing file commits"):
                try:
                    commits = list(repo.iter_commits(paths=[path], max_count=1))
                    if commits:
                        commit_times[path] = format_macos_modified_time(
                            commits[0].committed_date
                        )
                except (GitCommandError, ValueError):
                    pass

        if type_filter in ["dirs", "both"]:
            for dir_path in tqdm(dir_paths, desc="Processing directory commits"):
                try:
                    commits = list(repo.iter_commits(paths=[dir_path], max_count=1))
                    if commits:
                        commit_times[dir_path] = format_macos_modified_time(
                            commits[0].committed_date
                        )
                except (GitCommandError, ValueError):
                    continue

        for root, dirs, files in tqdm(os.walk(base_dir), desc="Building results"):
            current_depth = len(root.split(os.sep)) - base_depth
            if depth is not None and current_depth > depth:
                continue
            dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d), d)]

            if type_filter in ["files", "both"]:
                for name in files:
                    if is_excluded(os.path.join(root, name), name):
                        continue
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, repo.working_tree_dir)
                    if extensions:
                        _, ext = os.path.splitext(name)
                        if ext not in extensions:
                            continue
                    if rel_path in commit_times and full_path not in ignored_paths:
                        matched_pattern = None
                        if file_pattern:
                            patterns = [p.strip() for p in file_pattern.split(",")]
                            for p in patterns:
                                if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(
                                    rel_path, p
                                ):
                                    matched_pattern = p
                                    break
                        if rel_path in commit_times:
                            results.append(
                                {
                                    "basename": name,
                                    "updated_at": commit_times[rel_path],
                                    "type": "file",
                                    "rel_path": rel_path,
                                    "path": full_path,
                                    "depth": calculate_depth(rel_path),
                                    "matched_pattern": matched_pattern,
                                }
                            )

            if type_filter in ["dirs", "both"]:
                for name in dirs:
                    full_path = os.path.join(root, name)
                    rel_path = os.path.relpath(full_path, repo.working_tree_dir)
                    if rel_path in commit_times and full_path not in ignored_paths:
                        results.append(
                            {
                                "basename": name,
                                "updated_at": commit_times[rel_path],
                                "type": "directory",
                                "rel_path": rel_path,
                                "path": full_path,
                                "depth": calculate_depth(rel_path),
                            }
                        )

    else:  # file mode
        for root, dirs, files in tqdm(
            os.walk(base_dir), desc="Scanning files (non-Git)"
        ):
            current_depth = len(root.split(os.sep)) - base_depth
            if depth is not None and current_depth > depth:
                continue
            dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d), d)]

            if type_filter in ["files", "both"]:
                for name in files:
                    if is_excluded(os.path.join(root, name), name):
                        continue
                    full_path = os.path.join(root, name)
                    if extensions:
                        _, ext = os.path.splitext(name)
                        if ext not in extensions:
                            continue
                    matched_pattern = None
                    if file_pattern:
                        patterns = [p.strip() for p in file_pattern.split(",")]
                        rel_path = os.path.relpath(full_path, base_dir)
                        if not any(
                            fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel_path, p)
                            for p in patterns
                        ):
                            continue
                        for p in patterns:
                            if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel_path, p):
                                matched_pattern = p
                                break
                    try:
                        mtime = os.stat(full_path).st_mtime
                        updated_at = format_macos_modified_time(mtime)
                        rel_path = os.path.relpath(full_path, base_dir)
                        results.append(
                            {
                                "basename": name,
                                "updated_at": updated_at,
                                "type": "file",
                                "rel_path": rel_path,
                                "path": full_path,
                                "depth": calculate_depth(rel_path),
                                "matched_pattern": matched_pattern,
                            }
                        )
                    except Exception:
                        continue

            if type_filter in ["dirs", "both"]:
                for name in dirs:
                    full_path = os.path.join(root, name)
                    if is_excluded(full_path, name):
                        continue
                    try:
                        latest_mtime = None
                        for subroot, _, fnames in os.walk(full_path):
                            for fname in fnames:
                                fpath = os.path.join(subroot, fname)
                                try:
                                    mtime = os.stat(fpath).st_mtime
                                    if latest_mtime is None or mtime > latest_mtime:
                                        latest_mtime = mtime
                                except Exception:
                                    continue
                        if latest_mtime:
                            updated_at = format_macos_modified_time(latest_mtime)
                            rel_path = os.path.relpath(full_path, base_dir)
                            results.append(
                                {
                                    "basename": name,
                                    "updated_at": updated_at,
                                    "type": "directory",
                                    "rel_path": rel_path,
                                    "path": full_path,
                                    "depth": calculate_depth(rel_path),
                                }
                            )
                    except Exception:
                        continue

    # IMPORTANT: We no longer sort here — sorting & filtering is done later
    return results, is_git_repo


def process_file_mode(
    base_dir,
    extensions,
    depth,
    mode,
    type_filter,
    file_pattern,
    output_file,
    since,
    sort_by,
):
    raw_results, is_git_repo = get_last_commit_dates_optimized(
        base_dir, extensions, depth, None, mode, type_filter, file_pattern
    )
    updates = filter_and_sort_results(raw_results, since=since, sort_by=sort_by)
    base_output_file = os.path.join(base_dir, "_file_stats.json")
    output_file = output_file or base_output_file
    print("\nTop 10 most recent/relevant items:")
    for item in updates[:10]:
        print(
            f"{item['rank']:3d}. {item['rel_path']} "
            f"({item['type']}, depth={item['depth']}): {item['updated_at']}"
        )
    for item in updates:
        if "path" in item:
            item["path"] = os.path.abspath(item["path"])
    save_file(updates, output_file)


def process_repo(
    repo_dir,
    extensions,
    depth,
    mode,
    type_filter,
    file_pattern,
    output_file,
    since,
    sort_by,
):
    raw_results, is_git_repo = get_last_commit_dates_optimized(
        repo_dir, extensions, depth, None, mode, type_filter, file_pattern
    )
    updates = filter_and_sort_results(raw_results, since=since, sort_by=sort_by)
    base_output_file = os.path.join(
        repo_dir,
        "_git_stats.json" if is_git_repo and mode != "file" else "_file_stats.json",
    )
    output_file = output_file or base_output_file
    for item in updates:
        if "path" in item:
            item["path"] = os.path.abspath(item["path"])
    save_file(updates, output_file)
    return updates


def process_single(
    base_dir,
    extensions,
    depth,
    mode,
    type_filter,
    file_pattern,
    output_file,
    since,
    sort_by,
):
    print(f"\n=== Scanning: {base_dir} ===")
    updates = process_repo(
        base_dir,
        extensions,
        depth,
        mode,
        type_filter,
        file_pattern,
        output_file,
        since,
        sort_by,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get the last modified or commit dates of files and directories with macOS-style formatting."
    )
    parser.add_argument(
        "base_dir", nargs="?", default=os.getcwd(), help="Base directory to scan"
    )
    parser.add_argument(
        "-e", "--extensions", help="Comma-separated file extensions (e.g. .py,.js)"
    )
    parser.add_argument(
        "-f",
        "--output-file",
        type=str,
        default=None,
        help="Custom output JSON file path",
    )
    parser.add_argument(
        "-d", "--depth", type=int, default=None, help="Maximum depth to scan"
    )
    parser.add_argument("-m", "--mode", choices=["auto", "git", "file"], default="auto")
    parser.add_argument(
        "-t", "--type", choices=["files", "dirs", "both"], default="files"
    )
    parser.add_argument(
        "-p",
        "--file-pattern",
        type=str,
        default=None,
        help="Comma-separated fnmatch patterns for files",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only show items updated on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--sort",
        type=str,
        default="-updated_at",
        help="Sort by: updated_at, -updated_at (default: newest first), "
        "name, -name, path, -path, depth, -depth",
    )

    args = parser.parse_args()

    base_dir = args.base_dir
    extensions = (
        [ext.strip() for ext in args.extensions.split(",")] if args.extensions else None
    )

    if args.mode == "file":
        process_file_mode(
            base_dir,
            extensions,
            args.depth,
            args.mode,
            args.type,
            args.file_pattern,
            args.output_file,
            args.since,
            args.sort,
        )
    else:
        repos = find_git_repos(base_dir)
        if repos:
            # Process each repo individually without combining
            for repo_dir in repos:
                process_single(
                    repo_dir,
                    extensions,
                    args.depth,
                    args.mode,
                    args.type,
                    args.file_pattern,
                    args.output_file,
                    args.since,
                    args.sort,
                )
        else:
            process_single(
                base_dir,
                extensions,
                args.depth,
                args.mode,
                args.type,
                args.file_pattern,
                args.output_file,
                args.since,
                args.sort,
            )
