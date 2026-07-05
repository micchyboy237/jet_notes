from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Iterator

from git_repo_utils import (
    RepoInfo,
    get_remote_origin_url,
    get_repo_info,
    is_git_repository,
)
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def get_args() -> argparse.Namespace:
    """
    Parse command line arguments using argparse.
    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Find git repositories in a directory with optional user filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find all repos
  python git_repo_finder.py /home/user/projects
  # Find repos under specific user/organization
  python git_repo_finder.py /home/user/projects --user microsoft
  # Find repos with short flag
  python git_repo_finder.py . -u microsoft
  # Find repos sorted by size (smallest first)
  python git_repo_finder.py . -s asc
  # Find repos sorted by size and save to custom JSON file
  python git_repo_finder.py . -s desc -o my_repos.json
  # Find repos without following symlinks (default)
  python git_repo_finder.py /opt/repos --user github
  # Follow symlinks while searching
  python git_repo_finder.py /opt/repos --follow-symlinks
  # Debug mode to see all repositories and their remote URLs
  python git_repo_finder.py . --user microsoft --verbose
        """,
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Root directory to start searching from (default: current directory)",
    )
    parser.add_argument(
        "-u",
        "--user",
        type=str,
        default=None,
        help="Filter repositories by username/organization from remote URL (case-insensitive)",
    )
    parser.add_argument(
        "-S",
        "--follow-symlinks",
        action="store_true",
        default=False,
        help="Follow symbolic links when traversing directories",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging output and show all repositories with remote URLs",
    )
    parser.add_argument(
        "-s",
        "--sort-by-size",
        dest="sort_by_size",
        choices=["asc", "desc"],
        default=None,
        help="Sort repositories by .git folder size "
        "(asc: smallest first, desc: largest first)",
    )
    parser.add_argument(
        "-o",
        "--out",
        dest="out",
        type=Path,
        help="Save results to custom JSON file path",
    )
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    logger.info(
        f"Parsed arguments: directory={args.directory}, user={args.user}, "
        f"follow_symlinks={args.follow_symlinks}, verbose={args.verbose}, "
        f"sort_by_size={args.sort_by_size}, out={args.out}"
    )
    return args


def linkify(path: str | Path) -> str:
    """
    Create a clickable file link for terminal display.
    Args:
        path: File path to create link for
    Returns:
        Rich-formatted clickable link string
    """
    path = Path(path)
    return f"[bold blue][link=file://{path}]{path.name}[/link][/bold blue]"


def _matches_user_filter(repo_path: Path, user: str) -> bool:
    """
    Check if the repository's remote origin URL matches the user filter.
    Args:
        repo_path: Path to the git repository
        user: Lowercase username/organization to match against
    Returns:
        True if the remote URL contains the user/organization
    """
    remote_url = get_remote_origin_url(repo_path)
    if not remote_url:
        logger.debug(f"No remote URL for {repo_path}, cannot match filter")
        return False

    user_lower = user.lower()
    url_lower = remote_url.lower()

    if f"/{user_lower}/" in url_lower:
        logger.debug(f"Match found: '{user}' in URL path: {remote_url}")
        return True
    if f":{user_lower}/" in url_lower:
        logger.debug(f"Match found: '{user}' in git URL: {remote_url}")
        return True
    if url_lower.endswith(f"/{user_lower}") or url_lower.endswith(f":{user_lower}"):
        logger.debug(f"Match found: '{user}' at end of URL: {remote_url}")
        return True

    logger.debug(f"No match: '{user}' not found in URL: {remote_url}")
    return False


def find_git_repositories(
    base_dir: str | Path,
    *,
    follow_symlinks: bool = False,
    user: str | None = None,
    verbose: bool = False,
    sort_by_size: str | None = None,
    include_size: bool = False,
    include_branch: bool = False,
    include_commit_date: bool = False,
    include_uncommitted: bool = False,
    include_commit_count: bool = False,
    check_remote_tracking: bool = False,
    require_remote: bool = False,
) -> Iterator[RepoInfo]:
    """
    Recursively find all git repositories under base_dir with comprehensive info.

    Args:
        base_dir: Root directory to start searching from
        follow_symlinks: Whether to follow symbolic links
        user: Optional username/organization filter to match in remote URL
        verbose: Whether to show all repositories for debugging
        sort_by_size: Sort repos by .git size before yielding ("asc" or "desc")
        include_size: Calculate .git directory size
        include_branch: Get current branch name
        include_commit_date: Get last commit date
        include_uncommitted: Check for uncommitted changes
        include_commit_count: Get total commit count
        check_remote_tracking: Check if upstream is configured
        require_remote: Only yield repos that have a remote origin URL

    Optimization:
        - Once a .git folder is found, we SKIP walking inside that directory
        - All repository info gathering is done here, not in callers

    Yields:
        RepoInfo dataclasses for matching repositories (sorted if sort_by_size is set)
    """
    base_path = Path(base_dir).resolve()
    if not base_path.is_dir():
        logger.error(f"Not a directory: {base_path}")
        raise NotADirectoryError(f"Not a directory: {base_path}")

    logger.info(f"Starting repository search in: {base_path}")
    if user:
        logger.info(f"Applying user filter based on remote URL: '{user}'")
    if sort_by_size:
        logger.info(f"Will sort repositories by size: {sort_by_size}")

    # Handle case where base_path itself is a git repo
    if is_git_repository(base_path):
        if not user or _matches_user_filter(base_path, user):
            logger.info(f"Base path itself is a git repository: {base_path}")
            info = get_repo_info(
                base_path,
                include_size=include_size or sort_by_size is not None,
                include_branch=include_branch,
                include_commit_date=include_commit_date,
                include_uncommitted=include_uncommitted,
                include_commit_count=include_commit_count,
                check_remote_tracking=check_remote_tracking,
            )
            if not require_remote or info.remote_url:
                yield info
        return

    visited: set[Path] = set()
    filtered_count = 0
    total_repos_found = 0
    no_remote_count = 0

    def walk(start: Path) -> Generator[RepoInfo, None, None]:
        nonlocal filtered_count, total_repos_found, no_remote_count
        try:
            for entry in os.scandir(start):
                try:
                    entry_path = Path(entry.path)
                    if entry_path in visited:
                        continue

                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        if is_git_repository(entry_path):
                            visited.add(entry_path)
                            resolved_path = entry_path.resolve()
                            total_repos_found += 1

                            # Get remote URL early for filtering
                            remote_url = get_remote_origin_url(resolved_path)

                            if verbose:
                                console.print(
                                    f"  [dim]Found repo: {resolved_path.name}[/dim]"
                                )
                                if remote_url:
                                    console.print(
                                        f"  [dim]Remote URL: {remote_url}[/dim]"
                                    )
                                else:
                                    console.print("  [dim]No remote origin[/dim]")
                                    no_remote_count += 1

                            # Apply user filter
                            if user:
                                if not remote_url:
                                    filtered_count += 1
                                    logger.debug(
                                        f"Filtered out (no remote): {resolved_path}"
                                    )
                                    if verbose:
                                        console.print(
                                            "  [yellow]✗ Filtered out (no remote URL)[/yellow]"
                                        )
                                    continue
                                if not _matches_user_filter(resolved_path, user):
                                    filtered_count += 1
                                    logger.debug(f"Filtered out: {resolved_path}")
                                    if verbose:
                                        console.print(
                                            "  [yellow]✗ Filtered out (URL doesn't match)[/yellow]"
                                        )
                                    continue

                            # Apply require_remote filter
                            if require_remote and not remote_url:
                                filtered_count += 1
                                logger.debug(
                                    f"Filtered out (require_remote=True, no URL): {resolved_path}"
                                )
                                continue

                            if verbose and user:
                                console.print("  [green]✓ Matches filter[/green]")

                            # Gather all requested info
                            repo_info = get_repo_info(
                                resolved_path,
                                include_size=include_size or sort_by_size is not None,
                                include_branch=include_branch,
                                include_commit_date=include_commit_date,
                                include_uncommitted=include_uncommitted,
                                include_commit_count=include_commit_count,
                                check_remote_tracking=check_remote_tracking,
                            )

                            logger.debug(f"Found matching repository: {resolved_path}")
                            yield repo_info
                            continue

                        yield from walk(entry_path)
                except (PermissionError, OSError) as e:
                    logger.debug(f"Permission denied for: {entry.path} - {e}")
                    continue
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot access directory: {start} - {e}")

    # If sorting is requested, collect all repos first
    if sort_by_size:
        repos_buffer = list(walk(base_path))

        # Sort by size (None values go last for asc, first for desc)
        def sort_key(info: RepoInfo) -> tuple[bool, int]:
            """Sort key: (is_none, size) - None sizes go last."""
            return (info.size_bytes is None, info.size_bytes or 0)

        reverse = sort_by_size == "desc"
        repos_buffer.sort(key=sort_key, reverse=reverse)

        logger.info(f"Sorted {len(repos_buffer)} repositories by size ({sort_by_size})")

        yield from repos_buffer
    else:
        yield from walk(base_path)

    # Log summary statistics
    logger.info(f"Total repositories found: {total_repos_found}")
    if no_remote_count > 0:
        logger.info(f"Repositories without remote origin: {no_remote_count}")
    if user and filtered_count > 0:
        logger.info(f"Filtered out {filtered_count} repositories not matching '{user}'")
        logger.info(
            f"Remaining matching repositories: {total_repos_found - filtered_count}"
        )


def print_git_repositories(
    base_dir: str | Path,
    follow_symlinks: bool = False,
    user: str | None = None,
    verbose: bool = False,
    sort_by_size: str | None = None,
    output_path: Path | None = None,
) -> None:
    """
    Print all found git repositories with optional user filtering.

    This is now a thin wrapper around find_git_repositories that handles
    display formatting and JSON output.

    Args:
        base_dir: Root directory to start searching from
        follow_symlinks: Whether to follow symbolic links
        user: Optional username/organization filter based on remote URL
        verbose: Whether to show verbose output
        sort_by_size: Sort repos by .git size ("asc" or "desc")
        output_path: Optional custom output file path
    """
    filter_msg = f" (filtered by remote URL: {user})" if user else ""
    console.print(
        f"[bold cyan]Searching git repositories in:[/bold cyan] {base_dir}{filter_msg}\n"
    )

    if verbose and user:
        console.print(
            "[yellow]Verbose mode: Showing all repositories and filtering decisions[/yellow]\n"
        )

    # All the heavy lifting is now in find_git_repositories
    repos = list(
        find_git_repositories(
            base_dir,
            follow_symlinks=follow_symlinks,
            user=user,
            verbose=verbose,
            sort_by_size=sort_by_size,
            include_size=True,  # Always include size for display
            require_remote=True,  # Only show repos with remote URLs
        )
    )

    # Display sorting info if requested
    if sort_by_size and repos:
        console.print("[bold]Repositories sorted by size:[/bold]")
        for i, repo_info in enumerate(repos, 1):
            console.print(f"  {i:3d}. {repo_info.name:40s} → {repo_info.size_display}")
        console.print()

    # Display and collect results
    results = []
    for repo_info in repos:
        clickable_name = linkify(repo_info.path)
        size_suffix = (
            f" [dim]({repo_info.size_human})[/dim]" if repo_info.size_human else ""
        )

        if user and repo_info.remote_url:
            highlighted_url = _highlight_user_in_url(repo_info.remote_url, user)
            console.print(f"  • {clickable_name}{size_suffix} -> {highlighted_url}")
        else:
            console.print(
                f"  • {clickable_name}{size_suffix} -> {repo_info.remote_url or 'No remote'}"
            )

        results.append(repo_info.to_dict())

    # Save results
    input_config = {
        "user_filter": user,
        "follow_symlinks": follow_symlinks,
        "verbose": verbose,
        "sort_by_size": sort_by_size,
    }
    target_dir = Path(base_dir).resolve()
    json_path = save_results_to_json(results, target_dir, input_config, output_path)

    # Summary
    count = len(repos)
    if user:
        if count > 0:
            console.print(
                f"\n[bold]Found [magenta]{count}[/magenta] git repositories "
                f"matching '[yellow]{user}[/yellow]' in remote URL.[/bold]"
            )
        else:
            console.print(
                f"\n[bold yellow]No repositories found with '{user}' in remote URL. "
                f"Try --verbose to debug.[/bold yellow]"
            )
    else:
        console.print(
            f"\n[bold]Found [magenta]{count}[/magenta] git repositories "
            f"with remote URLs.[/bold]"
        )

    console.print(f"[bold green]Results saved to:[/bold green] {linkify(json_path)}")
    logger.info(f"Displayed {count} repositories")


def _highlight_user_in_url(url: str, user: str) -> str:
    """
    Highlight the user/organization part in the remote URL using Rich markup.
    Args:
        url: Remote URL string
        user: Username/organization to highlight
    Returns:
        Rich-formatted string with highlighted user
    """
    patterns = [
        (
            rf"/({re.escape(user)})/",
            r"/\[yellow bold\]\1\[/yellow bold\]/",
        ),
        (
            rf":({re.escape(user)})/",
            r":\[yellow bold\]\1\[/yellow bold\]/",
        ),
    ]
    highlighted_url = url
    for pattern, replacement in patterns:
        if re.search(pattern, highlighted_url, re.IGNORECASE):
            highlighted_url = re.sub(
                pattern, replacement, highlighted_url, flags=re.IGNORECASE
            )
            break
    return highlighted_url


def save_results_to_json(
    results: list[dict],
    target_dir: Path,
    input_config: dict[str, str | bool | None],
    output_path: Path | None = None,
) -> Path:
    """
    Save repository results to a JSON file.

    Args:
        results: List of repository info dictionaries
        target_dir: Directory to save the JSON file (used as fallback)
        input_config: Dictionary containing input configuration (user_filter, etc.)
        output_path: Optional custom output path. If a directory, saves
                     _git_repo_finder_results.json inside it. If a file, saves directly.
    Returns:
        Path to the saved JSON file
    """
    if output_path:
        resolved = output_path.resolve()
        if resolved.is_dir() or output_path.suffix == "":
            # Treat as directory - save with default filename inside it
            json_path = resolved / "_git_repo_finder_results.json"
        else:
            # Treat as file path
            json_path = resolved
        json_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        json_filename = "_git_repo_finder_results.json"
        json_path = target_dir / json_filename

    json_data = {
        "search_directory": str(target_dir),
        "input": input_config,
        "timestamp": datetime.now().isoformat(),
        "total_repositories": len(results),
        "repositories": results,
    }
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to: {json_path}")
        return json_path
    except Exception as e:
        logger.error(f"Failed to save JSON file: {e}")
        raise


if __name__ == "__main__":
    try:
        args = get_args()
        logger.info("Starting git repository finder")
        logger.debug(f"Configuration: {vars(args)}")

        # Resolve target directory
        target_dir = Path(args.directory).expanduser().resolve()

        # Resolve output path with directory/file detection
        output_path = None
        if args.out is not None:
            out = args.out.expanduser().resolve()
            if out.is_dir() or args.out.suffix == "":
                # Treat as directory
                output_path = out / "_git_repo_finder_results.json"
            else:
                # Treat as file
                output_path = out

        print_git_repositories(
            args.directory,
            follow_symlinks=args.follow_symlinks,
            user=args.user,
            verbose=args.verbose,
            sort_by_size=args.sort_by_size,
            output_path=output_path,
        )
    except NotADirectoryError as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Directory error: {e}")
        import sys

        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Search interrupted by user.[/yellow]")
        logger.info("Search interrupted by user")
        import sys

        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error occurred")
        import sys

        sys.exit(1)
