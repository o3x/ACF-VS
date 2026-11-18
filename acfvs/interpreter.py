"""
ACF-VS 解釈（Interpret）モジュール。

観測された事実データ（FileEntry のリスト）に対して、現場の規則（連番のまとめ方、
(old) アーカイブ判定、カット/種別の名札付け）を後から適用する。

バージョン: 0.4.3
更新日時: Wed Nov 18 14:31:28 JST 2026
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .models import FileEntry, Observation, SequenceGroup
from .profile import CutProfile, SlotRule

DEFAULT_ARCHIVE_MARKERS = ("(old)",)


@dataclass(frozen=True)
class InterpretRules:
    """解釈に使う現場ルール設定。"""

    archive_markers: tuple[str, ...] = DEFAULT_ARCHIVE_MARKERS
    seq_min_digits: int = 4
    seq_min_count: int = 2


def is_archived_path(path: str, rules: InterpretRules | None = None) -> bool:
    """パスがアーカイブ領域（(old) 等）に属するかを判定する。"""
    active_rules = rules or InterpretRules()
    lower_path = path.lower()
    return any(marker.lower() in lower_path for marker in active_rules.archive_markers)


def extract_unit_name(path: str) -> str:
    """
    パスから最上位フォルダー（カット番号や種別など）をユニット名として抽出する。
    ルート直下のファイルの場合は "" を返す。
    """
    parts = path.split("/")
    if len(parts) <= 1:
        return ""
    return parts[0]


def group_sequences(
    entries: list[FileEntry],
    rules: InterpretRules | None = None,
) -> tuple[dict[str, SequenceGroup], dict[str, FileEntry]]:
    """
    FileEntry のリストを「連番グループ」と「単一ファイル」に仕分ける。

    連番グループのキーにはコマ範囲を含めない（例: "CELL/A/A_####.tga"）。
    これにより、連番に1枚追加されても別物扱いにならず、増減として追跡できる。
    """
    active_rules = rules or InterpretRules()
    pattern = re.compile(rf"^(.*?)([0-9]{{{active_rules.seq_min_digits},}})\.([a-zA-Z0-9]+)$")

    candidates: dict[tuple[str, str, str, int], list[tuple[int, FileEntry]]] = defaultdict(list)
    singles: dict[str, FileEntry] = {}

    for entry in entries:
        if "/" in entry.path:
            dir_path, filename = entry.path.rsplit("/", 1)
        else:
            dir_path, filename = "", entry.path

        match = pattern.match(filename)
        if not match:
            singles[entry.path] = entry
            continue

        prefix, num_str, ext = match.groups()
        digits = len(num_str)
        candidates[(dir_path, prefix, ext, digits)].append((int(num_str), entry))

    groups: dict[str, SequenceGroup] = {}
    for (dir_path, prefix, ext, digits), frames in candidates.items():
        if len(frames) < active_rules.seq_min_count:
            for _, entry in frames:
                singles[entry.path] = entry
            continue

        frames.sort(key=lambda item: item[0])
        placeholder = "#" * digits
        key_name = f"{prefix}{placeholder}.{ext}"
        full_key = f"{dir_path}/{key_name}" if dir_path else key_name

        # 同じディレクトリ・プレフィックスで桁数が異なる稀有なケースの衝突回避
        if full_key in groups:
            for _, entry in frames:
                singles[entry.path] = entry
            continue

        groups[full_key] = SequenceGroup(
            key=full_key,
            dir_path=dir_path,
            prefix=prefix,
            ext=ext,
            digits=digits,
            frames=frames,
        )

    return groups, singles


def classify_material_kind(path: str, rules: InterpretRules | None = None) -> str:
    """パスや拡張子から撮影素材の種別（名札）を推定する。"""
    if is_archived_path(path, rules):
        return "(old) アーカイブ"

    lower = path.lower()
    if lower.endswith((".aep", ".aepx")):
        return "AEP (コンポ)"

    parts = [p for p in lower.split("/") if p]
    dir_tokens = " ".join(parts[:-1]) if len(parts) > 1 else ""
    check_target = dir_tokens or lower

    if any(k in check_target for k in ("harikomi", "ハリコミ", "貼り込み")):
        return "ハリコミ素材"
    if any(k in check_target for k in ("monitor", "モニター")):
        return "モニター素材"
    if any(k in check_target for k in ("3dcg", "3d", "cg")):
        return "3DCG / CG"
    if any(k in check_target for k in ("cell", "cel", "セル", "仕上")):
        return "CELL (セル)"
    if any(k in check_target for k in ("bg", "背景", "book")):
        return "BG (背景)"
    if any(k in check_target for k in ("render", "撮出", "output", "preview")):
        return "撮出し / 出力"
    return "その他"


@dataclass
class InventoryItem:
    """現在地一覧の1項目（単一ファイルまたは連番グループ）。"""

    kind: str
    path: str
    is_sequence: bool
    detail: str
    total_size: int
    duplicate_paths: list[str] = field(default_factory=list)
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "is_sequence": self.is_sequence,
            "detail": self.detail,
            "total_size": self.total_size,
            "duplicate_paths": self.duplicate_paths,
            "unit": self.unit,
        }


@dataclass
class InventoryReport:
    """観測データから読み解いたフォルダーの現在地レポート。"""

    label: str
    taken_at: str
    total_files: int
    items: list[InventoryItem] = field(default_factory=list)
    by_kind_counts: dict[str, int] = field(default_factory=dict)
    duplicate_groups: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "taken_at": self.taken_at,
            "total_files": self.total_files,
            "by_kind_counts": self.by_kind_counts,
            "duplicate_groups": self.duplicate_groups,
            "items": [i.to_dict() for i in self.items],
        }


def build_inventory(
    obs: Observation,
    *,
    subpath: str = "",
    rules: InterpretRules | None = None,
) -> InventoryReport:
    """観測データから「素材種別ごとの現在地・重複」を組み立てる。"""
    active_rules = rules or InterpretRules()
    clean_sub = subpath.strip("/").replace("\\", "/")
    entries = obs.entries
    if clean_sub:
        prefix = clean_sub + "/"
        entries = [
            FileEntry(
                path=e.path[len(prefix):],
                size=e.size,
                mtime_ns=e.mtime_ns,
                mtime_iso=e.mtime_iso,
                sha256=e.sha256,
                hash_reused=e.hash_reused,
                error=e.error,
            )
            for e in obs.entries
            if e.path.startswith(prefix)
        ]

    seqs, singles = group_sequences(entries, active_rules)

    # 重複マップ（連番フレームの止め・空コマや(old)は除外し、単一ファイルのみ対象にする）
    hash_map: dict[str, list[str]] = defaultdict(list)
    for path, e in singles.items():
        if e.sha256 and not is_archived_path(path, active_rules):
            hash_map[e.sha256].append(path)

    duplicate_groups = [
        {"sha256": digest, "paths": sorted(paths)}
        for digest, paths in sorted(hash_map.items())
        if len(paths) > 1
    ]

    items: list[InventoryItem] = []
    kind_counts: dict[str, int] = defaultdict(int)

    for key in sorted(seqs.keys()):
        grp = seqs[key]
        kind = classify_material_kind(grp.key, active_rules)
        kind_counts[kind] += 1
        total_sz = sum(f.size for _, f in grp.frames)
        items.append(
            InventoryItem(
                kind=kind,
                path=grp.key,
                is_sequence=True,
                detail=grp.frame_range_label,
                total_size=total_sz,
                unit=extract_unit_name(grp.key),
            )
        )

    for path in sorted(singles.keys()):
        e = singles[path]
        kind = classify_material_kind(path, active_rules)
        kind_counts[kind] += 1
        dups: list[str] = []
        if (
            e.sha256
            and not is_archived_path(path, active_rules)
            and len(hash_map.get(e.sha256, [])) > 1
        ):
            dups = [p for p in hash_map[e.sha256] if p != path]
        detail = f"{e.size:,} B"
        if e.error:
            detail = f"読込エラー: {e.error}"
        items.append(
            InventoryItem(
                kind=kind,
                path=path,
                is_sequence=False,
                detail=detail,
                total_size=e.size,
                duplicate_paths=dups,
                unit=extract_unit_name(path),
            )
        )

    items.sort(key=lambda it: (it.kind, it.path))
    return InventoryReport(
        label=obs.header.root_label,
        taken_at=obs.header.taken_at,
        total_files=len(entries),
        items=items,
        by_kind_counts=dict(kind_counts),
        duplicate_groups=duplicate_groups,
    )


@dataclass
class SlotPackage:
    """スロット内の1つの塊（撮入れフォルダー全体、または単一ファイル）。"""

    name: str
    rel_path: str
    is_folder: bool
    file_count: int
    seq_count: int
    total_size: int
    package_hash: str | None = None
    duplicate_of: list[str] = field(default_factory=list)
    items: list[InventoryItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rel_path": self.rel_path,
            "is_folder": self.is_folder,
            "file_count": self.file_count,
            "seq_count": self.seq_count,
            "total_size": self.total_size,
            "package_hash": self.package_hash,
            "duplicate_of": self.duplicate_of,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class SlotStatus:
    """1スロット（CELL/BG/3D 等）の現在地。"""

    slot_name: str
    slot_label: str
    folder: str
    state: str  # "ok" | "multiple" | "empty"
    active_packages: list[SlotPackage] = field(default_factory=list)
    archived_packages: list[SlotPackage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_name": self.slot_name,
            "slot_label": self.slot_label,
            "folder": self.folder,
            "state": self.state,
            "active_packages": [p.to_dict() for p in self.active_packages],
            "archived_packages": [p.to_dict() for p in self.archived_packages],
        }


@dataclass
class CutOverviewReport:
    """カットフォルダー全体の「スロット×塊」俯瞰レポート。"""

    label: str
    taken_at: str
    profile_name: str
    slots: list[SlotStatus] = field(default_factory=list)
    unclassified_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "taken_at": self.taken_at,
            "profile_name": self.profile_name,
            "slots": [s.to_dict() for s in self.slots],
            "unclassified_paths": self.unclassified_paths,
        }


def _compute_package_hash(entries: list[FileEntry], base_prefix: str) -> str | None:
    """塊の中の全ファイル（相対パス＋sha256）から塊全体の結合ハッシュを計算する。"""
    if not entries or any(e.sha256 is None for e in entries):
        return None
    hasher = hashlib.sha256()
    for e in sorted(entries, key=lambda x: x.path):
        inner_rel = e.path[len(base_prefix):] if base_prefix and e.path.startswith(base_prefix) else e.path
        hasher.update(f"{inner_rel}:{e.sha256}\n".encode("utf-8"))
    return hasher.hexdigest()


def _entries_to_package(
    name: str,
    rel_path: str,
    is_folder: bool,
    entries: list[FileEntry],
    rules: InterpretRules,
) -> SlotPackage:
    seqs, singles = group_sequences(entries, rules)
    items: list[InventoryItem] = []

    for key in sorted(seqs.keys()):
        grp = seqs[key]
        items.append(
            InventoryItem(
                kind="連番",
                path=grp.key,
                is_sequence=True,
                detail=grp.frame_range_label,
                total_size=sum(f.size for _, f in grp.frames),
            )
        )
    for path in sorted(singles.keys()):
        e = singles[path]
        items.append(
            InventoryItem(
                kind="ファイル",
                path=path,
                is_sequence=False,
                detail=f"{e.size:,} B",
                total_size=e.size,
            )
        )

    prefix = (rel_path + "/") if is_folder else ""
    return SlotPackage(
        name=name,
        rel_path=rel_path,
        is_folder=is_folder,
        file_count=len(entries),
        seq_count=len(seqs),
        total_size=sum(e.size for e in entries),
        package_hash=_compute_package_hash(entries, prefix),
        items=items,
    )


def build_slot_overview(
    obs: Observation,
    profile: CutProfile | None = None,
    *,
    subpath: str = "",
) -> CutOverviewReport:
    """観測データを作品プロファイルのスロット＆塊（パッケージ）単位で俯瞰する。"""
    active_profile = profile or CutProfile.default()
    rules = InterpretRules(archive_markers=active_profile.archive_markers)

    clean_sub = subpath.strip("/").replace("\\", "/")
    entries = obs.entries
    if clean_sub:
        prefix = clean_sub + "/"
        entries = [
            FileEntry(
                path=e.path[len(prefix):],
                size=e.size,
                mtime_ns=e.mtime_ns,
                mtime_iso=e.mtime_iso,
                sha256=e.sha256,
                hash_reused=e.hash_reused,
                error=e.error,
            )
            for e in obs.entries
            if e.path.startswith(prefix)
        ]

    # パッケージハッシュの重複検知（同じ塊が別名・(old)等に存在するかを塊単位で把握）
    all_packages: list[SlotPackage] = []
    slot_statuses: list[SlotStatus] = []
    claimed_paths: set[str] = set()

    for slot in active_profile.slots:
        active_buckets: dict[str, tuple[bool, list[FileEntry]]] = defaultdict(lambda: (False, []))
        archive_buckets: dict[str, tuple[bool, list[FileEntry]]] = defaultdict(lambda: (False, []))

        for e in entries:
            p = e.path
            # スロットへの所属判定
            if slot.folder == "":
                # ルート直下スロット（例: AEP）
                if "/" in p:
                    first, rest = p.split("/", 1)
                    if first.lower() == "(old)" and "/" not in rest:
                        if not slot.extensions or any(rest.lower().endswith(ext) for ext in slot.extensions):
                            claimed_paths.add(p)
                            _, lst = archive_buckets[rest]
                            archive_buckets[rest] = (False, lst + [e])
                    continue
                if slot.extensions and not any(p.lower().endswith(ext) for ext in slot.extensions):
                    continue
                claimed_paths.add(p)
                _, lst = active_buckets[p]
                active_buckets[p] = (False, lst + [e])
            else:
                slot_prefix = slot.folder + "/"
                if not p.startswith(slot_prefix):
                    continue
                claimed_paths.add(p)
                inner = p[len(slot_prefix):]
                parts = inner.split("/")

                # (old) 配下か？
                if parts[0].lower() == "(old)":
                    if len(parts) == 1:
                        continue
                    pkg_name = parts[1]
                    is_dir = len(parts) > 2
                    _, lst = archive_buckets[pkg_name]
                    archive_buckets[pkg_name] = (is_dir, lst + [e])
                else:
                    pkg_name = parts[0]
                    is_dir = len(parts) > 1
                    _, lst = active_buckets[pkg_name]
                    active_buckets[pkg_name] = (is_dir, lst + [e])

        active_pkgs: list[SlotPackage] = []
        for name, (is_dir, pkg_entries) in sorted(active_buckets.items()):
            rel_path = f"{slot.folder}/{name}" if slot.folder else name
            pkg = _entries_to_package(name, rel_path, is_dir, pkg_entries, rules)
            active_pkgs.append(pkg)
            all_packages.append(pkg)

        archive_pkgs: list[SlotPackage] = []
        for name, (is_dir, pkg_entries) in sorted(archive_buckets.items()):
            rel_path = f"{slot.folder}/(old)/{name}" if slot.folder else f"(old)/{name}"
            pkg = _entries_to_package(name, rel_path, is_dir, pkg_entries, rules)
            archive_pkgs.append(pkg)
            all_packages.append(pkg)

        if not active_pkgs:
            state = "empty"
        elif len(active_pkgs) == 1:
            state = "ok"
        else:
            state = "multiple"

        slot_statuses.append(
            SlotStatus(
                slot_name=slot.name,
                slot_label=slot.label,
                folder=slot.folder or "(ルート)",
                state=state,
                active_packages=active_pkgs,
                archived_packages=archive_pkgs,
            )
        )

    # 塊単位の完全一致チェック（別名・(old)と同じ塊があるか）
    pkg_hash_map: dict[str, list[str]] = defaultdict(list)
    for pkg in all_packages:
        if pkg.package_hash:
            pkg_hash_map[pkg.package_hash].append(pkg.rel_path)
    for pkg in all_packages:
        if pkg.package_hash and len(pkg_hash_map[pkg.package_hash]) > 1:
            pkg.duplicate_of = [p for p in pkg_hash_map[pkg.package_hash] if p != pkg.rel_path]

    unclassified = sorted(e.path for e in entries if e.path not in claimed_paths)

    return CutOverviewReport(
        label=obs.header.root_label,
        taken_at=obs.header.taken_at,
        profile_name=active_profile.profile_name,
        slots=slot_statuses,
        unclassified_paths=unclassified,
    )
