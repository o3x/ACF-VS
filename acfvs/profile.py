"""
ACF-VS 作品プロファイル（カットフォルダー構成ルール）モジュール。

作品ごとに異なるカットフォルダー内のスロット構成（CELL/BG/3D/2D/FX/TS等）と、
「フォルダーの塊（パッケージ）」として扱う単位を定義・読み込みする。

バージョン: 0.4.3
更新日時: Wed Nov 18 14:31:28 JST 2026
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SlotRule:
    """カットフォルダー内の1スロット（素材種別領域）の定義。"""

    name: str
    folder: str = ""  # "" はカットルート直下を表す
    label: str = ""
    unit_mode: str = "auto"  # "folder" | "file" | "auto"
    extensions: tuple[str, ...] = ()  # ルート直下で拡張子絞り込みする場合（例: (".aep", ".aepx")）
    description: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SlotRule:
        return cls(
            name=str(raw["name"]),
            folder=str(raw.get("folder", "")),
            label=str(raw.get("label", raw["name"])),
            unit_mode=str(raw.get("unit_mode", "auto")),
            extensions=tuple(str(e).lower() for e in raw.get("extensions", [])),
            description=str(raw.get("description", "")),
        )


@dataclass(frozen=True)
class CutProfile:
    """作品ごとのカットフォルダー構成プロファイル。"""

    profile_name: str = "standard-comp"
    archive_markers: tuple[str, ...] = ("(old)",)
    slots: tuple[SlotRule, ...] = field(default_factory=tuple)

    @classmethod
    def default(cls) -> CutProfile:
        """標準的な撮影カットフォルダー構成プロファイルを返す。"""
        return cls(
            profile_name="standard-comp",
            archive_markers=("(old)",),
            slots=(
                SlotRule(
                    name="AEP",
                    folder="",
                    label="撮影AEP",
                    unit_mode="file",
                    extensions=(".aep", ".aepx"),
                    description="カット直下の撮影AEP",
                ),
                SlotRule(
                    name="CELL",
                    folder="CELL",
                    label="仕上げ (CELL)",
                    unit_mode="folder",
                    description="撮入れフォルダーの塊をそのまま格納",
                ),
                SlotRule(
                    name="BG",
                    folder="BG",
                    label="美術背景 (BG)",
                    unit_mode="auto",
                    description="美術背景データ",
                ),
                SlotRule(
                    name="3D",
                    folder="3D",
                    label="CG素材 (3D)",
                    unit_mode="folder",
                    description="3DCGデータの塊",
                ),
                SlotRule(
                    name="2D",
                    folder="2D",
                    label="2D / モニター",
                    unit_mode="folder",
                    description="モニター・2D素材データの塊",
                ),
                SlotRule(
                    name="FX",
                    folder="FX",
                    label="特技 (FX)",
                    unit_mode="folder",
                    description="特技AEPフォルダー等の塊",
                ),
                SlotRule(
                    name="TS",
                    folder="TS",
                    label="タイムシート (TS)",
                    unit_mode="auto",
                    description="リマップ用タイムシートデータ",
                ),
                SlotRule(
                    name="SATSUDASHI",
                    folder="SATSUDASHI",
                    label="撮出し",
                    unit_mode="auto",
                    description="撮出し・チェック用データ",
                ),
                SlotRule(
                    name="RETAKE",
                    folder="RETAKE",
                    label="リテイク指示",
                    unit_mode="auto",
                    description="リテイク指示書",
                ),
                SlotRule(
                    name="PROXY",
                    folder="(proxy)",
                    label="プロキシ",
                    unit_mode="folder",
                    description="プロキシデータ",
                ),
            ),
        )


def load_profile(target_dir: str | Path, ledger_dir: str | Path | None = None) -> CutProfile:
    """
    プロファイル設定（acfvs_profile.json）を探す。
    優先順: 台帳内 -> 対象フォルダー直下 -> デフォルトプロファイル。
    """
    candidates: list[Path] = []
    if ledger_dir:
        candidates.append(Path(ledger_dir) / "acfvs_profile.json")
    candidates.append(Path(target_dir) / "acfvs_profile.json")

    for path in candidates:
        if path.exists() and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                slots = tuple(SlotRule.from_dict(s) for s in raw.get("slots", []))
                markers = tuple(str(m) for m in raw.get("archive_markers", ["(old)"]))
                return CutProfile(
                    profile_name=str(raw.get("profile_name", path.stem)),
                    archive_markers=markers,
                    slots=slots or CutProfile.default().slots,
                )
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                break

    return CutProfile.default()
