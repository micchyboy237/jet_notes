#!/usr/bin/env python3
"""
Mac M1 Disk Space Diagnosis Tool
Author: For Jethro Estrada (Dreydeveloper)
Purpose: Comprehensive disk space analysis with rich logging and progress tracking
"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Rich library for beautiful terminal output
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Installing required package: rich")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table
    from rich.text import Text

import logging

# Setup paths
OUTPUT_DIR = Path(__file__).parent / "generated" / Path(__file__).stem
shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_FILE = OUTPUT_DIR / "disk_diagnosis.txt"

# Initialize Rich console
console = Console()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
logger = logging.getLogger(__name__)


class DiskDiagnoser:
    """Comprehensive disk space diagnosis tool for macOS"""

    def __init__(self):
        self.console = console
        self.report_lines = []
        self.home_dir = Path.home()

    def add_to_report(self, text: str):
        """Add line to report file"""
        self.report_lines.append(text)

    def save_report(self):
        """Save accumulated report to file"""
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.report_lines))
        logger.info(f"Report saved to: {REPORT_FILE}")

    def run_command(
        self, cmd: str | list, shell: bool = False, capture: bool = True
    ) -> Optional[str]:
        """Run shell command and return output"""
        try:
            # If cmd is a list and contains wildcards, convert to string for shell execution
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "*" in cmd_str or "?" in cmd_str:
                    shell = True
                    cmd = cmd_str

            result = subprocess.run(
                cmd, shell=shell, capture_output=capture, text=True, timeout=60
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.warning(f"Command failed: {cmd}")
                logger.warning(f"Error: {result.stderr.strip()}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {cmd}")
            return None
        except Exception as e:
            logger.error(f"Command error: {e}")
            return None

    def get_folder_size(self, path: Path) -> str:
        """Get human-readable folder size"""
        try:
            result = self.run_command(["du", "-sh", str(path)])
            if result:
                return result.split()[0]
            return "N/A"
        except:
            return "N/A"

    def display_header(self, title: str):
        """Display section header"""
        self.console.print()
        panel = Panel(
            Text(title, style="bold cyan"), border_style="cyan", padding=(0, 2)
        )
        self.console.print(panel)
        self.add_to_report(f"\n{'=' * 60}")
        self.add_to_report(f"{title}")
        self.add_to_report("=" * 60)

    def section_overall_disk_usage(self):
        """Section 1: Overall disk usage"""
        self.display_header("Section 1: Overall Disk Usage")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Analyzing disk usage...", total=None)

            # Get disk info
            df_output = self.run_command(["df", "-h", "/"])

            if df_output:
                lines = df_output.split("\n")
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        total = parts[1]
                        used = parts[2]
                        available = parts[3]
                        percent = parts[4]

                        table = Table(show_header=False, box=None)
                        table.add_column("Metric", style="cyan")
                        table.add_column("Value", style="green")

                        table.add_row("Total Space", total)
                        table.add_row("Used Space", used)
                        table.add_row("Available Space", available)
                        table.add_row("Usage Percentage", percent)

                        self.console.print(table)

                        self.add_to_report(df_output)
                        self.add_to_report(
                            f"\nTotal: {total} | Used: {used} | Available: {available} | {percent}"
                        )

                        # Store available space for recommendations
                        self.available_gb = float(re.sub(r"[A-Za-z]", "", available))

            progress.update(task, completed=True)

    def section_top_level_directories(self):
        """Section 2: Top-level directory sizes"""
        self.display_header("Section 2: Top-Level Directory Sizes (Root)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Scanning root directories...", total=None)

            output = self.run_command(["sudo", "du", "-sh", "/*"], capture=True)

            if output:
                lines = output.split("\n")
                # Sort by size
                sorted_lines = sorted(
                    [line for line in lines if line],
                    key=lambda x: float(re.sub(r"[A-Za-z]", "", x.split()[0]))
                    if x.split()[0].replace(".", "").isdigit()
                    else 0,
                    reverse=True,
                )[:15]

                table = Table(title="Top 15 Root Directories")
                table.add_column("Size", style="yellow")
                table.add_column("Path", style="white")

                for line in sorted_lines:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        table.add_row(parts[0], parts[1])

                self.console.print(table)
                self.add_to_report("\n".join(sorted_lines))

            progress.update(task, completed=True)

    def section_home_directory(self):
        """Section 3: Home directory breakdown"""
        self.display_header("Section 3: Home Directory Breakdown")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Analyzing home directory...", total=None)

            output = self.run_command(
                ["du", "-sh", str(self.home_dir) + "/*", str(self.home_dir) + "/.*"]
            )

            if output:
                lines = output.split("\n")
                sorted_lines = sorted(
                    [line for line in lines if line],
                    key=lambda x: float(re.sub(r"[A-Za-z]", "", x.split()[0]))
                    if x.split()[0].replace(".", "").isdigit()
                    else 0,
                    reverse=True,
                )[:20]

                table = Table(title="Top 20 Items in Home Directory")
                table.add_column("Size", style="yellow")
                table.add_column("Path", style="white")

                for line in sorted_lines:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        table.add_row(parts[0], parts[1])

                self.console.print(table)
                self.add_to_report("\n".join(sorted_lines))

            progress.update(task, completed=True)

    def section_library_analysis(self):
        """Section 4: ~/Library folder deep dive"""
        self.display_header("Section 4: ~/Library Folder Analysis")

        library_path = self.home_dir / "Library"
        if not library_path.exists():
            logger.warning("~/Library not found")
            return

        # Main library folders
        critical_folders = [
            ("Caches", library_path / "Caches"),
            ("Application Support", library_path / "Application Support"),
            ("Containers", library_path / "Containers"),
            ("Developer", library_path / "Developer"),
            ("Messages", library_path / "Messages"),
            ("Metadata", library_path / "Metadata"),
            ("Logs", library_path / "Logs"),
            ("Mobile Documents", library_path / "Mobile Documents"),
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "Analyzing Library folders...", total=len(critical_folders)
            )

            for folder_name, folder_path in critical_folders:
                progress.update(task, description=f"Checking {folder_name}...")

                if folder_path.exists():
                    size = self.get_folder_size(folder_path)

                    # Color code based on size
                    size_num = (
                        float(re.sub(r"[A-Za-z]", "", size)) if size != "N/A" else 0
                    )
                    if size_num > 10:
                        size_text = Text(f"{size}", style="red bold")
                    elif size_num > 5:
                        size_text = Text(f"{size}", style="yellow")
                    else:
                        size_text = Text(f"{size}", style="green")

                    self.console.print(f"  {folder_name:25s}: {size_text}")
                    self.add_to_report(f"{folder_name}: {size}")

                    # Show top items for large folders
                    if size_num > 1 and folder_name in [
                        "Caches",
                        "Application Support",
                        "Containers",
                    ]:
                        sub_output = self.run_command(
                            ["du", "-sh", str(folder_path) + "/*"]
                        )
                        if sub_output:
                            sub_lines = sub_output.split("\n")
                            sorted_subs = sorted(
                                [line for line in sub_lines if line],
                                key=lambda x: float(
                                    re.sub(r"[A-Za-z]", "", x.split()[0])
                                )
                                if x.split()[0].replace(".", "").isdigit()
                                else 0,
                                reverse=True,
                            )[:10]

                            if sorted_subs:
                                self.console.print(f"    Top items in {folder_name}:")
                                for sub_line in sorted_subs[:5]:
                                    self.console.print(f"      {sub_line}")
                                self.add_to_report(
                                    f"  Top items in {folder_name}:\n"
                                    + "\n".join(sorted_subs[:5])
                                )

                progress.update(task, advance=1)

        # Special check for SpotlightKnowledgeEvents
        spotlight_path = library_path / "Metadata" / "SpotlightKnowledgeEvents"
        if spotlight_path.exists():
            spotlight_size = self.get_folder_size(spotlight_path)
            self.console.print(
                f"\n  ⚠️  SpotlightKnowledgeEvents: {spotlight_size} (KNOWN ISSUE)",
                style="red bold",
            )
            self.add_to_report(
                f"\n⚠️ SpotlightKnowledgeEvents: {spotlight_size} (KNOWN ISSUE)"
            )

    def section_global_library(self):
        """Section 5: /Library folder analysis"""
        self.display_header("Section 5: /Library Folder Analysis")

        global_lib = Path("/Library")
        if global_lib.exists():
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=self.console,
            ) as progress:
                task = progress.add_task("Scanning /Library...", total=None)

                size = self.get_folder_size(global_lib)
                self.console.print(f"/Library total size: {size}", style="cyan")
                self.add_to_report(f"/Library total size: {size}")

                output = self.run_command(["sudo", "du", "-sh", "/Library/*"])
                if output:
                    lines = output.split("\n")
                    sorted_lines = sorted(
                        [line for line in lines if line],
                        key=lambda x: float(re.sub(r"[A-Za-z]", "", x.split()[0]))
                        if x.split()[0].replace(".", "").isdigit()
                        else 0,
                        reverse=True,
                    )[:10]

                    table = Table(title="Top 10 Folders in /Library")
                    table.add_column("Size", style="yellow")
                    table.add_column("Path", style="white")

                    for line in sorted_lines:
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            table.add_row(parts[0], parts[1])

                    self.console.print(table)
                    self.add_to_report("\n".join(sorted_lines))

                progress.update(task, completed=True)

    def section_time_machine_snapshots(self):
        """Section 6: Time Machine local snapshots"""
        self.display_header("Section 6: Time Machine Local Snapshots")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Checking Time Machine snapshots...", total=None)

            # Check filesystem
            fs_output = self.run_command(["df", "-T", "/"])
            is_apfs = "apfs" in fs_output.lower() if fs_output else False

            if is_apfs:
                self.console.print(
                    "Filesystem: APFS (supports snapshots)", style="cyan"
                )
                self.add_to_report("Filesystem: APFS (supports snapshots)")

                # List snapshots
                snapshot_output = self.run_command(
                    ["diskutil", "apfs", "listsnapshots", "/"]
                )

                if snapshot_output and "Snapshot" in snapshot_output:
                    lines = snapshot_output.split("\n")
                    snapshot_count = sum(1 for line in lines if "Snapshot" in line)

                    self.console.print(
                        f"Found {snapshot_count} local snapshot(s)", style="yellow"
                    )
                    self.add_to_report(f"Found {snapshot_count} local snapshot(s)")

                    if snapshot_count > 5:
                        self.console.print(
                            "⚠️  WARNING: High number of local snapshots!",
                            style="red bold",
                        )
                        self.add_to_report("⚠️ WARNING: High number of local snapshots!")

                    # Show first few snapshots
                    for line in lines[:10]:
                        if "Snapshot" in line:
                            self.console.print(f"  {line}")
                            self.add_to_report(f"  {line}")
                else:
                    self.console.print("No local snapshots found", style="green")
                    self.add_to_report("No local snapshots found")
            else:
                self.console.print(f"Filesystem: Not APFS", style="gray")
                self.add_to_report("Filesystem: Not APFS")

            progress.update(task, completed=True)

    def section_large_files(self):
        """Section 7: Recently modified large files"""
        self.display_header("Section 7: Recently Modified Large Files (>100MB)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Searching for large files...", total=None)

            # Find files >100MB modified in last 7 days
            find_cmd = f"find {self.home_dir} -type f -size +100M -mtime -7 2>/dev/null | head -20"
            output = self.run_command(find_cmd, shell=True)

            if output:
                files = output.split("\n")
                table = Table(title="Large Recent Files")
                table.add_column("Size", style="yellow")
                table.add_column("Path", style="white")

                for file_path in files[:15]:
                    if file_path:
                        size = self.get_folder_size(Path(file_path))
                        table.add_row(size, file_path)
                        self.add_to_report(f"{size} - {file_path}")

                self.console.print(table)
            else:
                self.console.print("No large recent files found", style="green")
                self.add_to_report("No large recent files found")

            progress.update(task, completed=True)

    def section_orphaned_apps(self):
        """Section 8: Potential orphaned app data"""
        self.display_header("Section 8: Potential Orphaned App Data")

        orphaned_apps = [
            "Spotify",
            "Slack",
            "Discord",
            "Zoom",
            "Teams",
            "Skype",
            "WhatsApp",
            "Telegram",
            "Signal",
        ]

        found_orphans = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "Checking for orphaned app data...", total=len(orphaned_apps)
            )

            for app in orphaned_apps:
                progress.update(task, description=f"Checking {app}...")

                paths_to_check = [
                    self.home_dir / "Library" / "Application Support" / app,
                    self.home_dir / "Library" / "Caches" / app,
                    self.home_dir
                    / "Library"
                    / "Preferences"
                    / f"com.{app.lower()}.plist",
                ]

                for path in paths_to_check:
                    if path.exists():
                        size = self.get_folder_size(path)
                        found_orphans.append((app, str(path), size))
                        break

                progress.update(task, advance=1)

        if found_orphans:
            table = Table(title="Orphaned App Data Found")
            table.add_column("App", style="cyan")
            table.add_column("Path", style="white")
            table.add_column("Size", style="yellow")

            for app, path, size in found_orphans:
                table.add_row(app, path, size)
                self.add_to_report(f"{app}: {path} ({size})")

            self.console.print(table)
        else:
            self.console.print("No obvious orphaned app data found", style="green")
            self.add_to_report("No obvious orphaned app data found")

    def section_dev_tools(self):
        """Section 9: Development tools storage"""
        self.display_header("Section 9: Development Tools Storage")

        dev_tools = []

        # Docker
        docker_path = self.home_dir / "Library" / "Containers" / "com.docker.docker"
        if docker_path.exists():
            size = self.get_folder_size(docker_path)
            dev_tools.append(("Docker", size))

        # npm cache
        npm_cache = self.home_dir / ".npm"
        if npm_cache.exists():
            size = self.get_folder_size(npm_cache)
            dev_tools.append(("npm cache", size))

        # pip cache
        pip_cache = self.home_dir / "Library" / "Caches" / "pip"
        if pip_cache.exists():
            size = self.get_folder_size(pip_cache)
            dev_tools.append(("pip cache", size))

        # Homebrew
        brew_path = Path("/opt/homebrew")
        if brew_path.exists():
            size = self.get_folder_size(brew_path)
            dev_tools.append(("Homebrew", size))

        # Node modules in common locations
        node_modules_paths = [
            self.home_dir / "node_modules",
            self.home_dir / "Documents" / "node_modules",
        ]

        for nm_path in node_modules_paths:
            if nm_path.exists():
                size = self.get_folder_size(nm_path)
                dev_tools.append((f"node_modules ({nm_path.name})", size))

        if dev_tools:
            table = Table(title="Development Tools Storage")
            table.add_column("Tool", style="cyan")
            table.add_column("Size", style="yellow")

            for tool, size in dev_tools:
                table.add_row(tool, size)
                self.add_to_report(f"{tool}: {size}")

            self.console.print(table)
        else:
            self.console.print("No development tools detected", style="gray")
            self.add_to_report("No development tools detected")

    def section_recommendations(self):
        """Section 10: Recommendations"""
        self.display_header("Section 10: Diagnosis Summary & Recommendations")

        # Determine severity
        if hasattr(self, "available_gb"):
            if self.available_gb < 10:
                severity = "CRITICAL"
                color = "red bold"
                message = f"Less than 10GB free space! Immediate action required."
            elif self.available_gb < 20:
                severity = "WARNING"
                color = "yellow"
                message = f"Less than 20GB free space. Cleanup recommended."
            else:
                severity = "OK"
                color = "green"
                message = f"Disk space is adequate ({self.available_gb:.1f}GB free)."

            self.console.print(f"Status: {severity}", style=color)
            self.console.print(message, style=color)
            self.add_to_report(f"Status: {severity}")
            self.add_to_report(message)

        # Cleanup commands
        self.console.print("\nRecommended cleanup commands:", style="cyan bold")

        cleanup_commands = [
            ("Clear user caches", "rm -rf ~/Library/Caches/*"),
            ("Delete Time Machine snapshots", "tmutil deletelocalsnapshots /"),
            ("Clear npm cache", "npm cache clean --force"),
            ("Clear pip cache", "pip cache purge"),
            ("Docker cleanup", "docker system prune -a"),
            ("Homebrew cleanup", "brew cleanup"),
            (
                "Clear Spotlight metadata",
                "rm -rf ~/Library/Metadata/SpotlightKnowledgeEvents",
            ),
        ]

        table = Table(title="Safe Cleanup Commands")
        table.add_column("Action", style="cyan")
        table.add_column("Command", style="white")

        for action, cmd in cleanup_commands:
            table.add_row(action, cmd)
            self.add_to_report(f"{action}: {cmd}")

        self.console.print(table)

        self.console.print("\n⚠️  Always verify before deleting!", style="yellow bold")
        self.add_to_report("\n⚠️ Always verify before deleting!")

    def run_full_diagnosis(self):
        """Run complete diagnosis"""
        self.console.print(
            Panel(
                "[bold cyan]Mac M1 Disk Space Diagnosis Tool[/bold cyan]\n"
                f"[gray]Starting comprehensive analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/gray]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

        # Initialize report
        self.add_to_report("=" * 60)
        self.add_to_report("Mac M1 Disk Space Diagnosis Report")
        self.add_to_report(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.add_to_report(f"User: {os.getenv('USER', 'unknown')}")
        self.add_to_report(f"Hostname: {os.uname().nodename}")
        self.add_to_report(f"macOS Version: {os.uname().version}")
        self.add_to_report(f"Architecture: {os.uname().machine}")
        self.add_to_report("=" * 60)

        # Run all sections
        sections = [
            self.section_overall_disk_usage,
            self.section_top_level_directories,
            self.section_home_directory,
            self.section_library_analysis,
            self.section_global_library,
            self.section_time_machine_snapshots,
            self.section_large_files,
            self.section_orphaned_apps,
            self.section_dev_tools,
            self.section_recommendations,
        ]

        total_sections = len(sections)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            main_task = progress.add_task("Running diagnosis...", total=total_sections)

            for i, section in enumerate(sections):
                progress.update(main_task, description=f"Running: {section.__doc__}")
                try:
                    section()
                except Exception as e:
                    logger.error(f"Error in {section.__name__}: {e}")
                    self.add_to_report(f"ERROR in {section.__name__}: {e}")

                progress.update(main_task, advance=1)

        # Save report
        self.save_report()

        # Final summary
        self.console.print()
        self.console.print(
            Panel(
                f"[bold green]✓ Diagnosis Complete![/bold green]\n\n"
                f"Report saved to: [cyan]{REPORT_FILE}[/cyan]\n\n"
                f"[yellow]Next steps:[/yellow]\n"
                f"  1. Review the report file for specific large folders\n"
                f"  2. Use 'du -sh' to verify sizes before deletion\n"
                f"  3. Start with safe cleanup (caches, trash, snapshots)\n"
                f"  4. Monitor disk space after cleanup",
                border_style="green",
                padding=(1, 2),
            )
        )


if __name__ == "__main__":
    diagnoser = DiskDiagnoser()
    diagnoser.run_full_diagnosis()
