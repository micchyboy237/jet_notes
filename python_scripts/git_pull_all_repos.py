"""
git_pull_all_repos.py – Pull all Git repositories under a directory.
Features:
  • Resumable: state is saved after every repo; use --continue after Ctrl+C.
  • Retry failed: use --only-failed to retry only previously failed repos.
  • Time-based shallow fetch (--shallow-since) or full history.
  • Shallow boundary verification: detects if remote has commits outside
    the shallow-since window that were not fetched.
  • Merge conflicts are caught and recorded as "error" state.
  • Sort by .git size to prioritize small/large repos.
Usage examples:
  # Pull all repos (shallow since 1 year ago)
  python git_pull_all_repos.py /path/to/repos
  # Custom time window
  python git_pull_all_repos.py /path/to/repos --shallow-since "6 months ago"
  # Full history fetch
  python git_pull_all_repos.py /path/to/repos --shallow-since full
  # Resume after interruption
  python git_pull_all_repos.py /path/to/repos --continue
  # Retry only failed repos from last run
  python git_pull_all_repos.py /path/to/repos --only-failed
  # Sorted largest-first, custom state file
  python git_pull_all_repos.py /path/to/repos -s desc -o state.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from git_repo_finder import find_git_repositories
from git_repo_utils import RepoInfo
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()

DEFAULT_SHALLOW_SINCE = "1 year ago"


def _check_shallow_boundary(
    repo_path: Path, branch: str, shallow_since: str | None
) -> dict:
    """Compare local and remote tip dates to verify shallow completeness.
    Returns a dict with shallow status information.
    Only meaningful when shallow_since is set.
    """
    status: dict = {
        "mode": "shallow-since" if shallow_since else "full",
        "value": shallow_since,
        "remote_has_unfetched": None,
        "local_tip_date": None,
        "remote_tip_date": None,
    }
    if not shallow_since:
        status["remote_has_unfetched"] = False
        return status

    try:
        local_result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1", "--format=%aI", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        status["local_tip_date"] = local_result.stdout.strip() or None
    except Exception:
        pass

    try:
        remote_result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                "-1",
                "--format=%aI",
                f"origin/{branch}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        status["remote_tip_date"] = remote_result.stdout.strip() or None
    except Exception:
        pass

    if status["local_tip_date"] and status["remote_tip_date"]:
        status["remote_has_unfetched"] = (
            status["local_tip_date"] != status["remote_tip_date"]
        )
    else:
        status["remote_has_unfetched"] = None

    return status


def run_git_pull(
    repo_path: Path,
    shallow_since: str | None = DEFAULT_SHALLOW_SINCE,
) -> tuple[Literal["success", "up-to-date", "failed", "error"], str, dict | None]:
    """Execute git pull with automatic fast-forward/force-push recovery.
    Handles stale .git lock files by removing them once.
    Timeouts and network errors are recorded as 'failed' and move on immediately.
    Detached HEAD repos fall back to origin/HEAD or skip merge gracefully.
    Returns (status, message, shallow_status_dict).
    """
    fetch_cmd = ["git", "-C", str(repo_path), "fetch"]
    if shallow_since:
        fetch_cmd.extend(["--shallow-since", shallow_since])

    try:
        subprocess.run(
            fetch_cmd, capture_output=True, text=True, timeout=120, check=True
        )
    except subprocess.TimeoutExpired:
        return "failed", "Fetch timed out after 120s", None
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()
        # Handle stale lock file once
        if "Unable to create" in stderr and ".git/shallow.lock" in stderr:
            lock_path = repo_path / ".git" / "shallow.lock"
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    console.print(
                        f" [green]✓[/green] [dim]Removed stale lock file[/dim]"
                    )
                    # Single retry after lock cleanup only
                    try:
                        subprocess.run(
                            fetch_cmd,
                            capture_output=True,
                            text=True,
                            timeout=120,
                            check=True,
                        )
                    except Exception as retry_err:
                        return (
                            "failed",
                            f"Fetch failed after lock cleanup: {retry_err}",
                            None,
                        )
                except OSError as unlink_error:
                    return "failed", f"Failed to remove lock: {unlink_error}", None
            else:
                return "failed", f"Fetch failed: {stderr}", None
        return "failed", f"Fetch failed: {stderr}", None
    except Exception as e:
        return "failed", f"Fetch exception: {e}", None

    # Determine branch with detached HEAD fallback
    branch = None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        branch = result.stdout.strip()
        if branch == "HEAD":
            branch = None
    except Exception:
        pass

    if not branch:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "symbolic-ref",
                    "--short",
                    "refs/remotes/origin/HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            branch = result.stdout.strip().replace("origin/", "")
        except Exception:
            shallow_status = _check_shallow_boundary(repo_path, "HEAD", shallow_since)
            return (
                "success",
                "Fetched successfully (detached HEAD, no merge attempted)",
                shallow_status,
            )

    # Fast-forward merge
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "merge", "--ff-only", f"origin/{branch}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        if "Already up to date" in result.stdout:
            shallow_status = _check_shallow_boundary(repo_path, branch, shallow_since)
            return "up-to-date", result.stdout.strip(), shallow_status
        shallow_status = _check_shallow_boundary(repo_path, branch, shallow_since)
        return "success", result.stdout.strip(), shallow_status
    except subprocess.CalledProcessError as merge_err:
        merge_stderr = merge_err.stderr.strip()
        conflict_indicators = (
            "CONFLICT",
            "Automatic merge failed",
            "Merge conflict",
            "conflict",
        )
        is_conflict = any(
            ind.lower() in merge_stderr.lower() for ind in conflict_indicators
        )
        if is_conflict:
            try:
                subprocess.run(
                    ["git", "-C", str(repo_path), "merge", "--abort"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except Exception:
                pass
            return (
                "error",
                f"Merge conflict on branch '{branch}': {merge_stderr[:300]}",
                None,
            )
        # Non-conflict merge failure falls through to hard reset

    # Hard reset fallback for force-pushed branches
    try:
        subprocess.run(
            ["git", "-C", str(repo_path), "reset", "--hard", f"origin/{branch}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        shallow_status = _check_shallow_boundary(repo_path, branch, shallow_since)
        return "success", "Hard reset to origin (force-push recovery)", shallow_status
    except subprocess.CalledProcessError as e:
        return "failed", f"Reset failed: {e.stderr.strip()}", None
    except Exception as e:
        return "error", f"Exception during reset: {e}", None


def _write_state_file(state_path: Path, state: dict) -> None:
    """Atomically write the complete state to a single JSON file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp_path.replace(state_path)


def _load_state_file(state_path: Path) -> dict | None:
    """Load existing state from JSON file if it exists."""
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except (json.JSONDecodeError, KeyError) as e:
            console.print(f"[yellow]Warning: Could not load state file: {e}[/yellow]")
            return None
    return None


def _build_state(
    progress_data: dict[str, dict[str, str]],
    grouped_results: dict[str, list[str]],
    failed_entries: list[dict[str, str]],
    stats: dict[str, int],
    total: int,
    target_dir: str,
    shallow_since: str | None,
    sort_by_size: str | None,
    processed_repos: set[str],
    completed: bool = False,
    previous_state: dict | None = None,
) -> dict:
    """Build the complete state dictionary with proper merging for continue/only-failed."""
    final_stats = dict(stats)
    if previous_state:
        prev_summary = previous_state.get("summary", {})
        for status in ["success", "up-to-date", "failed", "error"]:
            final_stats[status] = final_stats.get(status, 0) + prev_summary.get(
                status, {}
            ).get("count", 0)

    total_for_summary = sum(final_stats.values()) or total

    summary: dict[str, dict[str, float]] = {}
    for status, count in final_stats.items():
        percentage = (
            round((count / total_for_summary * 100), 1)
            if total_for_summary > 0
            else 0.0
        )
        summary[status] = {
            "count": count,
            "percentage": percentage,
        }

    final_grouped: dict[str, list[str]] = {
        "success": [],
        "up-to-date": [],
        "failed": [],
        "error": [],
    }
    if previous_state:
        for k in final_grouped:
            final_grouped[k] = previous_state.get("grouped_results", {}).get(k, [])[:]
    for k in grouped_results:
        final_grouped[k].extend(grouped_results[k])

    final_failed = []
    if previous_state:
        current_failed_paths = {entry["repoPath"] for entry in failed_entries}
        final_failed = [
            entry
            for entry in previous_state.get("failed", [])
            if entry["repoPath"] not in current_failed_paths
        ]
        console.print(
            f"[dim]State merge: keeping {len(final_failed)} previous failed entries, "
            f"replacing {len(current_failed_paths)} with current results[/dim]"
        )
    final_failed.extend(failed_entries)

    return {
        "metadata": {
            "target_directory": target_dir,
            "shallow_since": shallow_since,
            "sort_by_size": sort_by_size,
            "timestamp": datetime.now().isoformat(),
            "completed": completed,
            "total_repositories": total_for_summary,
            "processed_count": len(processed_repos),
        },
        "summary": summary,
        "grouped_results": final_grouped,
        "failed": final_failed,
        "processed_repos": sorted(list(processed_repos)),
        "progress": progress_data,
    }


def _status_label(status: str) -> str:
    """Return Rich-formatted label for a status string."""
    labels = {
        "success": "[green]✓ Success[/green]",
        "up-to-date": "[blue]→ Up to date[/blue]",
        "failed": "[red]✗ Failed[/red]",
        "error": "[red bold]! Error[/red bold]",
    }
    return labels.get(status, status)


def git_pull_all_repos(
    target_dir: str | Path = ".",
    out_path: Path | None = None,
    shallow_since: str | None = DEFAULT_SHALLOW_SINCE,
    sort_by_size: str | None = None,
    continue_from_last: bool = False,
    only_failed: bool = False,
) -> None:
    """
    Find all git repositories under target_dir and run `git pull` in each.
    Properly handles state merging for --continue and --only-failed.
    Uses --shallow-since for time-based shallow fetching.
    Verifies shallow boundary and records unfetched commit status in state.
    Merge conflicts are caught and recorded as 'error' status.
    """
    base_path = Path(target_dir).expanduser().resolve()
    target_dir_str = str(base_path)

    if out_path is None:
        state_path = base_path / "_git_pull_all_repos_state.json"
    else:
        state_path = out_path.expanduser().resolve()

    mode_line = (
        f'[bold yellow]Shallow mode enabled: --shallow-since="{shallow_since}"[/bold yellow]'
        if shallow_since
        else "[bold yellow]Full history mode (no shallow-since)[/bold yellow]"
    )

    if continue_from_last:
        console.print(
            "[bold cyan]Mode: Continue from last unprocessed repo[/bold cyan]"
        )
    elif only_failed:
        console.print("[bold cyan]Mode: Only retry failed repos[/bold cyan]")

    console.print(
        f"[bold cyan]Scanning for git repositories in:[/bold cyan] {base_path}\n"
        f"{mode_line}\n"
    )
    console.print(f"[dim]State file: {state_path}[/dim]\n")

    processed_repos: set[str] = set()
    previous_state = None

    if continue_from_last or only_failed:
        existing_state = _load_state_file(state_path)
        if existing_state:
            processed_repos = set(existing_state.get("processed_repos", []))
            previous_state = existing_state
            if continue_from_last:
                console.print(
                    f"[green]Found {len(processed_repos)} previously processed repos. "
                    f"Continuing from where we left off.[/green]\n"
                )
            elif only_failed:
                failed_repos = {
                    entry["repoPath"] for entry in existing_state.get("failed", [])
                }
                console.print(
                    f"[yellow]Found {len(failed_repos)} failed repos from previous run. "
                    f"Will only process those.[/yellow]\n"
                )
        else:
            console.print("[yellow]No previous state found. Starting fresh.[/yellow]\n")
            continue_from_last = False
            only_failed = False

    repos: list[RepoInfo] = list(
        find_git_repositories(
            base_path,
            sort_by_size=sort_by_size,
            include_size=sort_by_size is not None,
            check_remote_tracking=True,
        )
    )

    if only_failed and previous_state:
        failed_paths = {entry["repoPath"] for entry in previous_state.get("failed", [])}
        repos = [repo for repo in repos if str(repo.path) in failed_paths]
        if not repos:
            console.print("[green]No failed repos to retry! Everything passed.[/green]")
            return
    elif continue_from_last:
        repos = [repo for repo in repos if str(repo.path) not in processed_repos]
        if not repos:
            console.print("[green]All repos already processed! Nothing to do.[/green]")
            return

    if sort_by_size:
        console.print("[bold]Pull order (sorted by size):[/bold]")
        for i, repo_info in enumerate(repos, 1):
            console.print(f" {i:3d}. {repo_info.name:40s} → {repo_info.size_display}")
        console.print()

    total_this_run = len(repos)
    grand_total = (
        previous_state.get("metadata", {}).get("total_repositories", total_this_run)
        if previous_state
        else total_this_run
    )

    progress_data: dict[str, dict[str, str]] = (
        previous_state.get("progress", {}) if previous_state else {}
    )
    grouped_results: dict[str, list[str]] = {
        "success": [],
        "up-to-date": [],
        "failed": [],
        "error": [],
    }
    failed_entries: list[dict[str, str]] = []

    if total_this_run == 0:
        console.print("[yellow]No git repositories found.[/yellow]")
        state = _build_state(
            progress_data=progress_data,
            grouped_results=grouped_results,
            failed_entries=failed_entries,
            stats={"success": 0, "up-to-date": 0, "failed": 0, "error": 0},
            total=grand_total,
            target_dir=target_dir_str,
            shallow_since=shallow_since,
            sort_by_size=sort_by_size,
            processed_repos=processed_repos,
            completed=True,
            previous_state=previous_state,
        )
        _write_state_file(state_path, state)
        console.print(f"[dim]State saved to: {state_path}[/dim]")
        return

    console.print(
        f"[bold]Found [magenta]{total_this_run}[/magenta] repositories to process this run. "
        f"(Grand total: {grand_total})[/bold]\n"
    )

    stats = {"success": 0, "up-to-date": 0, "failed": 0, "error": 0}

    def save_state(completed: bool = False) -> None:
        """Save complete state to single JSON file."""
        state = _build_state(
            progress_data=progress_data,
            grouped_results=grouped_results,
            failed_entries=failed_entries,
            stats=stats,
            total=grand_total,
            target_dir=target_dir_str,
            shallow_since=shallow_since,
            sort_by_size=sort_by_size,
            processed_repos=processed_repos,
            completed=completed,
            previous_state=previous_state,
        )
        _write_state_file(state_path, state)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Pulling repositories...", total=total_this_run)
        for repo_info in repos:
            repo = repo_info.path
            short_name = repo_info.name
            repo_key = str(repo)
            progress.update(task, description=f"[cyan]Pulling {short_name}...")

            status, message, shallow_status = run_git_pull(
                repo, shallow_since=shallow_since
            )
            stats[status] += 1
            progress_data[repo_key] = {
                "status": status,
                "message": message,
                "shallow_status": shallow_status,
            }
            grouped_results[status].append(repo_key)
            processed_repos.add(repo_key)

            if status in ("failed", "error"):
                failed_entries.append({"repoPath": repo_key, "message": message})

            save_state()

            icon = {
                "success": "[green]✓[/green]",
                "up-to-date": "[blue]→[/blue]",
                "failed": "[red]✗[/red]",
                "error": "[red bold]![/red bold]",
            }[status]

            # Append shallow boundary warning to display
            shallow_note = ""
            if shallow_status and shallow_status.get("remote_has_unfetched") is True:
                shallow_note = " [yellow]⚠ Remote has commits outside shallow-since window[/yellow]"

            console.print(
                f" {icon} {repo} → "
                f"[dim]{message[:120]}{'...' if len(message) > 120 else ''}[/dim]"
                f"{shallow_note}"
            )
            progress.advance(task)

    save_state(completed=True)

    merged_stats = dict(stats)
    if previous_state:
        prev_summary = previous_state.get("summary", {})
        for status in ["success", "up-to-date", "failed", "error"]:
            merged_stats[status] = merged_stats.get(status, 0) + prev_summary.get(
                status, {}
            ).get("count", 0)

    # Summarize repos with unfetched commits
    unfetched_repos = [
        repo_key
        for repo_key, data in progress_data.items()
        if data.get("shallow_status", {})
        and data["shallow_status"].get("remote_has_unfetched") is True
    ]
    if unfetched_repos:
        console.print(
            f"\n[yellow]⚠ {len(unfetched_repos)} repo(s) have commits outside "
            f"the shallow-since window that were NOT fetched:[/yellow]"
        )
        for repo_key in unfetched_repos:
            ss = progress_data[repo_key]["shallow_status"]
            console.print(
                f"   • {repo_key}  local={ss.get('local_tip_date')}  "
                f"remote={ss.get('remote_tip_date')}"
            )

    if total_this_run > 0:
        table = Table(
            title="Pull Summary (This Run)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")

        status_order = ["success", "up-to-date", "failed", "error"]
        for status in status_order:
            count = stats.get(status, 0)
            perc = (count / total_this_run * 100) if total_this_run > 0 else 0
            label = _status_label(status)
            table.add_row(label, str(count), f"{perc:5.1f}%")

        console.print("\n")
        console.print(table)
        console.print(
            f"\n[bold]Completed processing {total_this_run} repositories this run.[/bold]\n"
            f"[bold green]State saved to:[/bold green] "
            f"[link=file://{state_path}]{state_path}[/link]"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Recursively pull all Git repositories under a directory."
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Target directory to search (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--out",
        dest="out",
        type=Path,
        help="Save state to JSON file or directory. "
        "If a directory, saves _git_pull_all_repos_state.json inside it. "
        "If a file path, saves directly to that file. "
        "(default: _git_pull_all_repos_state.json in target directory)",
    )
    parser.add_argument(
        "--shallow-since",
        dest="shallow_since",
        type=str,
        default=DEFAULT_SHALLOW_SINCE,
        metavar="DATE",
        help=(
            "Use 'git fetch --shallow-since=DATE' instead of full history. "
            f'Default: "{DEFAULT_SHALLOW_SINCE}". '
            "Pass empty string or 'full' to fetch complete history."
        ),
    )
    parser.add_argument(
        "-s",
        "--sort-by-size",
        dest="sort_by_size",
        choices=["asc", "desc"],
        default=None,
        help="Sort repositories by .git folder size before pulling "
        "(asc: smallest first, desc: largest first)",
    )
    parser.add_argument(
        "--continue",
        dest="continue_from_last",
        action="store_true",
        help="Continue from the last unprocessed repository using existing state file",
    )
    parser.add_argument(
        "--only-failed",
        dest="only_failed",
        action="store_true",
        help="Only retry repositories that failed in the previous run",
    )

    args = parser.parse_args()

    target_dir = Path(args.target_dir).expanduser().resolve()

    if args.out is not None:
        out_path = args.out.expanduser().resolve()
        if out_path.is_dir() or args.out.suffix == "":
            out_path = out_path / "_git_pull_all_repos_state.json"
    else:
        out_path = target_dir / "_git_pull_all_repos_state.json"

    shallow_since_value: str | None = args.shallow_since
    if shallow_since_value and shallow_since_value.lower() in ("full", "none", ""):
        shallow_since_value = None

    console.print(
        f"[bold]Target directory:[/bold] [link=file://{target_dir}]{target_dir}[/link]"
    )
    console.print(f"[bold]State file:[/bold] [link=file://{out_path}]{out_path}[/link]")
    console.print(
        "[bold]Pull mode:[/bold] "
        + (
            f'shallow (--shallow-since="{shallow_since_value}")'
            if shallow_since_value
            else "full history"
        )
    )

    git_pull_all_repos(
        args.target_dir,
        out_path=out_path,
        shallow_since=shallow_since_value,
        sort_by_size=args.sort_by_size,
        continue_from_last=args.continue_from_last,
        only_failed=args.only_failed,
    )


if __name__ == "__main__":
    main()
