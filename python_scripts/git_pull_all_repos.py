"""
git_pull_all_repos.py – Pull all Git repositories under a directory.
Features:
  • Resumable: state is saved after every repo; use --continue after Ctrl+C.
  • Retry failed: use --only-failed to retry only previously failed repos.
  • Time-based shallow clone (--shallow-since) or full history.
  • STRICT RECLONE: Removes and reclones repos if safe (no uncommitted/stashed work).
    Ignores local branches, unpushed commits, or detached HEADs.
  • SMART CHECK: Only reclones when there are actual updates to fetch.
Usage examples:
  # Pull all repos (shallow since 1 year ago, with reclone optimization)
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
  # Disable reclone optimization (use traditional fetch/merge)
  python git_pull_all_repos.py /path/to/repos --no-reclone
"""

from __future__ import annotations

import argparse
import json
import shutil
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
DEFAULT_FETCH_TIMEOUT = 60


def _safe_strip(text: str | bytes | None) -> str:
    """Safely strip subprocess output that may be None."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace").strip()
    return str(text).strip()


def _check_repo_safety_for_reclone(repo_path: Path) -> tuple[bool, str]:
    """Check if repository is safe to reclone.

    In STRICT mode, we only block if there is UNSAVED WORK that would be lost.
    We IGNORE local branches, unpushed commits, or detached HEADs because
    the reclone will intentionally overwrite them with the remote state.

    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    # Check 1: Uncommitted changes in working directory (CRITICAL)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        if result.stdout.strip():
            return False, "Has uncommitted changes in working directory"
    except Exception as e:
        return False, f"Failed to check status: {e}"

    # Check 2: Staged changes (CRITICAL)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        if result.stdout.strip():
            return False, "Has staged changes not yet committed"
    except Exception as e:
        return False, f"Failed to check staged changes: {e}"

    # Check 3: Stashed changes (CRITICAL - often forgotten work)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "stash", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        if result.stdout.strip():
            stash_count = len(result.stdout.strip().split("\n"))
            return False, f"Has {stash_count} stashed change(s)"
    except Exception as e:
        return False, f"Failed to check stashes: {e}"

    # All checks passed - safe to reclone
    # Note: We intentionally DO NOT check for local branches or unpushed commits
    # because the user wants a strict sync with remote.
    return True, ""


def _check_if_updates_available(
    repo_path: Path,
    branch: str,
    fetch_timeout: int = DEFAULT_FETCH_TIMEOUT,
) -> tuple[bool, str]:
    """Check if there are actually updates to fetch from remote."""
    try:
        # Fetch remote refs without merging (fast operation)
        result = subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=fetch_timeout,
            check=True,
        )

        # Check if there are any new commits
        if result.stderr or result.stdout:
            combined_output = (result.stdout + result.stderr).lower()
            if any(
                indicator in combined_output
                for indicator in [
                    "new tag",
                    "new branch",
                    "from",
                    "to",
                    "updating",
                    "remote:",
                    "counting objects",
                    "compressing objects",
                ]
            ):
                return True, "Updates available from remote"

        # Double-check by comparing local vs remote commit hashes
        try:
            local_hash = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()

            remote_hash = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", f"origin/{branch}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()

            if local_hash != remote_hash:
                return (
                    True,
                    f"Local ({local_hash[:8]}) differs from remote ({remote_hash[:8]})",
                )
            else:
                return False, "Already up to date"
        except Exception:
            return True, "Cannot verify, assuming updates available"

    except subprocess.TimeoutExpired:
        return True, "Fetch timed out, will attempt reclone"
    except Exception as e:
        return True, f"Update check failed: {e}, will attempt reclone"


def _check_shallow_boundary(
    repo_path: Path, branch: str, shallow_since: str | None
) -> dict:
    """Compare local and remote tip dates to verify shallow completeness."""
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


def _reclone_repo(
    repo_path: Path,
    shallow_since: str | None = DEFAULT_SHALLOW_SINCE,
    fetch_timeout: int = DEFAULT_FETCH_TIMEOUT,
) -> tuple[Literal["success", "failed", "error"], str, dict | None]:
    """Safely remove and reclone repository for faster updates."""
    try:
        # Get remote URL before removing
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        remote_url = result.stdout.strip()

        # Get current branch (mostly for logging, reclone will use default unless specified)
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        current_branch = result.stdout.strip()
        if current_branch == "HEAD":
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
                timeout=5,
                check=True,
            )
            current_branch = result.stdout.strip().replace("origin/", "")

        console.print(f"  [dim]Remote: {remote_url}, Branch: {current_branch}[/dim]")

        # Remove the entire repository directory
        console.print(f"  [cyan]Removing old repository...[/cyan]")
        shutil.rmtree(repo_path)

        # Clone with shallow-since
        clone_cmd = ["git", "clone"]
        if shallow_since:
            clone_cmd.extend(["--shallow-since", shallow_since])
        clone_cmd.extend([remote_url, str(repo_path)])

        console.print(f"  [cyan]Cloning with shallow-since='{shallow_since}'...[/cyan]")
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
            timeout=fetch_timeout * 2,
            check=True,
        )

        # Checkout the correct branch if needed
        if current_branch and current_branch not in ("master", "main"):
            try:
                subprocess.run(
                    ["git", "-C", str(repo_path), "checkout", current_branch],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            except subprocess.CalledProcessError:
                pass  # Branch may not exist on remote

        # Verify the clone
        shallow_status = _check_shallow_boundary(
            repo_path, current_branch or "HEAD", shallow_since
        )

        return (
            "success",
            f"Recloned successfully (branch: {current_branch})",
            shallow_status,
        )

    except subprocess.TimeoutExpired:
        return "failed", f"Clone timed out after {fetch_timeout * 2}s", None
    except subprocess.CalledProcessError as e:
        stderr = _safe_strip(e.stderr)
        return "failed", f"Clone failed: {stderr[:300]}", None
    except Exception as e:
        return "error", f"Reclone exception: {e}", None


def run_git_pull(
    repo_path: Path,
    shallow_since: str | None = DEFAULT_SHALLOW_SINCE,
    fetch_timeout: int = DEFAULT_FETCH_TIMEOUT,
    use_reclone: bool = True,
) -> tuple[Literal["success", "up-to-date", "failed", "error"], str, dict | None]:
    """Execute git pull using strict reclone strategy."""

    if use_reclone and shallow_since:
        # Step 1: Check Safety (Only uncommitted/stashed work blocks us)
        is_safe, safety_reason = _check_repo_safety_for_reclone(repo_path)

        if not is_safe:
            return "error", f"Unsafe to reclone: {safety_reason}", None

        console.print(f"  [green]✓ Safe to reclone[/green]")

        # Step 2: Get Branch for Update Check
        branch = None
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
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
                    timeout=5,
                    check=True,
                )
                branch = result.stdout.strip().replace("origin/", "")
            except Exception:
                branch = "HEAD"

        # Step 3: Check for Updates
        console.print(f"  [dim]Checking for updates on branch '{branch}'...[/dim]")
        has_updates, update_message = _check_if_updates_available(
            repo_path, branch, fetch_timeout
        )

        if not has_updates:
            console.print(f"  [blue]→ {update_message}[/blue]")
            shallow_status = _check_shallow_boundary(repo_path, branch, shallow_since)
            return "up-to-date", update_message, shallow_status
        else:
            console.print(f"  [green]✓ {update_message}[/green]")
            console.print(f"  [cyan]Proceeding with reclone...[/cyan]")
            return _reclone_repo(repo_path, shallow_since, fetch_timeout)

    else:
        return "error", "Reclone optimization disabled or no shallow-since set", None


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
    current_run_paths: set[str] = set()
    for paths_list in grouped_results.values():
        current_run_paths.update(paths_list)
    final_grouped: dict[str, list[str]] = {
        "success": [],
        "up-to-date": [],
        "failed": [],
        "error": [],
    }
    if previous_state:
        prev_grouped = previous_state.get("grouped_results", {})
        for k in final_grouped:
            final_grouped[k] = [
                path
                for path in prev_grouped.get(k, [])
                if path not in current_run_paths
            ]
    for k in grouped_results:
        final_grouped[k].extend(grouped_results[k])
    final_failed = []
    if previous_state:
        final_failed = [
            entry
            for entry in previous_state.get("failed", [])
            if entry["repoPath"] not in current_run_paths
        ]
        kept_count = len(final_failed)
        removed_count = len(previous_state.get("failed", [])) - kept_count
        if removed_count > 0:
            console.print(
                f"[dim]State merge: cleaned {removed_count} resolved/reprocessed "
                f"entries from failed list, keeping {kept_count} unresolved[/dim]"
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
    use_reclone: bool = True,
    state_path: Path | None = None,
) -> None:
    """
    Find all git repositories under target_dir and run `git pull` in each.
    Uses strict reclone optimization when safe (no uncommitted/stashed work).
    """
    base_path = Path(target_dir).expanduser().resolve()
    target_dir_str = str(base_path)

    # Determine state file location
    if state_path is not None:
        state_path = state_path.expanduser().resolve()
    elif out_path is not None:
        state_path = out_path.expanduser().resolve()
    else:
        state_path = base_path / "_git_pull_all_repos_state.json"

    mode_line = (
        f'[bold yellow]Shallow mode enabled: --shallow-since="{shallow_since}"[/bold yellow]'
        if shallow_since
        else "[bold yellow]Full history mode (no shallow-since)[/bold yellow]"
    )
    reclone_line = (
        "[bold green]Strict Reclone: ENABLED[/bold green]"
        if use_reclone and shallow_since
        else "[dim]Reclone optimization: disabled[/dim]"
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
        f"{reclone_line}\n"
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
                repo, shallow_since=shallow_since, use_reclone=use_reclone
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
        "--state-path",
        dest="state_path",
        type=Path,
        default=None,
        help="Custom path for the state JSON file. Overrides --out if both are specified. "
        "Useful for storing state outside the target directory.",
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
    parser.add_argument(
        "--no-reclone",
        dest="no_reclone",
        action="store_true",
        help="Disable reclone optimization (use traditional fetch/merge only)",
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
    use_reclone = not args.no_reclone
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
    console.print(
        "[bold]Reclone:[/bold] "
        + ("[green]Enabled[/green]" if use_reclone else "[dim]Disabled[/dim]")
    )
    git_pull_all_repos(
        args.target_dir,
        out_path=out_path,
        shallow_since=shallow_since_value,
        sort_by_size=args.sort_by_size,
        continue_from_last=args.continue_from_last,
        only_failed=args.only_failed,
        use_reclone=use_reclone,
        state_path=args.state_path,
    )


if __name__ == "__main__":
    main()
