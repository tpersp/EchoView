#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilities for interacting with the EchoView Git repository.

These helpers encapsulate the Git workflows needed by the web UI to
check update status, show history, create restore points, and perform
update/rollback operations.  They are written defensively so that the
UI can surface useful error messages to the user instead of exposing
raw stack traces.
"""

import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from echoview.config import UPDATE_BRANCH, VIEWER_HOME
from echoview.utils import log_message

DEFAULT_REMOTE = "origin"
RESTORE_POINTS_FILE = os.path.join(VIEWER_HOME, "restore_points.json")


class GitError(RuntimeError):
    """Raised when a Git command fails."""

    def __init__(self, message: str, command: Optional[Iterable[str]] = None, output: Optional[str] = None):
        super().__init__(message)
        self.command = list(command) if command else None
        self.output = output


def run_git_cmd(args: List[str], cwd: str = VIEWER_HOME, check: bool = True) -> subprocess.CompletedProcess:
    """
    Invoke a Git command and return the CompletedProcess.  Raises GitError
    with the captured output when the command fails so callers can show a
    useful error to the user.
    """
    cmd = ["git"] + args
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )
        return completed
    except FileNotFoundError as exc:
        raise GitError("Git is not installed or not available in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stderr or exc.stdout or "").strip()
        raise GitError(output or "Git command failed.", command=cmd, output=output) from exc


def ensure_git_repo(path: str = VIEWER_HOME) -> None:
    """Ensure the supplied path is a Git repository."""
    try:
        result = run_git_cmd(["rev-parse", "--is-inside-work-tree"], cwd=path)
    except GitError as exc:
        raise GitError("EchoView directory is not a Git repository.") from exc
    if result.stdout.strip() != "true":
        raise GitError("EchoView directory is not a Git repository.")


def has_uncommitted_changes() -> bool:
    """Return True if there are uncommitted or untracked changes."""
    ensure_git_repo()
    result = run_git_cmd(["status", "--porcelain"])
    return bool(result.stdout.strip())


def get_current_branch() -> str:
    ensure_git_repo()
    result = run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.strip()
    if branch == "HEAD":
        raise GitError("Repository is in a detached HEAD state; updates are disabled.")
    return branch


def get_remote_name() -> str:
    """
    Return the remote EchoView should use for update checks.  Falls back
    to the default when UPDATE_BRANCH points to a local-only branch.
    """
    ensure_git_repo()
    result = run_git_cmd(["remote"])
    remotes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not remotes:
        raise GitError("No Git remotes are configured; updates cannot be checked.")
    if DEFAULT_REMOTE in remotes:
        return DEFAULT_REMOTE
    if len(remotes) == 1:
        return remotes[0]
    # Multiple remotes and no origin, prefer one that tracks UPDATE_BRANCH if present.
    for remote in remotes:
        try:
            run_git_cmd(["rev-parse", f"{remote}/{UPDATE_BRANCH}"], check=True)
            return remote
        except GitError:
            continue
    return remotes[0]


def _commit_details(ref: str) -> Dict[str, Any]:
    """
    Return a dictionary describing the commit referenced by *ref*.
    Keys include: hash, short_hash, author, email, date_iso, relative_time, subject.
    """
    ensure_git_repo()
    fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%cI%x1f%cr%x1f%s"
    result = run_git_cmd(["show", "-s", f"--format={fmt}", ref])
    data = result.stdout.strip().split("\x1f")
    if len(data) < 7:
        raise GitError(f"Could not parse commit information for {ref}.")
    return {
        "hash": data[0],
        "short_hash": data[1],
        "author": data[2],
        "email": data[3],
        "date_iso": data[4],
        "relative_time": data[5],
        "subject": data[6],
    }


def _optional_commit_details(ref: str) -> Optional[Dict[str, Any]]:
    try:
        return _commit_details(ref)
    except GitError:
        return None


def _count_commits(range_expr: str) -> int:
    try:
        output = run_git_cmd(["rev-list", "--count", range_expr], check=True).stdout.strip()
        return int(output or "0")
    except GitError:
        return 0


def _fetch_remote(remote: str, branch: str) -> None:
    run_git_cmd(["fetch", remote, branch])


def get_update_status(fetch_remote: bool = True) -> Dict[str, Any]:
    """
    Return a dictionary describing the repository update status.
    Includes information about the current, remote latest, and previous commits,
    along with ahead/behind counts.
    """
    ensure_git_repo()
    branch = get_current_branch()
    remote = get_remote_name()
    if fetch_remote:
        try:
            _fetch_remote(remote, branch)
        except GitError as exc:
            log_message(f"Git fetch failed while checking status: {exc}")
            # Proceed with existing information while surfacing the error.
            fetch_error = str(exc)
        else:
            fetch_error = None
    else:
        fetch_error = None

    current = _commit_details("HEAD")
    latest = _optional_commit_details(f"{remote}/{branch}")
    previous = _optional_commit_details("HEAD^")
    behind_count = _count_commits(f"HEAD..{remote}/{branch}") if latest else 0
    ahead_count = _count_commits(f"{remote}/{branch}..HEAD") if latest else 0

    return {
        "branch": branch,
        "remote": remote,
        "current_commit": current,
        "latest_commit": latest,
        "previous_commit": previous,
        "behind_count": behind_count,
        "ahead_count": ahead_count,
        "is_behind": behind_count > 0,
        "is_ahead": ahead_count > 0,
        "fetch_error": fetch_error,
    }


def get_update_history(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Return the most recent *limit* commits on the current branch.
    Each entry includes commit metadata and decoration (tags/branches).
    """
    ensure_git_repo()
    fmt = "%H%x1f%h%x1f%an%x1f%ae%x1f%cI%x1f%cr%x1f%s%x1f%d%x1e"
    result = run_git_cmd(["log", f"--pretty=format:{fmt}", "-n", str(limit)])
    entries = []
    raw = result.stdout.strip()
    if not raw:
        return entries
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 8:
            continue
        decorations = parts[7].strip()
        entries.append(
            {
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "email": parts[3],
                "date_iso": parts[4],
                "relative_time": parts[5],
                "subject": parts[6],
                "decorations": decorations.strip("() ") if decorations else "",
            }
        )
    return entries


def _file_hash(ref: str, path: str) -> str:
    try:
        return run_git_cmd(["rev-parse", f"{ref}:{path}"]).stdout.strip()
    except GitError:
        return ""


def _ensure_clean_worktree() -> None:
    if has_uncommitted_changes():
        raise GitError("Uncommitted changes detected. Commit or stash changes before continuing.")


def _ensure_not_ahead(remote: str, branch: str) -> None:
    ahead = _count_commits(f"{remote}/{branch}..HEAD")
    if ahead > 0:
        raise GitError(
            "Local branch has commits that are not on the remote. Push or back up those commits before updating."
        )


def update_to_latest(target_branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Reset the working tree to match the remote tracking branch.
    Returns metadata about the operation including whether setup.sh changed.
    """
    ensure_git_repo()
    _ensure_clean_worktree()
    remote = get_remote_name()
    branch = target_branch or get_current_branch()
    _fetch_remote(remote, branch)
    try:
        run_git_cmd(["rev-parse", f"{remote}/{branch}"])
    except GitError:
        raise GitError(f"Remote branch {remote}/{branch} was not found.")
    run_git_cmd(["checkout", branch])
    _ensure_not_ahead(remote, branch)
    current_before = _commit_details("HEAD")
    setup_before = _file_hash("HEAD", "setup.sh")

    run_git_cmd(["reset", "--hard", f"{remote}/{branch}"])

    current_after = _commit_details("HEAD")
    setup_after = _file_hash("HEAD", "setup.sh")

    setup_changed = bool(setup_before and setup_after and setup_before != setup_after)
    return {
        "branch": branch,
        "remote": remote,
        "before": current_before,
        "after": current_after,
        "setup_changed": setup_changed,
    }


def rollback_to_previous() -> Dict[str, Any]:
    """Reset the working tree to the previous commit."""
    ensure_git_repo()
    _ensure_clean_worktree()
    if not _optional_commit_details("HEAD^"):
        raise GitError("No previous commit is available for rollback.")

    current_before = _commit_details("HEAD")
    setup_before = _file_hash("HEAD", "setup.sh")
    run_git_cmd(["reset", "--hard", "HEAD^"])
    current_after = _commit_details("HEAD")
    setup_after = _file_hash("HEAD", "setup.sh")

    return {
        "before": current_before,
        "after": current_after,
        "target": "HEAD^",
        "setup_changed": bool(setup_before and setup_after and setup_before != setup_after),
    }


def restore_to_ref(ref: str) -> Dict[str, Any]:
    """Reset the working tree to the supplied Git ref."""
    ensure_git_repo()
    _ensure_clean_worktree()
    run_git_cmd(["rev-parse", "--verify", ref])

    current_before = _commit_details("HEAD")
    setup_before = _file_hash("HEAD", "setup.sh")
    run_git_cmd(["reset", "--hard", ref])
    current_after = _commit_details("HEAD")
    setup_after = _file_hash("HEAD", "setup.sh")
    return {
        "before": current_before,
        "after": current_after,
        "target": ref,
        "setup_changed": bool(setup_before and setup_after and setup_before != setup_after),
    }


def _load_manifest() -> Dict[str, Any]:
    if not os.path.exists(RESTORE_POINTS_FILE):
        return {"points": []}
    try:
        with open(RESTORE_POINTS_FILE, "r") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        data = {"points": []}
    if isinstance(data, list):
        data = {"points": data}
    data.setdefault("points", [])
    return data


def _save_manifest(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(RESTORE_POINTS_FILE), exist_ok=True)
    with open(RESTORE_POINTS_FILE, "w") as handle:
        json.dump(data, handle, indent=2)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def create_restore_point(label: str, commit: str = "HEAD", description: Optional[str] = None) -> Dict[str, Any]:
    """Create a Git tag tracking a restore point and record metadata."""
    ensure_git_repo()
    if not label or not label.strip():
        raise GitError("Restore point name cannot be empty.")

    slug = _slugify(label)
    if not slug:
        raise GitError("Restore point name must include letters or numbers.")

    tag_name = f"ev-restore-{slug.lower()}"

    manifest = _load_manifest()
    for point in manifest["points"]:
        if point.get("tag") == tag_name:
            raise GitError("A restore point with that name already exists.")

    commit_hash = run_git_cmd(["rev-parse", commit]).stdout.strip()
    run_git_cmd(["tag", tag_name, commit_hash])

    created_at = datetime.utcnow().isoformat() + "Z"
    entry = {
        "name": label.strip(),
        "tag": tag_name,
        "commit": commit_hash,
        "description": description.strip() if description else "",
        "created_at": created_at,
    }
    manifest["points"].append(entry)
    manifest["points"].sort(key=lambda item: item.get("created_at", ""), reverse=True)
    _save_manifest(manifest)

    log_message(f"Created restore point '{label}' at {commit_hash[:7]}")
    entry_with_commit = dict(entry)
    entry_with_commit["commit_info"] = _commit_details(tag_name)
    entry_with_commit["missing"] = False
    return entry_with_commit


def list_restore_points() -> List[Dict[str, Any]]:
    """Return restore point metadata along with commit details."""
    ensure_git_repo()
    manifest = _load_manifest()
    points: List[Dict[str, Any]] = []
    updated_manifest = {"points": []}
    for entry in manifest.get("points", []):
        point = dict(entry)
        try:
            point["commit_info"] = _commit_details(point["tag"])
            point["missing"] = False
            updated_manifest["points"].append(entry)
        except GitError:
            point["commit_info"] = None
            point["missing"] = True
        points.append(point)
    # Remove entries whose tags were deleted outside the UI.
    if updated_manifest["points"] != manifest.get("points"):
        _save_manifest(updated_manifest)
        points = [p for p in points if not p.get("missing")]
    return points


def delete_restore_point(tag: str) -> None:
    """Delete the Git tag and remove its metadata entry."""
    ensure_git_repo()
    manifest = _load_manifest()
    remaining = [p for p in manifest["points"] if p.get("tag") != tag]
    if len(remaining) == len(manifest["points"]):
        raise GitError("Restore point not found.")
    run_git_cmd(["tag", "-d", tag])
    manifest["points"] = remaining
    _save_manifest(manifest)
    log_message(f"Deleted restore point '{tag}'.")


def restore_to_point(tag: str) -> Dict[str, Any]:
    """Convenience wrapper that restores to a tracked restore point tag."""
    return restore_to_ref(tag)


def get_restore_point(tag: str) -> Optional[Dict[str, Any]]:
    """Return metadata for a specific restore point."""
    manifest = _load_manifest()
    for entry in manifest.get("points", []):
        if entry.get("tag") == tag:
            point = dict(entry)
            try:
                point["commit_info"] = _commit_details(tag)
                point["missing"] = False
            except GitError:
                point["commit_info"] = None
                point["missing"] = True
            return point
    return None
