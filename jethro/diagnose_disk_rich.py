#!/usr/bin/env python3
"""
Advanced macOS Disk Diagnostic Tool
Features: Rich UI, Progress Tracking, and Structured Logging
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# --- Rich Imports ---
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

# --- Configuration ---
console = Console()
HOME = Path.home()
THRESHOLD_SIZE_MB = 500

# Setup Logging
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
logger = logging.getLogger("disk_diag")


@dataclass
class DirInfo:
    name: str
    path: Path
    size_mb: float


def run_command(cmd: List[str]) -> Optional[str]:
    """Run a shell command silently."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=60
        )
        return result.stdout if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_size_mb(path: Path) -> float:
    """Get directory size in MB using du."""
    if not path.exists():
        return 0.0
    try:
        result = run_command(["du", "-sm", str(path)])
        if result:
            return float(result.split()[0])
    except (ValueError, IndexError):
        pass
    return 0.0


def format_size(mb: float) -> str:
    if mb < 1024:
        return f"{mb:.1f} MB"
    return f"{mb / 1024:.2f} GB"


def diagnose_filesystem(progress: Progress, task_id: int):
    """Check overall filesystem status."""
    logger.info("Analyzing Filesystem & APFS Volumes...")

    # df -h
    df_out = run_command(["df", "-h", "/"])
    apfs_out = run_command(["diskutil", "apfs", "list"])

    table = Table(title="Filesystem Overview", show_header=False, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    if df_out:
        lines = df_out.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            table.add_row("Total Capacity", parts[1])
            table.add_row("Used Space", parts[2])
            table.add_row("Available Space", parts[3])
            table.add_row("Use Percentage", parts[4])

    console.print(table)
    progress.update(task_id, advance=1)


def diagnose_top_directories(progress: Progress, task_id: int):
    """Find largest directories in Home."""
    logger.info("Scanning Home Directory for large folders...")

    items = []
    try:
        for item in HOME.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                size = get_size_mb(item)
                items.append(DirInfo(name=item.name, path=item, size_mb=size))

        items.sort(key=lambda x: x.size_mb, reverse=True)

        table = Table(title=f"Top Directories in {HOME}", show_lines=True)
        table.add_column("Rank", justify="right", style="dim")
        table.add_column("Directory Name", style="blue")
        table.add_column("Size", justify="right", style="green")

        for i, item in enumerate(items[:10]):
            table.add_row(str(i + 1), item.name, format_size(item.size_mb))

        console.print(table)
    except Exception as e:
        logger.error(f"Error scanning home: {e}")

    progress.update(task_id, advance=1)


def diagnose_dev_tools(progress: Progress, task_id: int):
    """Check developer tool caches."""
    logger.info("Checking Developer Tool Caches...")

    dev_paths = {
        "Xcode DerivedData": HOME / "Library/Developer/Xcode/DerivedData",
        "Xcode Archives": HOME / "Library/Developer/Xcode/Archives",
        "iOS Simulators": HOME / "Library/Developer/CoreSimulator",
        "Docker Data": HOME / "Library/Containers/com.docker.docker",
        "OrbStack Data": HOME / ".orbstack",
        "npm Cache": HOME / ".npm",
        "Yarn Cache": HOME / "Library/Caches/Yarn",
        "pnpm Store": HOME / "Library/pnpm/store",
        "iOS Backups": HOME / "Library/Application Support/MobileSync/Backup",
        "System Caches": HOME / "Library/Caches",
    }

    table = Table(title="Developer Space Consumers", show_lines=True)
    table.add_column("Tool", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Path", style="dim", no_wrap=True, overflow="fold")

    results = []
    for name, path in dev_paths.items():
        if path.exists():
            size = get_size_mb(path)
            results.append((name, size, path))

    results.sort(key=lambda x: x[1], reverse=True)

    for name, size, path in results:
        table.add_row(name, format_size(size), str(path))

    console.print(table)
    progress.update(task_id, advance=1)


def diagnose_large_files(progress: Progress, task_id: int):
    """Find large, old files."""
    logger.info(f"Searching for files >{THRESHOLD_SIZE_MB}MB older than 30 days...")

    cmd = [
        "find",
        str(HOME),
        "-type",
        "f",
        "-size",
        f"+{THRESHOLD_SIZE_MB}M",
        "-mtime",
        "+30",
        "-exec",
        "ls",
        "-lh",
        "{}",
        ";",
    ]

    output = run_command(cmd)
    count = 0
    if output:
        lines = [l for l in output.splitlines() if l]
        count = len(lines)

    logger.info(f"Found {count} large old files.")
    progress.update(task_id, advance=1)


def main():
    console.print(
        Panel.fit(
            "[bold blue]macOS Disk Diagnostic Tool[/bold blue]\n"
            f"User: [cyan]{os.getenv('USER')}[/cyan] | Home: [dim]{HOME}[/dim]",
            border_style="blue",
        )
    )

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            expand=True,
        ) as progress:
            tasks = [
                progress.add_task("[cyan]Filesystem Analysis", total=1),
                progress.add_task("[cyan]Home Directory Scan", total=1),
                progress.add_task("[cyan]Dev Tools Check", total=1),
                progress.add_task("[cyan]Large File Search", total=1),
            ]

            diagnose_filesystem(progress, tasks[0])
            diagnose_top_directories(progress, tasks[1])
            diagnose_dev_tools(progress, tasks[2])
            diagnose_large_files(progress, tasks[3])

        console.print("\n[bold green]✅ Diagnosis Complete![/bold green]")
        console.print("Review the tables above to decide what to clean up.")

    except KeyboardInterrupt:
        console.print("\n[bold red]⚠️ Diagnostic interrupted.[/bold red]")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        # Ensure terminal is left in a clean state
        console.print("\n")


if __name__ == "__main__":
    main()
