"""
ACF-VS 照合（Compare）モジュール。

二つの観測（過去 vs 現在、別フォルダー同士、全体の一部 vs 別フォルダーなど）を突き合わせ、
証拠の強さ（verified / stat_only）付きの差分結果（CompareResult）を生成する。

バージョン: 0.4.2
更新日時: Wed Nov 18 11:51:08 JST 2026
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .interpreter import (
    InterpretRules,
    extract_unit_name,
    group_sequences,
    is_archived_path,
)
from .models import CompareResult, DiffItem, FileEntry, Observation, SequenceGroup


def _filter_entries(obs: Observation, subpath: str = "") -> list[FileEntry]:
    """指定されたサブパス配下のエントリだけを抽出し、サブパス相対に正規化する。"""
    clean_sub = subpath.strip("/").replace("\\", "/")
    if not clean_sub:
        return list(obs.entries)

    prefix = clean_sub + "/"
    filtered: list[FileEntry] = []
    for entry in obs.entries:
        if entry.path.startswith(prefix):
            rel = entry.path[len(prefix):]
            filtered.append(
                FileEntry(
                    path=rel,
                    size=entry.size,
                    mtime_ns=entry.mtime_ns,
                    mtime_iso=entry.mtime_iso,
                    sha256=entry.sha256,
                    hash_reused=entry.hash_reused,
                    error=entry.error,
                )
            )
    return filtered


def _check_identity(a: FileEntry, b: FileEntry) -> tuple[bool, str]:
    """
    2つの FileEntry が同一かどうかと、その証拠の強さを返す。
    戻り値: (一致とみなせるか, confidence: "verified" | "stat_only" | "n/a")
    """
    if a.sha256 is not None and b.sha256 is not None:
        return (a.sha256 == b.sha256, "verified")
    if a.size == b.size and a.mtime_ns == b.mtime_ns and a.mtime_ns != 0:
        return (True, "stat_only")
    return (False, "stat_only" if (a.sha256 is None or b.sha256 is None) else "verified")


def _identity_key(entry: FileEntry) -> tuple[str, str] | None:
    """移動検知用の識別キーを返す。(種別, 値)。"""
    if entry.sha256 is not None:
        return ("sha256", entry.sha256)
    if entry.mtime_ns != 0:
        return ("stat", f"{entry.size}:{entry.mtime_ns}")
    return None


def _compare_sequence_pair(
    left_grp: SequenceGroup,
    right_grp: SequenceGroup,
) -> DiffItem:
    """同じキーを持つ連番グループ同士を比較し、1つの DiffItem にまとめる。"""
    left_frames = dict(left_grp.frames)
    right_frames = dict(right_grp.frames)

    all_nums = sorted(set(left_frames.keys()) | set(right_frames.keys()))
    added_nums: list[int] = []
    removed_nums: list[int] = []
    updated_nums: list[int] = []
    confidences: set[str] = set()

    for num in all_nums:
        lf = left_frames.get(num)
        rf = right_frames.get(num)
        if lf is None and rf is not None:
            added_nums.append(num)
        elif lf is not None and rf is None:
            removed_nums.append(num)
        elif lf is not None and rf is not None:
            same, conf = _check_identity(lf, rf)
            confidences.add(conf)
            if not same:
                updated_nums.append(num)

    digits = right_grp.digits
    unit = extract_unit_name(right_grp.key)

    if not added_nums and not removed_nums and not updated_nums:
        conf = "verified" if confidences == {"verified"} else "stat_only"
        return DiffItem(
            relation="same",
            confidence=conf,
            path=right_grp.key,
            is_sequence=True,
            detail=f"{right_grp.frame_range_label}",
            unit=unit,
        )

    parts: list[str] = [f"{left_grp.count}枚 → {right_grp.count}枚"]
    if added_nums:
        sample = ", ".join(str(n).zfill(digits) for n in added_nums[:5])
        suffix = "..." if len(added_nums) > 5 else ""
        parts.append(f"+{len(added_nums)}枚({sample}{suffix})")
    if removed_nums:
        sample = ", ".join(str(n).zfill(digits) for n in removed_nums[:5])
        suffix = "..." if len(removed_nums) > 5 else ""
        parts.append(f"-{len(removed_nums)}枚({sample}{suffix})")
    if updated_nums:
        sample = ", ".join(str(n).zfill(digits) for n in updated_nums[:5])
        suffix = "..." if len(updated_nums) > 5 else ""
        parts.append(f"更新{len(updated_nums)}枚({sample}{suffix})")

    conf = "verified" if "verified" in confidences and "stat_only" not in confidences else (
        "stat_only" if confidences else "n/a"
    )
    return DiffItem(
        relation="updated",
        confidence=conf,
        path=right_grp.key,
        is_sequence=True,
        detail=" / ".join(parts),
        unit=unit,
    )


def compare_observations(
    left: Observation,
    right: Observation,
    *,
    left_subpath: str = "",
    right_subpath: str = "",
    rules: InterpretRules | None = None,
    include_same: bool = False,
) -> CompareResult:
    """
    2つの Observation を比較して CompareResult を返す。
    """
    active_rules = rules or InterpretRules()
    left_entries = _filter_entries(left, left_subpath)
    right_entries = _filter_entries(right, right_subpath)

    left_seqs, left_singles = group_sequences(left_entries, active_rules)
    right_seqs, right_singles = group_sequences(right_entries, active_rules)

    items: list[DiffItem] = []

    # 1. 連番グループの比較
    all_seq_keys = sorted(set(left_seqs.keys()) | set(right_seqs.keys()))
    for key in all_seq_keys:
        lg = left_seqs.get(key)
        rg = right_seqs.get(key)
        if lg is not None and rg is not None:
            diff = _compare_sequence_pair(lg, rg)
            if diff.relation != "same" or include_same:
                items.append(diff)
        elif lg is None and rg is not None:
            items.append(
                DiffItem(
                    relation="added",
                    confidence="n/a",
                    path=rg.key,
                    is_sequence=True,
                    detail=rg.frame_range_label,
                    unit=extract_unit_name(rg.key),
                )
            )
        elif lg is not None and rg is None:
            items.append(
                DiffItem(
                    relation="removed",
                    confidence="n/a",
                    path=lg.key,
                    is_sequence=True,
                    detail=lg.frame_range_label,
                    unit=extract_unit_name(lg.key),
                )
            )

    # 2. 単一ファイルの比較（4パス）
    processed_left: set[str] = set()
    processed_right: set[str] = set()

    # Pass 1: パスも中身（またはstat）も一致
    for path in sorted(set(left_singles.keys()) & set(right_singles.keys())):
        le = left_singles[path]
        re_entry = right_singles[path]
        same, conf = _check_identity(le, re_entry)
        if same:
            processed_left.add(path)
            processed_right.add(path)
            if include_same:
                items.append(
                    DiffItem(
                        relation="same",
                        confidence=conf,
                        path=path,
                        unit=extract_unit_name(path),
                    )
                )

    # Pass 2: 移動・アーカイブ検知（未処理の中で同一キーが一致）
    unmatched_left_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path, le in sorted(left_singles.items()):
        if path in processed_left:
            continue
        ikey = _identity_key(le)
        if ikey is not None:
            unmatched_left_by_key[ikey].append(path)

    for path, re_entry in sorted(right_singles.items()):
        if path in processed_right:
            continue
        ikey = _identity_key(re_entry)
        if ikey is None:
            continue
        candidates = unmatched_left_by_key.get(ikey)
        if not candidates:
            continue

        # 同じキー種別が複数ある場合、最初の未使用を対応付け
        old_path = candidates.pop(0)
        processed_left.add(old_path)
        processed_right.add(path)

        conf = "verified" if ikey[0] == "sha256" else "stat_only"
        is_arch = (not is_archived_path(old_path, active_rules)) and is_archived_path(
            path, active_rules
        )
        items.append(
            DiffItem(
                relation="archived" if is_arch else "moved",
                confidence=conf,
                path=path,
                old_path=old_path,
                unit=extract_unit_name(path),
            )
        )

    # Pass 3: 残った right は updated または added
    for path in sorted(right_singles.keys()):
        if path in processed_right:
            continue
        re_entry = right_singles[path]
        if path in left_singles and path not in processed_left:
            processed_left.add(path)
            processed_right.add(path)
            _, conf = _check_identity(left_singles[path], re_entry)
            items.append(
                DiffItem(
                    relation="updated",
                    confidence=conf,
                    path=path,
                    unit=extract_unit_name(path),
                )
            )
        else:
            processed_right.add(path)
            items.append(
                DiffItem(
                    relation="added",
                    confidence="n/a",
                    path=path,
                    unit=extract_unit_name(path),
                )
            )

    # Pass 4: 未処理の left は removed
    for path in sorted(left_singles.keys()):
        if path in processed_left:
            continue
        items.append(
            DiffItem(
                relation="removed",
                confidence="n/a",
                path=path,
                unit=extract_unit_name(path),
            )
        )

    # 3. 重複ファイル検知（連番内の止め/空コマや(old)を除外し、単一ファイルのみ対象）
    hash_to_paths: dict[str, list[str]] = defaultdict(list)
    for path, entry in right_singles.items():
        if entry.sha256 is not None and not is_archived_path(path, active_rules):
            hash_to_paths[entry.sha256].append(path)

    duplicates: list[dict[str, Any]] = []
    for digest, paths in sorted(hash_to_paths.items()):
        if len(paths) > 1:
            duplicates.append({"sha256": digest, "paths": sorted(paths)})

    # 4. サマリ集計
    summary: dict[str, int] = defaultdict(int)
    for item in items:
        summary[item.relation] += 1

    left_label = f"{left.header.root_label} ({left.header.taken_at})"
    right_label = f"{right.header.root_label} ({right.header.taken_at})"

    return CompareResult(
        left_label=left_label,
        right_label=right_label,
        items=items,
        duplicates=duplicates,
        summary=dict(summary),
    )
