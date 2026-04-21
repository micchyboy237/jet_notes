from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Literal

from git_repo_finder import find_git_repositories
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


def run_git_pull(
    repo_path: Path,
) -> tuple[Literal["success", "up-to-date", "failed", "error"], str]:
    """Execute git pull in the given repository and classify the outcome."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "pull", "--ff-only"],
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
            return "failed", msg

    except subprocess.TimeoutExpired:
        return "error", "Timed out after 120 seconds"
    except Exception as exc:
        return "error", f"Exception: {exc.__class__.__name__}: {exc}"


def _write_progress(out_path: Path, data: dict[str, dict[str, str]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp_path.replace(out_path)


def _write_grouped_results(out_path: Path, grouped: dict[str, list[str]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(grouped, indent=2, sort_keys=True))
    tmp_path.replace(out_path)


def _write_failed_json(out_path: Path, failed: list[dict[str, str]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(failed, indent=2))
    tmp_path.replace(out_path)


def _write_summary(summary_path: Path, stats: dict[str, int], total: int) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict[str, float]] = {}
    for status, count in stats.items():
        percentage = (count / total * 100) if total > 0 else 0.0
        summary[status] = {
            "count": count,
            "percentage": round(percentage, 1),
        }

    tmp_path = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    tmp_path.replace(summary_path)


def git_pull_all_repos(
    target_dir: str | Path = ".",
    out_path: Path | None = None,
) -> None:
    """
    Find all git repositories under target_dir and run `git pull` in each.
    Uses rich progress bar and beautiful summary table.
    """
    base_path = Path(target_dir).expanduser().resolve()
    console.print(
        f"[bold cyan]Scanning for git repositories in:[/bold cyan] {base_path}\n"
    )

    repos = list(find_git_repositories(base_path))
    total = len(repos)

    progress_data: dict[str, dict[str, str]] = {}

    # Initialize grouped results (by status)
    grouped_results: dict[str, list[str]] = {
        "success": [],
        "up-to-date": [],
        "failed": [],
        "error": [],
    }

    # Accumulated failed/error entries for failed.json
    failed_entries: list[dict[str, str]] = []

    if total == 0:
        console.print("[yellow]No git repositories found.[/yellow]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
            transient=True,
        ):
            pass
        console.print("\n")
        if out_path:
            _write_progress(out_path, progress_data)
        return

    console.print(
        f"[bold]Found [magenta]{total}[/magenta] repositories. Starting pull...[/bold]\n"
    )

    stats = {
        "success": 0,
        "up-to-date": 0,
        "failed": 0,
        "error": 0,
    }
    messages: list[tuple[Path, str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Pulling repositories...", total=total)

        for repo in repos:
            short_name = repo.name or str(repo)
            progress.update(task, description=f"[cyan]Pulling {short_name}...")

            status, message = run_git_pull(repo)
            stats[status] += 1

            progress_data[str(repo)] = {
                "status": status,
                "message": message,
            }

            grouped_results[status].append(str(repo))

            if status in ("failed", "error"):
                failed_entries.append({"repoPath": str(repo), "message": message})

            if out_path:
                _write_progress(out_path, progress_data)
                # Write failed.json incrementally so it's always up to date
                failed_path = out_path.parent / "failed.json"
                _write_failed_json(failed_path, failed_entries)

            icon = {
                "success": "[green]✓[/green]",
                "up-to-date": "[blue]→[/blue]",
                "failed": "[red]✗[/red]",
                "error": "[red bold]![/red bold]",
            }[status]

            console.print(
                f"  {icon}  {repo} → [dim]{message[:120]}{'...' if len(message) > 120 else ''}[/dim]"
            )

            messages.append((repo, status, message))
            progress.advance(task)

    if total > 0:
        table = Table(
            title="Pull Summary", show_header=True, header_style="bold magenta"
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

        if out_path:
            # Write grouped results.json
            _write_grouped_results(out_path, grouped_results)

            # Write summary.json (same directory)
            summary_path = out_path.parent / "summary.json"
            _write_summary(summary_path, stats, total)

            # Write failed.json (same directory)
            failed_path = out_path.parent / "failed.json"
            _write_failed_json(failed_path, failed_entries)

            console.print(
                f"\n[bold]Completed processing {total} repositories.[/bold]\n"
                f"Results saved to: [link=file://{out_path}]{out_path}[/link]\n"
                f"Summary saved to: [link=file://{summary_path}]{summary_path}[/link]\n"
                f"Failed saved to:  [link=file://{failed_path}]{failed_path}[/link]"
            )
        else:
            console.print(f"\n[bold]Completed processing {total} repositories.[/bold]")
    else:
        console.print("\n")


def main():
    OUTPUT_DIR = Path(__file__).parent / "generated" / Path(__file__).stem

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
        help="Save progress status to JSON file",
    )
    args = parser.parse_args()

    # Determine output path (CLI override > default)
    if args.out is not None:
        out_path = args.out.expanduser().resolve()
    else:
        out_path = (OUTPUT_DIR / "results.json").resolve()

    console.print(
        f"[bold]Target directory:[/bold] [link=file://{Path(args.target_dir).expanduser().resolve()}]{args.target_dir}[/link]"
    )
    console.print(
        f"[bold]Output path:[/bold] [link=file://{out_path}]{out_path}[/link]"
    )

    git_pull_all_repos(args.target_dir, out_path=out_path)


if __name__ == "__main__":
    main()
