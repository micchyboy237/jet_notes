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
    """Execute git pull in the given repository and classify the outcome.
    If `depth` is set (default: 1), performs a shallow pull
    (git pull --depth N --ff-only), fetching only the latest N commits
    instead of full history. Pass depth=None for a full-history pull.
    """
    cmd = ["git", "-C", str(repo_path), "pull", "--ff-only"]
    if depth is not None:
        cmd.extend(["--depth", str(depth)])
    mode_note = f"shallow, depth={depth}" if depth is not None else "full history"
    console.log(f"[dim]Running:[/dim] {' '.join(cmd)} [dim]({mode_note})[/dim]")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0:
            stdout = result.stdout.strip()
            if "Already up to date" in stdout or "up to date" in stdout.lower():
                return "up-to-date", stdout or "Already up to date."
            return "success", stdout or "Pulled successfully."
        else:
            msg = result.stderr.strip() or result.stdout.strip() or "Non-zero exit code"
            console.log(f"[red]git pull failed for {repo_path}: {msg}[/red]")
            return "failed", msg
    except subprocess.TimeoutExpired:
        console.log(f"[red]git pull timed out for {repo_path}[/red]")
        return "error", "Timed out after 120 seconds"
    except Exception as exc:
        console.log(
            f"[red bold]Exception during git pull for {repo_path}: {exc}[/red bold]"
        )
        return "error", f"Exception: {exc.__class__.__name__}: {exc}"


def _write_state_file(state_path: Path, state: dict) -> None:
    """Atomically write the complete state to a single JSON file."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp_path.replace(state_path)


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
    completed: bool = False,
) -> dict:
    """Build the complete state dictionary for the single state file."""
    # Calculate summary percentages
    summary: dict[str, dict[str, float]] = {}
    for status, count in stats.items():
        percentage = (count / total * 100) if total > 0 else 0.0
        summary[status] = {
            "count": count,
            "percentage": round(percentage, 1),
        }

    return {
        "metadata": {
            "target_directory": target_dir,
            "depth": depth,
            "sort_by_size": sort_by_size,
            "timestamp": datetime.now().isoformat(),
            "completed": completed,
            "total_repositories": total,
            "processed_count": len(progress_data),
        },
        "summary": summary,
        "grouped_results": grouped_results,
        "failed": failed_entries,
        "skipped_no_remote": skipped_no_remote,
        "progress": progress_data,
    }


def git_pull_all_repos(
    target_dir: str | Path = ".",
    out_path: Path | None = None,
    depth: int | None = DEFAULT_DEPTH,
    sort_by_size: str | None = None,
) -> None:
    """
    Find all git repositories under target_dir and run `git pull` in each.

    Uses rich progress bar and beautiful summary table.
    By default, pulls are shallow (--depth 1), fetching only the latest
    changes instead of full history. Pass depth=None for a full pull.

    All progress and results are saved to a single state file.

    Args:
        target_dir: Root directory to search for git repositories
        out_path: Full path to the state JSON file (file, not directory)
        depth: Shallow clone depth (None for full history)
        sort_by_size: Sort repos by .git size before pulling ("asc" or "desc")
    """
    base_path = Path(target_dir).expanduser().resolve()
    target_dir_str = str(base_path)

    # Use provided out_path or default to target directory
    if out_path is None:
        state_path = base_path / "_git_pull_all_repos_state.json"
    else:
        state_path = out_path.expanduser().resolve()

    mode_line = (
        f"[bold yellow]Shallow mode enabled: depth={depth}[/bold yellow]"
        if depth is not None
        else "[bold yellow]Full history mode (--no-depth)[/bold yellow]"
    )
    console.print(
        f"[bold cyan]Scanning for git repositories in:[/bold cyan] {base_path}\n"
        f"{mode_line}\n"
    )
    console.print(f"[dim]State file: {state_path}[/dim]\n")

    # Use enhanced find_git_repositories with all needed info
    repos: list[RepoInfo] = list(
        find_git_repositories(
            base_path,
            sort_by_size=sort_by_size,
            include_size=sort_by_size is not None,
            check_remote_tracking=True,
        )
    )

    # Display sort order if sorting
    if sort_by_size:
        console.print("[bold]Pull order (sorted by size):[/bold]")
        for i, repo_info in enumerate(repos, 1):
            console.print(f"  {i:3d}. {repo_info.name:40s} → {repo_info.size_display}")
        console.print()

    total = len(repos)
    progress_data: dict[str, dict[str, str]] = {}
    grouped_results: dict[str, list[str]] = {
        "success": [],
        "up-to-date": [],
        "failed": [],
        "error": [],
    }
    failed_entries: list[dict[str, str]] = []
    skipped_no_remote: list[str] = []

    if total == 0:
        console.print("[yellow]No git repositories found.[/yellow]")
        state = _build_state(
            progress_data=progress_data,
            grouped_results=grouped_results,
            failed_entries=failed_entries,
            skipped_no_remote=skipped_no_remote,
            stats={"success": 0, "up-to-date": 0, "failed": 0, "error": 0},
            total=0,
            target_dir=target_dir_str,
            depth=depth,
            sort_by_size=sort_by_size,
            completed=True,
        )
        _write_state_file(state_path, state)
        console.print(f"[dim]State saved to: {state_path}[/dim]")
        return

    console.print(
        f"[bold]Found [magenta]{total}[/magenta] repositories. "
        f"Starting pull...[/bold]\n"
    )

    stats = {
        "success": 0,
        "up-to-date": 0,
        "failed": 0,
        "error": 0,
    }

    def save_state(completed: bool = False) -> None:
        """Save complete state to single JSON file."""
        state = _build_state(
            progress_data=progress_data,
            grouped_results=grouped_results,
            failed_entries=failed_entries,
            skipped_no_remote=skipped_no_remote,
            stats=stats,
            total=total,
            target_dir=target_dir_str,
            depth=depth,
            sort_by_size=sort_by_size,
            completed=completed,
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
        task = progress.add_task("[cyan]Pulling repositories...", total=total)

        for repo_info in repos:
            repo = repo_info.path
            short_name = repo_info.name

            progress.update(task, description=f"[cyan]Pulling {short_name}...")

            # Use pre-computed remote tracking info
            if not repo_info.has_remote_tracking:
                console.print(
                    f"  [yellow]⊘[/yellow]  {repo} → "
                    f"[dim]Skipped (no remote tracking)[/dim]"
                )
                skipped_no_remote.append(str(repo))
                progress_data[str(repo)] = {
                    "status": "skipped",
                    "message": "No remote tracking configured",
                }
                save_state()
                progress.advance(task)
                continue

            status, message = run_git_pull(repo, depth=depth)
            stats[status] += 1
            progress_data[str(repo)] = {
                "status": status,
                "message": message,
            }
            grouped_results[status].append(str(repo))

            if status in ("failed", "error"):
                failed_entries.append({"repoPath": str(repo), "message": message})

            # Save state immediately after each repo
            save_state()

            icon = {
                "success": "[green]✓[/green]",
                "up-to-date": "[blue]→[/blue]",
                "failed": "[red]✗[/red]",
                "error": "[red bold]![/red bold]",
            }[status]

            console.print(
                f"  {icon}  {repo} → "
                f"[dim]{message[:120]}{'...' if len(message) > 120 else ''}[/dim]"
            )
            progress.advance(task)

    # Write final completed state
    save_state(completed=True)

    # Display skipped repos
    if skipped_no_remote:
        console.print(
            f"\n[yellow]Skipped {len(skipped_no_remote)} repositories "
            f"without remote tracking:[/yellow]"
        )
        for repo_path in skipped_no_remote:
            console.print(f"  • {repo_path}")

    # Summary table
    if total > 0:
        table = Table(
            title="Pull Summary",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")

        for status, count in stats.items():
            perc = (count / total * 100) if total > 0 else 0
            table.add_row(
                "[green]Success[/green]"
                if status == "success"
                else "[blue]Up to date[/blue]"
                if status == "up-to-date"
                else "[red]Failed[/red]"
                if status == "failed"
                else "[red bold]Error[/red bold]",
                str(count),
                f"{perc:5.1f}%",
            )

        console.print("\n")
        console.print(table)

        console.print(
            f"\n[bold]Completed processing {total} repositories.[/bold]\n"
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
    args = parser.parse_args()

    # Resolve target directory
    target_dir = Path(args.target_dir).expanduser().resolve()

    # Determine output path
    if args.out is not None:
        out_path = args.out.expanduser().resolve()
        if out_path.is_dir() or args.out.suffix == "":
            # Treat as directory
            out_path = out_path / "_git_pull_all_repos_state.json"
    else:
        # Default: save in target directory
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
    )


if __name__ == "__main__":
    main()
