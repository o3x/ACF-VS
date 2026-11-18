"""
ACF-VS データモデル定義。

観測（Observation）、ファイル項目（FileEntry）、比較結果（CompareResult）、
工程メモ（WorkNote）など、核全体で共有する不変・構造化データ型を定義する。

バージョン: 0.4.0
更新日時: Wed Nov 18 11:28:37 JST 2026
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileEntry:
    """観測された1ファイルの事実データ。"""

    path: str
    size: int
    mtime_ns: int
    mtime_iso: str
    sha256: str | None = None
    hash_reused: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSONL 1行出力用の辞書に変換する。"""
        data: dict[str, Any] = {
            "path": self.path,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "mtime": self.mtime_iso,
        }
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        if self.hash_reused:
            data["hash_reused"] = True
        if self.error is not None:
            data["error"] = self.error
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FileEntry:
        """辞書から FileEntry を復元する。"""
        return cls(
            path=str(raw["path"]),
            size=int(raw.get("size", 0)),
            mtime_ns=int(raw.get("mtime_ns", 0)),
            mtime_iso=str(raw.get("mtime", "")),
            sha256=raw.get("sha256"),
            hash_reused=bool(raw.get("hash_reused", False)),
            error=raw.get("error"),
        )


@dataclass
class ObservationHeader:
    """観測ファイルの1行目（メタデータ）。"""

    id: str
    taken_at: str
    observer_user: str
    observer_host: str
    observer_tool: str
    root_path: str
    root_label: str
    subpath: str = ""
    exclude: list[str] = field(default_factory=list)
    depth: str = "content"  # "stat" | "content"
    note: str = ""
    trigger: str = "manual"
    format_version: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        """JSONL ヘッダー行用の辞書に変換する。"""
        return {
            "kind": "observation",
            "format": self.format_version,
            "id": self.id,
            "taken_at": self.taken_at,
            "observer": {
                "user": self.observer_user,
                "host": self.observer_host,
                "tool": self.observer_tool,
            },
            "root": {
                "path_as_seen": self.root_path,
                "label": self.root_label,
            },
            "scope": {
                "subpath": self.subpath,
                "exclude": self.exclude,
            },
            "depth": self.depth,
            "note": self.note,
            "trigger": self.trigger,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ObservationHeader:
        """辞書から ObservationHeader を復元する。"""
        observer = raw.get("observer", {})
        root = raw.get("root", {})
        scope = raw.get("scope", {})
        return cls(
            id=str(raw["id"]),
            taken_at=str(raw["taken_at"]),
            observer_user=str(observer.get("user", "")),
            observer_host=str(observer.get("host", "")),
            observer_tool=str(observer.get("tool", "")),
            root_path=str(root.get("path_as_seen", "")),
            root_label=str(root.get("label", "")),
            subpath=str(scope.get("subpath", "")),
            exclude=list(scope.get("exclude", [])),
            depth=str(raw.get("depth", "content")),
            note=str(raw.get("note", "")),
            trigger=str(raw.get("trigger", "manual")),
            format_version=str(raw.get("format", "2.0")),
        )


@dataclass
class Observation:
    """1回の観測結果全体（ヘッダー＋ファイル項目群）。"""

    header: ObservationHeader
    entries: list[FileEntry] = field(default_factory=list)

    def by_path(self) -> dict[str, FileEntry]:
        """正規化パスをキーとした辞書を返す。"""
        return {entry.path: entry for entry in self.entries}


@dataclass
class SequenceGroup:
    """連番として解釈されたファイル群。"""

    key: str  # 例: "c001/CELL/A/A_####.tga"
    dir_path: str
    prefix: str
    ext: str
    digits: int
    frames: list[tuple[int, FileEntry]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.frames)

    @property
    def frame_range_label(self) -> str:
        """例: [0001-0024] (24枚)"""
        if not self.frames:
            return "[]"
        nums = sorted(num for num, _ in self.frames)
        first = str(nums[0]).zfill(self.digits)
        last = str(nums[-1]).zfill(self.digits)
        if first == last:
            return f"[{first}] ({len(nums)}枚)"
        return f"[{first}-{last}] ({len(nums)}枚)"


@dataclass
class DiffItem:
    """照合結果の1項目。"""

    relation: str  # "same" | "updated" | "moved" | "archived" | "added" | "removed"
    confidence: str  # "verified" | "stat_only" | "n/a"
    path: str
    old_path: str | None = None
    is_sequence: bool = False
    detail: str = ""
    unit: str = ""  # 解釈されたカット/ユニット名など

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "confidence": self.confidence,
            "path": self.path,
            "old_path": self.old_path,
            "is_sequence": self.is_sequence,
            "detail": self.detail,
            "unit": self.unit,
        }


@dataclass
class CompareResult:
    """2つの状態の照合結果全体。"""

    left_label: str
    right_label: str
    items: list[DiffItem] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_label": self.left_label,
            "right_label": self.right_label,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
            "duplicates": self.duplicates,
        }


@dataclass
class WorkNote:
    """工程管理用の追記メモ（観測とは独立した追記ログ）。"""

    note_id: str
    created_at: str
    author: str
    host: str
    target_unit: str  # カット番号や相対パスなど（例: "c001" や "c001/CELL" や ""）
    status: str  # 例: "未着手", "素材待ち", "撮影中", "チェック待ち", "リテイク", "完了"
    pinned_path: str = ""  # 正（採用）として指し示すファイル/フォルダ（任意）
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "work_note",
            "note_id": self.note_id,
            "created_at": self.created_at,
            "author": self.author,
            "host": self.host,
            "target_unit": self.target_unit,
            "status": self.status,
            "pinned_path": self.pinned_path,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WorkNote:
        return cls(
            note_id=str(raw["note_id"]),
            created_at=str(raw["created_at"]),
            author=str(raw.get("author", "")),
            host=str(raw.get("host", "")),
            target_unit=str(raw.get("target_unit", "")),
            status=str(raw.get("status", "")),
            pinned_path=str(raw.get("pinned_path", "")),
            comment=str(raw.get("comment", "")),
        )
