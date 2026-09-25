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
from typing import List, Optional, Set, Tuple

# -----------------------------------------------------------------------------
# CONFIGURATION SETTINGS
# -----------------------------------------------------------------------------
CONFIG = {
    # Timeouts (in seconds)
    "COMMAND_TIMEOUT": 300,  # General command timeout
    "FOLDER_SIZE_TIMEOUT": 300,  # Timeout for individual folder size checks
    "FIND_FILES_TIMEOUT": 300,  # Timeout for searching large files
    # Scan Depth & Limits
    "MAX_ROOT_ITEMS": 15,  # Number of root directories to show
    "MAX_HOME_ITEMS": 20,  # Number of home directory items to show
    "MAX_SUBFOLDER_ITEMS": 10,  # Number of subfolders to list per category
    "FIND_MAX_DEPTH": 3,  # Max depth for 'find' command (prevents hanging on node_modules)
    # Thresholds
    "LARGE_FILE_SIZE_MB": 100,  # Minimum size (MB) to report in "Large Files" section
    "CRITICAL_SPACE_GB": 10,  # Threshold for CRITICAL warning
    "WARNING_SPACE_GB": 20,  # Threshold for WARNING status
    # Paths to Skip during Root Scan (to avoid timeouts/SIP issues)
    "SKIP_ROOT_DIRS": {
        "/System",
        "/Volumes",
        "/dev",
        "/proc",
        "/private/var/folders",  # Often huge and protected
    },
    # Generic Dev Tool Indicators (Folder names to look for in Home Dir)
    "DEV_TOOL_INDICATORS": [
        ".npm",
        ".yarn",
        ".pnpm-store",
        ".m2",
        ".gradle",
        ".cargo",
        "go/pkg",
        ".rustup",
        ".docker",
        ".conda",
        ".local/share/pip",
        "Library/Caches/pip",
        "Library/Developer/Xcode",
        "Library/Android/sdk",
    ],
}

# Rich library for beautiful terminal output
try:
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
        self.available_gb = 0

    def add_to_report(self, text: str):
        """Add line to report file"""
        self.report_lines.append(text)

    def save_report(self):
        """Save accumulated report to file"""
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.report_lines))
        logger.info(f"Report saved to: {REPORT_FILE}")

    def run_command(
        self,
        cmd: list | str,
        shell: bool = False,
        capture: bool = True,
        timeout: int = None,
    ) -> Optional[str]:
        """Run shell command and return output"""
        if timeout is None:
            timeout = CONFIG["COMMAND_TIMEOUT"]

        try:
            # Handle wildcard expansion manually if not using shell
            if isinstance(cmd, list) and not shell:
                has_wildcard = any("*" in str(c) for c in cmd)
                if has_wildcard:
                    cmd_str = " ".join(str(c) for c in cmd)
                    result = subprocess.run(
                        cmd_str,
                        shell=True,
                        capture_output=capture,
                        text=True,
                        timeout=timeout,
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        shell=shell,
                        capture_output=capture,
                        text=True,
                        timeout=timeout,
                    )
            else:
                result = subprocess.run(
                    cmd, shell=shell, capture_output=capture, text=True, timeout=timeout
                )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                # Filter out common macOS permission errors to keep logs clean
                stderr = result.stderr.strip()

                # Ignore "Permission denied" and "Operation not permitted" for system paths
                if stderr:
                    is_expected_error = any(
                        err in stderr
                        for err in [
                            "Permission denied",
                            "Operation not permitted",
                            "No such file or directory",
                        ]
                    )

                    if not is_expected_error:
                        logger.warning(f"Command failed: {cmd}")
                        logger.warning(f"Error: {stderr}")

                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {timeout}s: {cmd}")
            return None
        except Exception as e:
            logger.error(f"Command error: {e}")
            return None

    def get_folder_size(self, path: Path) -> str:
        """Get human-readable folder size"""
        if not path.exists():
            return "0B"
        try:
            result = self.run_command(
                ["du", "-sh", str(path)], timeout=CONFIG["FOLDER_SIZE_TIMEOUT"]
            )
            if result:
                return result.split()[0]
            return "N/A"
        except:
            return "N/A"

    def get_subfolder_sizes(
        self, parent_path: Path, limit: int = None
    ) -> List[Tuple[str, str]]:
        """Safely get sizes of immediate subfolders using iteration instead of wildcards"""
        if limit is None:
            limit = CONFIG["MAX_SUBFOLDER_ITEMS"]

        results = []
        if not parent_path.is_dir():
            return results

        try:
            entries = [e for e in parent_path.iterdir() if e.is_dir()]
        except PermissionError:
            return results

        for entry in entries:
            size = self.get_folder_size(entry)
            if size != "N/A":
                results.append((size, str(entry)))

        # Sort by size
        def parse_size(s):
            s = s.strip()
            multipliers = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
            match = re.match(r"([\d.]+)([BKMGTP]?)i?", s, re.IGNORECASE)
            if match:
                num = float(match.group(1))
                unit = match.group(2).upper() or "B"
                return num * multipliers.get(unit, 1)
            return 0

        results.sort(key=lambda x: parse_size(x[0]), reverse=True)
        return results[:limit]

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
                        try:
                            self.available_gb = float(
                                re.sub(r"[A-Za-z]", "", available)
                            )
                        except:
                            self.available_gb = 0

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

            # Iterate root items instead of using wildcard du
            root_items = []
            try:
                for entry in os.listdir("/"):
                    full_path = Path("/") / entry
                    # Skip configured directories
                    if str(full_path) in CONFIG["SKIP_ROOT_DIRS"]:
                        continue
                    if full_path.is_dir():
                        root_items.append(full_path)
            except PermissionError:
                pass

            results = []
            for item in root_items:
                progress.update(task, description=f"Measuring /{item.name}...")
                size = self.get_folder_size(item)
                if size != "N/A":
                    results.append((size, str(item)))

            # Add skipped system dir note
            results.append(("~12G+", "/System (Skipped)"))

            # Sort
            def parse_size(s):
                s = s.strip()
                multipliers = {
                    "B": 1,
                    "K": 1024,
                    "M": 1024**2,
                    "G": 1024**3,
                    "T": 1024**4,
                }
                match = re.match(r"([\d.]+)([BKMGTP]?)i?", s, re.IGNORECASE)
                if match:
                    num = float(match.group(1))
                    unit = match.group(2).upper() or "B"
                    return num * multipliers.get(unit, 1)
                return 0

            results.sort(key=lambda x: parse_size(x[0]), reverse=True)

            table = Table(title="Top Root Directories")
            table.add_column("Size", style="yellow")
            table.add_column("Path", style="white")

            report_lines = []
            for size, path in results[: CONFIG["MAX_ROOT_ITEMS"]]:
                table.add_row(size, path)
                report_lines.append(f"{size}\t{path}")

            self.console.print(table)
            self.add_to_report("\n".join(report_lines))

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

            # Use iterative approach instead of wildcard du
            results = self.get_subfolder_sizes(
                self.home_dir, limit=CONFIG["MAX_HOME_ITEMS"]
            )

            # Also check hidden files/folders
            hidden_results = []
            try:
                for entry in self.home_dir.iterdir():
                    if entry.name.startswith(".") and entry.is_dir():
                        size = self.get_folder_size(entry)
                        if size != "N/A":
                            hidden_results.append((size, str(entry)))
            except PermissionError:
                pass

            all_results = results + hidden_results

            def parse_size(s):
                s = s.strip()
                multipliers = {
                    "B": 1,
                    "K": 1024,
                    "M": 1024**2,
                    "G": 1024**3,
                    "T": 1024**4,
                }
                match = re.match(r"([\d.]+)([BKMGTP]?)i?", s, re.IGNORECASE)
                if match:
                    num = float(match.group(1))
                    unit = match.group(2).upper() or "B"
                    return num * multipliers.get(unit, 1)
                return 0

            all_results.sort(key=lambda x: parse_size(x[0]), reverse=True)

            table = Table(title="Top Items in Home Directory")
            table.add_column("Size", style="yellow")
            table.add_column("Path", style="white")

            report_lines = []
            for size, path in all_results[: CONFIG["MAX_HOME_ITEMS"]]:
                table.add_row(size, path)
                report_lines.append(f"{size}\t{path}")

            self.console.print(table)
            self.add_to_report("\n".join(report_lines))

            progress.update(task, completed=True)

    def section_library_analysis(self):
        """Section 4: ~/Library folder deep dive"""
        self.display_header("Section 4: ~/Library Folder Analysis")

        library_path = self.home_dir / "Library"
        if not library_path.exists():
            logger.warning("~/Library not found")
            return

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
                    size_num = 0
                    if size != "N/A":
                        match = re.match(r"([\d.]+)([BKMGTP]?)i?", size, re.IGNORECASE)
                        if match:
                            multipliers = {
                                "B": 1,
                                "K": 1024,
                                "M": 1024**2,
                                "G": 1024**3,
                                "T": 1024**4,
                            }
                            num = float(match.group(1))
                            unit = match.group(2).upper() or "B"
                            size_num = num * multipliers.get(unit, 1) / (1024**3)  # GB

                    if size_num > 10:
                        size_text = Text(f"{size}", style="red bold")
                    elif size_num > 5:
                        size_text = Text(f"{size}", style="yellow")
                    else:
                        size_text = Text(f"{size}", style="green")

                    self.console.print(f"  {folder_name:25s}: {size_text}")
                    self.add_to_report(f"{folder_name}: {size}")

                    # Show top items for large folders using iterative method
                    if size_num > 1 and folder_name in [
                        "Caches",
                        "Application Support",
                        "Containers",
                    ]:
                        sub_items = self.get_subfolder_sizes(folder_path, limit=5)
                        if sub_items:
                            self.console.print(f"    Top items in {folder_name}:")
                            for s, p in sub_items:
                                self.console.print(f"      {s} - {Path(p).name}")
                            self.add_to_report(
                                f"  Top items in {folder_name}:\n"
                                + "\n".join([f"{s} - {p}" for s, p in sub_items])
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

                # Use iterative method for subfolders
                sub_items = self.get_subfolder_sizes(
                    global_lib, limit=CONFIG["MAX_SUBFOLDER_ITEMS"]
                )

                if sub_items:
                    table = Table(title="Top 10 Folders in /Library")
                    table.add_column("Size", style="yellow")
                    table.add_column("Path", style="white")

                    report_lines = []
                    for s, p in sub_items:
                        table.add_row(s, p)
                        report_lines.append(f"{s}\t{p}")

                    self.console.print(table)
                    self.add_to_report("\n".join(report_lines))

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
                self.console.print(f"Filesystem: Not APFS", style="grey50")
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

            # Use find with maxdepth to avoid hanging on deep structures
            size_arg = f"+{CONFIG['LARGE_FILE_SIZE_MB']}M"
            find_cmd = f"find {self.home_dir} -maxdepth {CONFIG['FIND_MAX_DEPTH']} -type f -size {size_arg} -mtime -7 2>/dev/null | head -20"
            output = self.run_command(
                find_cmd, shell=True, timeout=CONFIG["FIND_FILES_TIMEOUT"]
            )

            if output:
                files = output.split("\n")
                table = Table(
                    title=f"Large Recent Files (>{CONFIG['LARGE_FILE_SIZE_MB']}MB, Top {CONFIG['FIND_MAX_DEPTH']} Levels)"
                )
                table.add_column("Size", style="yellow")
                table.add_column("Path", style="white")

                report_lines = []
                for file_path in files[:15]:
                    if file_path:
                        size = self.get_folder_size(Path(file_path))
                        table.add_row(size, file_path)
                        report_lines.append(f"{size} - {file_path}")

                self.console.print(table)
                self.add_to_report("\n".join(report_lines))
            else:
                self.console.print(
                    f"No large recent files found in top {CONFIG['FIND_MAX_DEPTH']} levels",
                    style="green",
                )
                self.add_to_report(
                    f"No large recent files found in top {CONFIG['FIND_MAX_DEPTH']} levels"
                )

            progress.update(task, completed=True)

    def get_installed_apps(self) -> Set[str]:
        """Get a set of lowercase app names found in /Applications"""
        apps = set()
        app_dirs = [Path("/Applications"), self.home_dir / "Applications"]

        for dir_path in app_dirs:
            if dir_path.exists():
                try:
                    for item in dir_path.iterdir():
                        if item.suffix == ".app":
                            # Store name without .app and lowercased for comparison
                            apps.add(item.stem.lower())
                except PermissionError:
                    continue
        return apps

    def section_orphaned_apps(self):
        """Section 8: Potential orphaned app data (Generic Logic)"""
        self.display_header("Section 8: Potential Orphaned App Data")

        # 1. Get list of currently installed apps
        installed_apps = self.get_installed_apps()

        # 2. Define system folders to ignore (these are not "orphaned" even if no .app exists)
        system_folders = {
            "apple",
            "icloud",
            "mobiledocuments",
            "microsoft",
            "adobe",
            "google",
            "dropbox",
            "zoom",
            "slack",
            "discord",
            "steam",
            "com.apple",
            "com.microsoft",
            "com.google",
        }

        support_path = self.home_dir / "Library" / "Application Support"
        caches_path = self.home_dir / "Library" / "Caches"

        potential_orphans = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task("Scanning for leftover app data...", total=None)

            # Helper to check a specific library folder
            def scan_library_folder(base_path: Path):
                if not base_path.exists():
                    return

                try:
                    entries = [e for e in base_path.iterdir() if e.is_dir()]
                except PermissionError:
                    return

                for entry in entries:
                    name_lower = entry.name.lower()

                    # Skip if it's a known system folder
                    if any(sys in name_lower for sys in system_folders):
                        continue

                    # Skip if the app is currently installed
                    if name_lower in installed_apps:
                        continue

                    # It's a candidate for orphaned data
                    size = self.get_folder_size(entry)
                    if size != "N/A" and size != "0B":
                        potential_orphans.append((entry.name, str(entry), size))

            scan_library_folder(support_path)
            scan_library_folder(caches_path)

            progress.update(task, completed=True)

        # Sort by size descending
        def parse_size(s):
            s = s.strip()
            multipliers = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
            match = re.match(r"([\d.]+)([BKMGTP]?)i?", s, re.IGNORECASE)
            if match:
                num = float(match.group(1))
                unit = match.group(2).upper() or "B"
                return num * multipliers.get(unit, 1)
            return 0

        potential_orphans.sort(key=lambda x: parse_size(x[2]), reverse=True)

        if potential_orphans:
            table = Table(title="Leftover/Orphaned App Data")
            table.add_column("Folder Name", style="cyan")
            table.add_column("Path", style="white")
            table.add_column("Size", style="yellow")

            report_lines = []
            # Show top 15 largest orphans
            for name, path, size in potential_orphans[:15]:
                table.add_row(name, path, size)
                report_lines.append(f"{name}: {path} ({size})")

            self.console.print(table)
            self.add_to_report("\n".join(report_lines))

            if len(potential_orphans) > 15:
                self.console.print(
                    f"... and {len(potential_orphans) - 15} more smaller items.",
                    style="grey50",
                )
        else:
            self.console.print("No obvious orphaned app data found", style="green")
            self.add_to_report("No obvious orphaned app data found")

    def section_dev_tools(self):
        """Section 9: Development tools storage (Generic Detection)"""
        self.display_header("Section 9: Development Tools Storage")

        dev_tools = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=self.console,
        ) as progress:
            task = progress.add_task(
                "Scanning for dev tools...", total=len(CONFIG["DEV_TOOL_INDICATORS"])
            )

            for indicator in CONFIG["DEV_TOOL_INDICATORS"]:
                progress.update(task, description=f"Checking {indicator}...")

                # Handle nested paths like "Library/Caches/pip"
                if "/" in indicator:
                    path = self.home_dir / indicator
                else:
                    path = self.home_dir / indicator

                if path.exists():
                    size = self.get_folder_size(path)
                    if size != "N/A" and size != "0B":
                        dev_tools.append((indicator, size))

                progress.update(task, advance=1)

        if dev_tools:
            # Sort by size
            def parse_size(s):
                s = s.strip()
                multipliers = {
                    "B": 1,
                    "K": 1024,
                    "M": 1024**2,
                    "G": 1024**3,
                    "T": 1024**4,
                }
                match = re.match(r"([\d.]+)([BKMGTP]?)i?", s, re.IGNORECASE)
                if match:
                    num = float(match.group(1))
                    unit = match.group(2).upper() or "B"
                    return num * multipliers.get(unit, 1)
                return 0

            dev_tools.sort(key=lambda x: parse_size(x[1]), reverse=True)

            table = Table(title="Development Tools Storage")
            table.add_column("Tool/Indicator", style="cyan")
            table.add_column("Size", style="yellow")

            report_lines = []
            for tool, size in dev_tools:
                table.add_row(tool, size)
                report_lines.append(f"{tool}: {size}")

            self.console.print(table)
            self.add_to_report("\n".join(report_lines))
        else:
            self.console.print("No development tools detected", style="grey50")
            self.add_to_report("No development tools detected")

    def section_recommendations(self):
        """Section 10: Recommendations"""
        self.display_header("Section 10: Diagnosis Summary & Recommendations")

        # Determine severity
        if self.available_gb > 0:
            if self.available_gb < CONFIG["CRITICAL_SPACE_GB"]:
                severity = "CRITICAL"
                color = "red bold"
                message = f"Less than {CONFIG['CRITICAL_SPACE_GB']}GB free space! Immediate action required."
            elif self.available_gb < CONFIG["WARNING_SPACE_GB"]:
                severity = "WARNING"
                color = "yellow"
                message = f"Less than {CONFIG['WARNING_SPACE_GB']}GB free space. Cleanup recommended."
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

        report_lines = []
        for action, cmd in cleanup_commands:
            table.add_row(action, cmd)
            report_lines.append(f"{action}: {cmd}")

        self.console.print(table)
        self.add_to_report(
            "\nRecommended Cleanup Commands:\n" + "\n".join(report_lines)
        )

        self.console.print("\n⚠️  Always verify before deleting!", style="yellow bold")
        self.add_to_report("\n⚠️ Always verify before deleting!")

    def run_full_diagnosis(self):
        """Run complete diagnosis"""
        self.console.print(
            Panel(
                "[bold cyan]Mac M1 Disk Space Diagnosis Tool[/bold cyan]\n"
                f"[grey50]Starting comprehensive analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/grey50]",
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
