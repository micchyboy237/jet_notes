#!/usr/bin/env python3
"""
Advanced macOS Disk Diagnostic Tool
Features: Rich Logging, Nested Progress, and Live Status
"""

import logging
import os
from pathlib import Path

# --- Rich Imports ---
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

# --- Configuration ---
console = Console()
HOME = Path.home()

# Setup Rich Logging
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console, markup=True)],
)
logger = logging.getLogger("disk_diag")


def get_size_with_live_update(
    path: Path, main_progress, main_task, sub_progress, sub_task
) -> float:
    """
    Calculate size while updating both main and sub-progress bars.
    """
    total_size = 0
    file_count = 0

    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                try:
                    total_size += entry.stat().st_size
                    file_count += 1
                    # Update sub-progress (files within current folder)
                    sub_progress.update(sub_task, advance=1)
                except (OSError, PermissionError):
                    pass
            elif entry.is_dir(follow_symlinks=False):
                # Recursively scan subdirectories
                # Create a new sub-task for this directory
                new_sub_task = sub_progress.add_task(
                    f"[dim]{entry.name}[/dim]", total=None
                )
                sub_size = get_size_with_live_update(
                    entry.path, main_progress, main_task, sub_progress, new_sub_task
                )
                total_size += sub_size
                sub_progress.remove_task(new_sub_task)

    except PermissionError:
        logger.warning(f"Permission denied: {path}")

    return total_size


def format_size(mb: float) -> str:
    if mb < 1024:
        return f"{mb:.1f} MB"
    return f"{mb / 1024:.2f} GB"


def diagnose_home_directories():
    logger.info("[bold blue]Starting Home Directory Scan...[/bold blue]")

    items = []
    dirs_to_scan = [d for d in HOME.iterdir() if d.is_dir()]

    # Main Progress: Tracks overall folders
    # Sub Progress: Tracks files inside the current folder
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as main_progress:
        main_task = main_progress.add_task(
            "[cyan]Scanning Folders", total=len(dirs_to_scan)
        )

        # Nested progress for file counting
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
            transient=True,  # Hides when done to keep UI clean
        ) as sub_progress:
            for item in dirs_to_scan:
                # Update main status
                main_progress.update(
                    main_task, description=f"[cyan]Scanning: {item.name}"
                )

                # Estimate total files for sub-bar (rough estimate to keep bar moving)
                sub_task = sub_progress.add_task(
                    f"[dim]Indexing {item.name}[/dim]", total=None
                )

                size_bytes = 0
                try:
                    for root, dirs, files in os.walk(item):
                        for f in files:
                            try:
                                size_bytes += os.path.getsize(os.path.join(root, f))
                                sub_progress.update(sub_task, advance=1)
                            except:
                                pass
                except PermissionError:
                    pass

                sub_progress.remove_task(sub_task)
                items.append((item.name, size_bytes / (1024 * 1024)))
                main_progress.update(main_task, advance=1)

    items.sort(key=lambda x: x[1], reverse=True)

    table = Table(title="📂 Home Directory Breakdown", show_lines=True)
    table.add_column("Directory", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right", style="green")
    table.add_column("Percentage", justify="right", style="dim")

    total_home_size = sum(size for _, size in items)

    for name, size in items[:15]:
        pct = (size / total_home_size * 100) if total_home_size > 0 else 0
        table.add_row(name, format_size(size), f"{pct:.1f}%")

    console.print(table)


def diagnose_dev_tools():
    logger.info("[bold yellow]Checking Developer Tools...[/bold yellow]")

    targets = {
        "Xcode DerivedData": HOME / "Library/Developer/Xcode/DerivedData",
        "iOS Simulators": HOME / "Library/Developer/CoreSimulator",
        "Docker Data": HOME / "Library/Containers/com.docker.docker",
        "OrbStack": HOME / ".orbstack",
        "Node Caches": HOME / ".npm",
        "Trash": HOME / ".Trash",
    }

    table = Table(title="🛠️ Developer Space Consumers")
    table.add_column("Tool", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Status", style="dim")

    for name, path in targets.items():
        if path.exists():
            size_mb = 0
            status = "Scanning..."
            try:
                # Quick scan for dev tools
                for root, dirs, files in os.walk(path):
                    for f in files:
                        try:
                            size_mb += os.path.getsize(os.path.join(root, f))
                        except:
                            pass
                status = "Indexed"
            except:
                status = "Error"

            table.add_row(name, format_size(size_mb / (1024 * 1024)), status)
        else:
            table.add_row(name, "-", "Not Found")

    console.print(table)


if __name__ == "__main__":
    console.print(
        Panel.fit(
            "[bold magenta]macOS Advanced Disk Diagnostic[/bold magenta]\n"
            f"User: [cyan]{os.getenv('USER')}[/cyan] | Home: [dim]{HOME}[/dim]",
            border_style="magenta",
        )
    )

    diagnose_home_directories()
    diagnose_dev_tools()

    logger.info("[bold green]✅ Diagnosis Complete![/bold green]")
