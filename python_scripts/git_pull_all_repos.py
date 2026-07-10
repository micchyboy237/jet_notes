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

DEFAULT_DEPTH = 1


def run_git_pull(
    repo_path: Path,
    depth: int | None = DEFAULT_DEPTH,
) -> tuple[Literal["success", "up-to-date", "failed", "error"], str]:
    """Execute git pull with automatic fast-forward/force-push recovery."""
    fetch_cmd = ["git", "-C", str(repo_path), "fetch"]
    if depth is not None:
        fetch_cmd.extend(["--depth", str(depth)])

    try:
        subprocess.run(
            fetch_cmd, capture_output=True, text=True, timeout=120, check=True
        )
    except subprocess.CalledProcessError as e:
        return "failed", f"Fetch failed: {e.stderr.strip()}"

    try:
        branch = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except Exception:
        return "failed", "Could not determine current branch"

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "merge", "--ff-only", f"origin/{branch}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        if "Already up to date" in result.stdout:
            return "up-to-date", result.stdout.strip()
        return "success", result.stdout.strip()
    except subprocess.CalledProcessError:
        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "reset", "--hard", f"origin/{branch}"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return "success", "Hard reset to origin (force-push recovery)"
        except subprocess.CalledProcessError as e:
            return "failed", f"Reset failed: {e.stderr.strip()}"
    except Exception as e:
        return "error", f"Exception: {e}"


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
    skipped_no_remote: list[str],
    stats: dict[str, int],
    total: int,
    target_dir: str,
    depth: int | None,
    sort_by_size: str | None,
    processed_repos: set[str],
    completed: bool = False,
    previous_state: dict | None = None,
) -> dict:
    """Build the complete state dictionary with proper merging for continue/only-failed."""
    # Merge stats from previous state when continuing
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

    # Merge grouped results
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

    # Merge failed entries (remove ones that succeeded on retry)
    final_failed = []
    if previous_state:
        prev_failed_paths = {
            entry["repoPath"] for entry in previous_state.get("failed", [])
        }
        current_failed_paths = {entry["repoPath"] for entry in failed_entries}
        final_failed = [
            entry
            for entry in previous_state.get("failed", [])
            if entry["repoPath"] not in current_failed_paths
            or entry["repoPath"] in current_failed_paths
        ]
    final_failed.extend(failed_entries)

    # Skipped
    final_skipped = skipped_no_remote[:]
    if previous_state:
        final_skipped = previous_state.get("skipped_no_remote", []) + final_skipped

    return {
        "metadata": {
            "target_directory": target_dir,
            "depth": depth,
            "sort_by_size": sort_by_size,
            "timestamp": datetime.now().isoformat(),
            "completed": completed,
            "total_repositories": total_for_summary,
            "processed_count": len(processed_repos),
        },
        "summary": summary,
        "grouped_results": final_grouped,
        "failed": final_failed,
        "skipped_no_remote": final_skipped,
        "processed_repos": sorted(list(processed_repos)),
        "progress": progress_data,
    }


def git_pull_all_repos(
    target_dir: str | Path = ".",
    out_path: Path | None = None,
    depth: int | None = DEFAULT_DEPTH,
    sort_by_size: str | None = None,
    continue_from_last: bool = False,
    only_failed: bool = False,
) -> None:
    """
    Find all git repositories under target_dir and run `git pull` in each.
    Now properly handles state merging for --continue and --only-failed.
    """
    base_path = Path(target_dir).expanduser().resolve()
    target_dir_str = str(base_path)

    if out_path is None:
        state_path = base_path / "_git_pull_all_repos_state.json"
    else:
        state_path = out_path.expanduser().resolve()

    mode_line = (
        f"[bold yellow]Shallow mode enabled: depth={depth}[/bold yellow]"
        if depth is not None
        else "[bold yellow]Full history mode (--no-depth)[/bold yellow]"
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

    existing_state = None
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

    if only_failed and existing_state:
        failed_paths = {entry["repoPath"] for entry in existing_state.get("failed", [])}
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
    skipped_no_remote: list[str] = []

    if total_this_run == 0:
        console.print("[yellow]No git repositories found.[/yellow]")
        state = _build_state(
            progress_data=progress_data,
            grouped_results=grouped_results,
            failed_entries=failed_entries,
            skipped_no_remote=skipped_no_remote,
            stats={"success": 0, "up-to-date": 0, "failed": 0, "error": 0},
            total=grand_total,
            target_dir=target_dir_str,
            depth=depth,
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
            skipped_no_remote=skipped_no_remote,
            stats=stats,
            total=grand_total,
            target_dir=target_dir_str,
            depth=depth,
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

            if not repo_info.has_remote_tracking:
                console.print(
                    f" [yellow]⊘[/yellow] {repo} → [dim]Skipped (no remote tracking)[/dim]"
                )
                skipped_no_remote.append(repo_key)
                progress_data[repo_key] = {
                    "status": "skipped",
                    "message": "No remote tracking configured",
                }
                processed_repos.add(repo_key)
                save_state()
                progress.advance(task)
                continue

            status, message = run_git_pull(repo, depth=depth)
            stats[status] += 1
            progress_data[repo_key] = {"status": status, "message": message}
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

            console.print(
                f" {icon} {repo} → "
                f"[dim]{message[:120]}{'...' if len(message) > 120 else ''}[/dim]"
            )
            progress.advance(task)

    save_state(completed=True)

    # Skipped summary
    if skipped_no_remote:
        console.print(
            f"\n[yellow]Skipped {len(skipped_no_remote)} repositories "
            f"without remote tracking:[/yellow]"
        )
        for repo_path in skipped_no_remote:
            console.print(f" • {repo_path}")

    # Final Pull Summary Table
    if total_this_run > 0:
        table = Table(
            title="Pull Summary", show_header=True, header_style="bold magenta"
        )
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")

        status_order = ["success", "up-to-date", "failed", "error"]
        for status in status_order:
            count = (
                stats.get(status, 0)
                if not previous_state
                else final_stats.get(status, 0)
            )  # use merged if available
            perc = (count / grand_total * 100) if grand_total > 0 else 0
            label = (
                "[green]Success[/green]"
                if status == "success"
                else "[blue]Up to date[/blue]"
                if status == "up-to-date"
                else "[red]Failed[/red]"
                if status == "failed"
                else "[red bold]Error[/red bold]"
            )
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
        "-n",
        "--no-depth",
        dest="no_depth",
        action="store_true",
        help=(
            "Disable shallow pulling and fetch full history instead. "
            f"By default, a shallow pull (--depth {DEFAULT_DEPTH}) is used "
            "to fetch only the latest changes."
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

    depth = None if args.no_depth else DEFAULT_DEPTH

    console.print(
        f"[bold]Target directory:[/bold] [link=file://{target_dir}]{target_dir}[/link]"
    )
    console.print(f"[bold]State file:[/bold] [link=file://{out_path}]{out_path}[/link]")
    console.print(
        "[bold]Pull mode:[/bold] "
        + (f"shallow (depth={depth})" if depth is not None else "full history")
    )

    git_pull_all_repos(
        args.target_dir,
        out_path=out_path,
        depth=depth,
        sort_by_size=args.sort_by_size,
        continue_from_last=args.continue_from_last,
        only_failed=args.only_failed,
    )


if __name__ == "__main__":
    main()
