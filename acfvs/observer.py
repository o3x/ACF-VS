"""
ACF-VS 観測（Observe）モジュール。

対象フォルダーを非破壊で走査し、ファイルの事実情報（相対パス・サイズ・更新日時・SHA-256）を
JSONL 形式の観測データとして記録・読み込みする。

バージョン: 0.4.0
更新日時: Wed Nov 18 11:28:37 JST 2026
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import secrets
import socket
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .models import FileEntry, Observation, ObservationHeader

DEFAULT_EXCLUDE_DIRS = frozenset({
    ".git",
    ".acfvs",
    ".acvs_history",
    "__pycache__",
})

DEFAULT_EXCLUDE_FILES = frozenset({
    ".gitignore",
    "Thumbs.db",
    ".DS_Store",
    "desktop.ini",
})


def normalize_rel_path(rel_path: str) -> str:
    """比較・保存用にパスを正規化する（NFC正規化＋スラッシュ統一）。"""
    return unicodedata.normalize("NFC", rel_path.replace("\\", "/"))


def _compute_sha256(file_path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """ストリーム読み込みでファイルの SHA-256 を計算する。"""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _format_mtime_iso(mtime_ns: int) -> str:
    """ナノ秒エポックをローカルタイムゾーン付き ISO8601 に変換する。"""
    sec = mtime_ns / 1_000_000_000
    dt = datetime.fromtimestamp(sec, tz=timezone.utc).astimezone()
    return dt.isoformat(timespec="milliseconds")


def _generate_observation_id(host: str) -> str:
    """複数マシンで衝突しない観測IDを生成する。"""
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_host = "".join(c if c.isalnum() or c in "-_" else "-" for c in host)[:20] or "HOST"
    rand = secrets.token_hex(2)
    return f"{now_utc}-{safe_host}-{rand}"


def observe_directory(
    root_dir: str | Path,
    *,
    subpath: str = "",
    label: str = "",
    depth: str = "content",
    note: str = "",
    trigger: str = "manual",
    exclude_dirs: frozenset[str] = DEFAULT_EXCLUDE_DIRS,
    exclude_files: frozenset[str] = DEFAULT_EXCLUDE_FILES,
    previous: Observation | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    max_workers: int = 4,
) -> Observation:
    """
    フォルダーを走査して Observation を構築する（ファイルの実体は一切変更しない）。

    previous が指定されている場合、相対パス・サイズ・mtime_ns が完全一致し、
    かつ前回 sha256 が計算済みであればハッシュ再計算を省略して引き継ぐ。
    """
    if depth not in ("stat", "content"):
        raise ValueError(f"未対応の depth 指定です: {depth} ('stat' または 'content')")

    root_path = Path(root_dir).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"対象フォルダーが見つかりません: {root_path}")

    scan_base = (root_path / subpath).resolve() if subpath else root_path
    if not scan_base.exists() or not scan_base.is_dir():
        raise FileNotFoundError(f"指定されたサブパスが見つかりません: {scan_base}")

    prev_map = previous.by_path() if previous is not None else {}

    # 1. ファイル一覧の収集
    targets: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(scan_base):
        # 除外ディレクトリをスキップ
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs)
        for fname in sorted(filenames):
            if fname in exclude_files or fname.startswith(".cut_manifest"):
                continue
            full_path = Path(dirpath) / fname
            try:
                rel = full_path.relative_to(root_path)
            except ValueError:
                rel = full_path.relative_to(scan_base)
            rel_str = normalize_rel_path(str(rel))
            targets.append((rel_str, full_path))

    total = len(targets)

    # 2. stat 取得＋必要に応じた sha256 計算
    def _inspect_one(item: tuple[str, Path]) -> FileEntry:
        rel_str, full_path = item
        try:
            st = full_path.stat()
            size = st.st_size
            mtime_ns = st.st_mtime_ns
            mtime_iso = _format_mtime_iso(mtime_ns)
        except OSError as exc:
            return FileEntry(
                path=rel_str,
                size=0,
                mtime_ns=0,
                mtime_iso="",
                error=f"stat失敗: {exc}",
            )

        if depth == "stat":
            return FileEntry(
                path=rel_str,
                size=size,
                mtime_ns=mtime_ns,
                mtime_iso=mtime_iso,
            )

        # 前回観測に同一 stat の sha256 があれば再利用
        prev_entry = prev_map.get(rel_str)
        if (
            prev_entry is not None
            and prev_entry.sha256 is not None
            and prev_entry.size == size
            and prev_entry.mtime_ns == mtime_ns
        ):
            return FileEntry(
                path=rel_str,
                size=size,
                mtime_ns=mtime_ns,
                mtime_iso=mtime_iso,
                sha256=prev_entry.sha256,
                hash_reused=True,
            )

        try:
            digest = _compute_sha256(full_path)
            return FileEntry(
                path=rel_str,
                size=size,
                mtime_ns=mtime_ns,
                mtime_iso=mtime_iso,
                sha256=digest,
                hash_reused=False,
            )
        except OSError as exc:
            return FileEntry(
                path=rel_str,
                size=size,
                mtime_ns=mtime_ns,
                mtime_iso=mtime_iso,
                error=f"読込失敗: {exc}",
            )

    entries: list[FileEntry] = []
    if total == 0:
        if progress_cb:
            progress_cb(0, 0)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_inspect_one, t): t[0] for t in targets}
            done_count = 0
            for fut in as_completed(future_map):
                entries.append(fut.result())
                done_count += 1
                if progress_cb and (done_count % 10 == 0 or done_count == total):
                    progress_cb(done_count, total)

    entries.sort(key=lambda e: e.path)

    host = socket.gethostname()
    user = getpass.getuser()
    taken_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    obs_id = _generate_observation_id(host)

    header = ObservationHeader(
        id=obs_id,
        taken_at=taken_at,
        observer_user=user,
        observer_host=host,
        observer_tool="acfvs 0.4.0",
        root_path=str(root_path),
        root_label=label or root_path.name,
        subpath=normalize_rel_path(subpath) if subpath else "",
        exclude=sorted(exclude_dirs | exclude_files),
        depth=depth,
        note=note,
        trigger=trigger,
    )
    return Observation(header=header, entries=entries)


def save_observation(obs: Observation, output_dir: str | Path) -> Path:
    """
    観測データを JSONL ファイルとして保存する（一時ファイル経由でアトミックに置換）。
    """
    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target_path = dest_dir / f"{obs.header.id}.jsonl"
    tmp_path = dest_dir / f".tmp.{obs.header.id}.jsonl"

    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obs.header.to_dict(), ensure_ascii=False) + "\n")
        for entry in obs.entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    os.replace(tmp_path, target_path)
    return target_path


def load_observation(file_path: str | Path) -> Observation:
    """JSONL 観測ファイルを読み込む。"""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"観測ファイルが見つかりません: {p}")

    header: ObservationHeader | None = None
    entries: list[FileEntry] = []

    with p.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"観測ファイルが破損しています ({p}:{line_no}): {exc}") from exc

            if line_no == 1 or raw.get("kind") == "observation":
                header = ObservationHeader.from_dict(raw)
            else:
                entries.append(FileEntry.from_dict(raw))

    if header is None:
        raise ValueError(f"観測ヘッダーが見つかりません: {p}")

    return Observation(header=header, entries=entries)
