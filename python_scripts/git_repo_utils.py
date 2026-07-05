from __future__ import annotations

import logging
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    """Comprehensive information about a git repository."""

    path: Path
    name: str
    remote_url: str | None = None
    size_bytes: int | None = None
    size_human: str | None = None
    current_branch: str | None = None
    last_commit_date: str | None = None
    has_uncommitted: bool | None = None
    commit_count: int | None = None
    has_remote_tracking: bool = False

    @property
    def size_display(self) -> str:
        """Human-readable size or 'unknown'."""
        return self.size_human or "unknown"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "path": str(self.path),
            "remote_url": self.remote_url,
            "size": {
                "bytes": self.size_bytes,
                "human_readable": self.size_human,
            },
            "current_branch": self.current_branch,
            "last_commit_date": self.last_commit_date,
            "has_uncommitted": self.has_uncommitted,
            "commit_count": self.commit_count,
            "has_remote_tracking": self.has_remote_tracking,
        }


def get_repo_size(repo_path: str | Path) -> Optional[tuple[int, str]]:
    """
    Get the size of a git repository's .git directory using 'du -sh'.
    Args:
        repo_path: Path to the git repository
    Returns:
        Tuple of (size_in_bytes, human_readable_size) or None if error
        Example: (123456789, "117.8M")
    """
    repo = Path(repo_path).resolve()
    git_dir = repo / ".git"
    if not git_dir.is_dir():
        logger.warning(f"No .git directory found at {repo}")
        return None
    try:
        result_hr = subprocess.run(
            ["du", "-sh", str(git_dir)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        human_readable = result_hr.stdout.strip().split("\t")[0]

        if platform.system() == "Darwin":
            result_kb = subprocess.run(
                ["du", "-sk", str(git_dir)],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            size_kb = int(result_kb.stdout.strip().split("\t")[0])
            size_bytes = size_kb * 1024
        else:
            result_bytes = subprocess.run(
                ["du", "-sb", str(git_dir)],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            size_bytes = int(result_bytes.stdout.strip().split("\t")[0])

        logger.debug(
            f"Repo size for {repo.name}: {human_readable} ({size_bytes} bytes)"
        )
        return size_bytes, human_readable
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout getting size for {repo}")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running du for {repo}: {e.stderr.strip() if e.stderr else str(e)}"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to get repo size for {repo}: {e}")
        return None


def get_remote_origin_url(repo_path: str | Path) -> Optional[str]:
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


def is_git_repository(path: str | Path) -> bool:
    """
    Check if the given path is the root of a git repository.
    Looks for .git/HEAD file (most reliable lightweight check).
    Args:
        path: Path to check
    Returns:
        True if path is a git repository root
    """
    return (Path(path) / ".git" / "HEAD").is_file()


def has_remote_tracking(repo_path: str | Path) -> bool:
    """
    Check if the repository has a remote tracking branch configured.
    Args:
        repo_path: Path to the git repository
    Returns:
        True if the current branch has an upstream remote set
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "@{u}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_current_branch(repo_path: str | Path) -> Optional[str]:
    """
    Get the current branch name of a git repository.
    Args:
        repo_path: Path to the git repository
    Returns:
        Current branch name or None if error
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        branch = result.stdout.strip()
        logger.debug(f"Current branch for {repo_path}: {branch}")
        return branch if branch else None
    except Exception as e:
        logger.debug(f"Error getting current branch for {repo_path}: {e}")
        return None


def get_last_commit_date(repo_path: str | Path) -> Optional[str]:
    """
    Get the date of the last commit in a git repository.
    Args:
        repo_path: Path to the git repository
    Returns:
        ISO format date string or None if error
        Example: "2024-01-15T10:30:00"
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1", "--format=%aI"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        date_str = result.stdout.strip()
        logger.debug(f"Last commit date for {repo_path}: {date_str}")
        return date_str if date_str else None
    except Exception as e:
        logger.debug(f"Error getting last commit date for {repo_path}: {e}")
        return None


def has_uncommitted_changes(repo_path: str | Path) -> Optional[bool]:
    """
    Check if a git repository has uncommitted changes.
    Args:
        repo_path: Path to the git repository
    Returns:
        True if there are uncommitted changes, False if clean, None if error
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        has_changes = bool(result.stdout.strip())
        logger.debug(f"Uncommitted changes for {repo_path}: {has_changes}")
        return has_changes
    except Exception as e:
        logger.debug(f"Error checking uncommitted changes for {repo_path}: {e}")
        return None


def get_commit_count(repo_path: str | Path, branch: str = "HEAD") -> Optional[int]:
    """
    Get the total number of commits in a git repository.
    Args:
        repo_path: Path to the git repository
        branch: Branch name (default: HEAD)
    Returns:
        Number of commits or None if error
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--count", branch],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        count = int(result.stdout.strip())
        logger.debug(f"Commit count for {repo_path}: {count}")
        return count
    except Exception as e:
        logger.debug(f"Error getting commit count for {repo_path}: {e}")
        return None


def get_repo_info(
    repo_path: str | Path,
    *,
    include_size: bool = True,
    include_branch: bool = False,
    include_commit_date: bool = False,
    include_uncommitted: bool = False,
    include_commit_count: bool = False,
    check_remote_tracking: bool = False,
) -> RepoInfo:
    """
    Gather comprehensive information about a git repository.

    Args:
        repo_path: Path to the git repository
        include_size: Calculate .git directory size
        include_branch: Get current branch name
        include_commit_date: Get last commit date
        include_uncommitted: Check for uncommitted changes
        include_commit_count: Get total commit count
        check_remote_tracking: Check if upstream is configured

    Returns:
        RepoInfo dataclass with requested information
    """
    path = Path(repo_path).resolve()
    remote_url = get_remote_origin_url(path)

    info = RepoInfo(
        path=path,
        name=path.name,
        remote_url=remote_url,
    )

    if include_size:
        size_info = get_repo_size(path)
        if size_info:
            info.size_bytes, info.size_human = size_info
            logger.debug(f"Size for {path.name}: {info.size_human}")

    if include_branch:
        info.current_branch = get_current_branch(path)
        logger.debug(f"Branch for {path.name}: {info.current_branch}")

    if include_commit_date:
        info.last_commit_date = get_last_commit_date(path)
        logger.debug(f"Last commit for {path.name}: {info.last_commit_date}")

    if include_uncommitted:
        info.has_uncommitted = has_uncommitted_changes(path)
        logger.debug(f"Uncommitted in {path.name}: {info.has_uncommitted}")

    if include_commit_count:
        info.commit_count = get_commit_count(path)
        logger.debug(f"Commits in {path.name}: {info.commit_count}")

    if check_remote_tracking:
        info.has_remote_tracking = has_remote_tracking(path)
        logger.debug(f"Remote tracking for {path.name}: {info.has_remote_tracking}")

    return info
