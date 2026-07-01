from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
from collections.abc import Generator, Iterator
from datetime import datetime
from pathlib import Path

from rich.console import Console

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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
        "-s",
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

    args = parser.parse_args()

    # Configure logging level based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    logger.info(
        f"Parsed arguments: directory={args.directory}, user={args.user}, "
        f"follow_symlinks={args.follow_symlinks}, verbose={args.verbose}"
    )

    return args


def is_git_repository(path: Path) -> bool:
    """
    Check if the given path is the root of a git repository.
    Looks for .git/HEAD file (most reliable lightweight check).
    """
    return (path / ".git" / "HEAD").is_file()


def get_remote_origin_url(repo_path: Path) -> str | None:
    """
    Get the remote origin URL for a git repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        Remote origin URL string or None if not found/error
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip()
            logger.debug(f"Remote URL for {repo_path}: {url}")
            return url
        else:
            logger.debug(f"No remote origin found for {repo_path}")
            return None

    except subprocess.TimeoutExpired:
        logger.debug(f"Timeout getting remote URL for {repo_path}")
        return None
    except Exception as e:
        logger.debug(f"Error getting remote URL for {repo_path}: {e}")
        return None


def linkify(path: str | Path) -> str:
    """
    Create a clickable file link for terminal display.

    Args:
        path: File path to create link for

    Returns:
        Rich-formatted clickable link string
    """
    path = Path(path)
    # Provide clickable file link with basename (for rich/terminal that support it)
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

    # Normalize both for comparison
    user_lower = user.lower()
    url_lower = remote_url.lower()

    # Check for the user/organization in the URL
    # This handles various URL formats:
    # https://github.com/microsoft/vscode.git
    # git@github.com:microsoft/vscode.git
    # https://github.com/Microsoft/TypeScript

    # Check if the user appears as a path component in the URL
    if f"/{user_lower}/" in url_lower:
        logger.debug(f"Match found: '{user}' in URL path: {remote_url}")
        return True

    # Check for git@ format: git@github.com:user/repo.git
    if f":{user_lower}/" in url_lower:
        logger.debug(f"Match found: '{user}' in git URL: {remote_url}")
        return True

    # Check if the URL ends with user/repo format
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
) -> Iterator[Path]:
    """
    Recursively find all git repositories under base_dir.

    Args:
        base_dir: Root directory to start searching from
        follow_symlinks: Whether to follow symbolic links
        user: Optional username/organization filter to match in remote URL
        verbose: Whether to show all repositories for debugging

    Optimization:
        - Once a .git folder is found, we SKIP walking inside that directory
          (no need to look for nested repos unless you explicitly want them)

    Yields:
        Absolute paths to git repository roots that match the filter
    """
    base_path = Path(base_dir).resolve()

    if not base_path.is_dir():
        logger.error(f"Not a directory: {base_path}")
        raise NotADirectoryError(f"Not a directory: {base_path}")

    logger.info(f"Starting repository search in: {base_path}")

    if user:
        logger.info(f"Applying user filter based on remote URL: '{user}'")

    if is_git_repository(base_path):
        if not user or _matches_user_filter(base_path, user):
            logger.info(f"Base path itself is a git repository: {base_path}")
            yield base_path
        return

    visited: set[Path] = set()
    filtered_count = 0
    total_repos_found = 0
    no_remote_count = 0

    def walk(start: Path) -> Generator[Path, None, None]:
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

                            # Get remote URL for debugging
                            remote_url = get_remote_origin_url(resolved_path)

                            # Print ALL repositories in verbose mode for debugging
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

                            # Apply user filter if specified
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

                            if verbose and user:
                                console.print("  [green]✓ Matches filter[/green]")

                            logger.debug(f"Found matching repository: {resolved_path}")
                            yield resolved_path
                            continue

                        yield from walk(entry_path)

                except (PermissionError, OSError) as e:
                    logger.debug(f"Permission denied for: {entry.path} - {e}")
                    continue

        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot access directory: {start} - {e}")

    yield from walk(base_path)

    logger.info(f"Total repositories found: {total_repos_found}")
    if no_remote_count > 0:
        logger.info(f"Repositories without remote origin: {no_remote_count}")
    if user and filtered_count > 0:
        logger.info(f"Filtered out {filtered_count} repositories not matching '{user}'")
        logger.info(
            f"Remaining matching repositories: {total_repos_found - filtered_count}"
        )


def save_results_to_json(
    results: list[dict],
    target_dir: Path,
    user_filter: str | None = None,
) -> Path:
    """
    Save repository results to a JSON file in the target directory.
    Always overwrites the same file: git_repos_results.json

    Args:
        results: List of repository info dictionaries
        target_dir: Directory to save the JSON file
        user_filter: Optional user filter that was applied

    Returns:
        Path to the saved JSON file
    """
    # Always use the same filename - overwrites on each run
    json_filename = "git_repos_results.json"
    json_path = target_dir / json_filename

    # Prepare data for JSON
    json_data = {
        "search_directory": str(target_dir),
        "user_filter": user_filter,
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


def print_git_repositories(
    base_dir: str | Path,
    follow_symlinks: bool = False,
    user: str | None = None,
    verbose: bool = False,
) -> None:
    """
    Print all found git repositories with optional user filtering.

    Args:
        base_dir: Root directory to start searching from
        follow_symlinks: Whether to follow symbolic links
        user: Optional username/organization filter based on remote URL
        verbose: Whether to show verbose output
    """
    filter_msg = f" (filtered by remote URL: {user})" if user else ""
    console.print(
        f"[bold cyan]Searching git repositories in:[/bold cyan] {base_dir}{filter_msg}\n"
    )

    if verbose and user:
        console.print(
            "[yellow]Verbose mode: Showing all repositories and filtering decisions[/yellow]\n"
        )

    results = []
    count = 0

    for repo in find_git_repositories(
        base_dir, follow_symlinks=follow_symlinks, user=user, verbose=verbose
    ):
        # Get remote URL for display
        remote_url = get_remote_origin_url(repo)

        # Create clickable link for the repository name
        clickable_name = linkify(repo)

        if remote_url:
            # Highlight user in URL if filter is applied
            if user:
                highlighted_url = _highlight_user_in_url(remote_url, user)
                console.print(f"  • {clickable_name} -> {highlighted_url}")
            else:
                console.print(f"  • {clickable_name} -> {remote_url}")
        else:
            console.print(f"  • {clickable_name} -> [yellow]No remote origin[/yellow]")

        # Collect results for JSON
        results.append({"name": repo.name, "path": str(repo), "remote_url": remote_url})

        count += 1

    # Save results to JSON
    target_dir = Path(base_dir).resolve()
    json_path = save_results_to_json(results, target_dir, user)

    # Show summary
    if user:
        if count > 0:
            console.print(
                f"\n[bold]Found [magenta]{count}[/magenta] git repositories matching '[yellow]{user}[/yellow]' in remote URL.[/bold]"
            )
        else:
            console.print(
                f"\n[bold yellow]No repositories found with '{user}' in remote URL. Try --verbose to debug.[/bold yellow]"
            )
    else:
        console.print(
            f"\n[bold]Found [magenta]{count}[/magenta] git repositories.[/bold]"
        )

    # Show saved file location with clickable link
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
    # Pattern to match user/organization in different URL formats
    patterns = [
        (
            rf"/({re.escape(user)})/",
            r"/\[yellow bold\]\1\[/yellow bold\]/",
        ),  # https://github.com/user/repo
        (
            rf":({re.escape(user)})/",
            r":\[yellow bold\]\1\[/yellow bold\]/",
        ),  # git@github.com:user/repo
    ]

    highlighted_url = url
    for pattern, replacement in patterns:
        if re.search(pattern, highlighted_url, re.IGNORECASE):
            highlighted_url = re.sub(
                pattern, replacement, highlighted_url, flags=re.IGNORECASE
            )
            break

    return highlighted_url


if __name__ == "__main__":
    try:
        args = get_args()

        logger.info("Starting git repository finder")
        logger.debug(f"Configuration: {vars(args)}")

        print_git_repositories(
            args.directory,
            follow_symlinks=args.follow_symlinks,
            user=args.user,
            verbose=args.verbose,
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
