"""
ACF-VS 簡易デスクトップ GUI（tkinter / 標準ライブラリのみ）。

カットの「今の構成」をビジュアルに美しく把握し、フォルダーの塊同士（例: 現在の仕上げと (old)）の
比較や過去観測との照合を直感的に行うためのデスクトップビューア。

バージョン: 0.4.8
更新日時: Wed Nov 18 20:52:58 JST 2026
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .comparer import compare_observations
from .interpreter import (
    CutOverviewReport,
    InventoryItem,
    InventoryReport,
    SlotPackage,
    SlotStatus,
    build_inventory,
    build_slot_overview,
)
from .ledger import Ledger, resolve_ledger_dir
from .models import CompareResult, Observation, ObservationHeader, WorkNote
from .observer import DEFAULT_EXCLUDE_DIRS, observe_directory
from .profile import CutProfile, load_profile

STATUS_PRESETS = ("未着手", "素材待ち", "撮影中", "チェック待ち", "リテイク", "完了")


def _format_size(num_bytes: int) -> str:
    """バイト数を人間が読みやすい単位に変換する。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def _open_with_default_app(target_path: Path) -> None:
    """OS の関連付けられたアプリ（またはファイラー）でファイル・フォルダーを開く。"""
    if not target_path.exists():
        raise FileNotFoundError(f"対象が見つかりません（過去の観測のみの項目可能性があります）:\n{target_path}")
    if sys.platform.startswith("win"):
        os.startfile(str(target_path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target_path)])
    else:
        subprocess.Popen(["xdg-open", str(target_path)])


class CutMapCanvas(tk.Canvas):
    """左ペインにカットの構成をビジュアルカードとして描画するキャンバス。"""

    BG_COLOR = "#1e222a"
    HEADER_BG = "#282c34"
    CARD_BG = "#2c313c"
    CARD_EMPTY_BG = "#242830"
    BORDER_OK = "#3fb950"
    BORDER_MULTI = "#d29922"
    BORDER_EMPTY = "#3e4451"
    TEXT_MAIN = "#e6edf3"
    TEXT_SUB = "#8b949e"

    def __init__(self, master: tk.Misc, on_select_slot: Callable[[str], None]) -> None:
        super().__init__(master, bg=self.BG_COLOR, highlightthickness=0, width=320)
        self._on_select_slot = on_select_slot
        self._card_regions: list[tuple[int, int, int, int, str]] = []
        self._last_report: CutOverviewReport | None = None
        self._show_empty: bool = True
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._handle_click)

    def render(self, report: CutOverviewReport) -> None:
        self._last_report = report
        self._redraw()

    def set_show_empty(self, show_empty: bool) -> None:
        self._show_empty = show_empty
        self._redraw()

    def _handle_click(self, event: tk.Event) -> None:
        y = self.canvasy(event.y)
        x = self.canvasx(event.x)
        for x1, y1, x2, y2, slot_name in self._card_regions:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._on_select_slot(slot_name)
                break

    def _redraw(self) -> None:
        self.delete("all")
        self._card_regions.clear()
        width = max(self.winfo_width(), 280)

        if self._last_report is None:
            self.create_text(
                width // 2,
                140,
                text="フォルダーを選択して\n「現在地を見る」を押すと\nカット構成マップが表示されます",
                fill=self.TEXT_SUB,
                font=("Yu Gothic UI", 10),
                justify=tk.CENTER,
            )
            self.configure(scrollregion=(0, 0, width, 300))
            return

        rep = self._last_report
        pad = 12
        y = pad

        # カットヘッダーカード
        total_bytes = sum(p.total_size for s in rep.slots for p in s.active_packages)
        total_pkgs = sum(len(s.active_packages) for s in rep.slots)
        self.create_rectangle(pad, y, width - pad, y + 62, fill=self.HEADER_BG, outline="#3e4451", width=1)
        self.create_text(
            pad + 12,
            y + 18,
            text=f"🎬 {rep.label}",
            fill=self.TEXT_MAIN,
            font=("Yu Gothic UI", 11, "bold"),
            anchor=tk.W,
        )
        self.create_text(
            pad + 12,
            y + 42,
            text=f"通常配置 {total_pkgs}塊 / {_format_size(total_bytes)}  |  {rep.profile_name}",
            fill=self.TEXT_SUB,
            font=("Yu Gothic UI", 8),
            anchor=tk.W,
        )
        y += 74

        # スロットカード群
        card_h = 54
        gap = 7
        for slot in rep.slots:
            if not self._show_empty and not slot.active_packages and not slot.archived_packages:
                continue
            if slot.state == "ok":
                bg = self.CARD_BG
                accent = self.BORDER_OK
                badge = f"{len(slot.active_packages)}件"
            elif slot.state == "multiple":
                bg = self.CARD_BG
                accent = self.BORDER_MULTI
                badge = f"{len(slot.active_packages)}件混在"
            else:
                bg = self.CARD_EMPTY_BG
                accent = self.BORDER_EMPTY
                badge = "空"

            x1, y1, x2, y2 = pad, y, width - pad, y + card_h
            self.create_rectangle(x1, y1, x2, y2, fill=bg, outline="#363b47", width=1)
            # 左端のアクセントバー
            self.create_rectangle(x1, y1, x1 + 5, y2, fill=accent, outline="")

            # スロット名
            self.create_text(
                x1 + 14,
                y1 + 17,
                text=slot.slot_label,
                fill=self.TEXT_MAIN if slot.state != "empty" else self.TEXT_SUB,
                font=("Yu Gothic UI", 9, "bold" if slot.state != "empty" else "normal"),
                anchor=tk.W,
            )

            # 右上バッジ（件数＋(old)数）
            old_part = f" / old:{len(slot.archived_packages)}" if slot.archived_packages else ""
            self.create_text(
                x2 - 10,
                y1 + 17,
                text=f"{badge}{old_part}",
                fill=accent if slot.state != "empty" else self.TEXT_SUB,
                font=("Yu Gothic UI", 8, "bold"),
                anchor=tk.E,
            )

            # 下段: 代表の塊名＋容量
            if slot.active_packages:
                names = ", ".join(p.name for p in slot.active_packages[:2])
                if len(slot.active_packages) > 2:
                    names += f" 他{len(slot.active_packages) - 2}"
                sz = _format_size(sum(p.total_size for p in slot.active_packages))
                sub_text = f"{names}  ({sz})"
            elif slot.archived_packages:
                sub_text = f"(old) に {len(slot.archived_packages)}件"
            else:
                sub_text = "-"

            self.create_text(
                x1 + 14,
                y1 + 38,
                text=sub_text,
                fill=self.TEXT_SUB,
                font=("Yu Gothic UI", 8),
                anchor=tk.W,
            )

            self._card_regions.append((x1, y1, x2, y2, slot.slot_name))
            y += card_h + gap

        self.configure(scrollregion=(0, 0, width, y + pad))


class ACFVSApp(tk.Tk):
    """ACF-VS v0.4.4 プロトタイプ GUI。"""

    def __init__(self, initial_dir: str = "", initial_ledger: str | None = None) -> None:
        super().__init__()
        self.title("ACF-VS v0.4.4 - カット構成＆フォルダー観測ツール")
        self.geometry("1180x760")
        self.minsize(960, 620)

        self.dir_var = tk.StringVar(value=initial_dir)
        self.ledger_var = tk.StringVar(value=initial_ledger or "")
        self.subpath_var = tk.StringVar(value="")
        self.depth_var = tk.StringVar(value="content")
        self.note_var = tk.StringVar(value="")
        self.show_empty_var = tk.BooleanVar(value=True)
        self.status_msg_var = tk.StringVar(value="フォルダーを選択してください。")

        self.unit_var = tk.StringVar(value="")
        self.work_status_var = tk.StringVar(value="撮影中")
        self.pinned_var = tk.StringVar(value="")
        self.comment_var = tk.StringVar(value="")

        self._headers: list[ObservationHeader] = []
        self._current_obs: Observation | None = None
        self._slot_node_iids: dict[str, str] = {}
        self._pkg_rel_paths: dict[str, str] = {}
        self._pkg_hashes: dict[str, str] = {}
        self._slot_item_paths: dict[str, tuple[str, bool]] = {}
        self._inv_item_paths: dict[str, tuple[str, bool]] = {}
        self._busy = False

        self._build_ui()
        if initial_dir:
            self._detect_cut_candidates(initial_dir)
            self.refresh_ledger()
            self._on_inspect_live()

    def _build_ui(self) -> None:
        # 上部: パス指定
        top_frame = ttk.LabelFrame(self, text="対象フォルダー・設定", padding=8)
        top_frame.pack(fill=tk.X, padx=10, pady=(8, 4))

        ttk.Label(top_frame, text="対象フォルダー:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(top_frame, textvariable=self.dir_var, width=68).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(top_frame, text="参照...", command=self._browse_dir).grid(row=0, column=2, padx=2)
        ttk.Button(top_frame, text="台帳再読込", command=self.refresh_ledger).grid(row=0, column=3, padx=2)

        ttk.Label(top_frame, text="カット選択 / 台帳:").grid(row=1, column=0, sticky=tk.W, pady=2)
        sub_frame = ttk.Frame(top_frame)
        sub_frame.grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5)
        self.subpath_combo = ttk.Combobox(sub_frame, textvariable=self.subpath_var, width=20)
        self.subpath_combo.pack(side=tk.LEFT)
        self.subpath_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_inspect_live())
        ttk.Label(sub_frame, text="(話数指定時はここからカット選択)   台帳(任意):").pack(
            side=tk.LEFT, padx=(6, 4)
        )
        ttk.Entry(sub_frame, textvariable=self.ledger_var, width=28).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sub_frame, text="参照...", command=self._browse_ledger).pack(side=tk.LEFT, padx=(4, 0))
        top_frame.columnconfigure(1, weight=1)

        # 操作バー
        action_frame = ttk.Frame(self, padding=(10, 2))
        action_frame.pack(fill=tk.X)

        ttk.Radiobutton(action_frame, text="中身確認 (SHA-256)", variable=self.depth_var, value="content").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Radiobutton(action_frame, text="サイズ・日時のみ", variable=self.depth_var, value="stat").pack(
            side=tk.LEFT, padx=(0, 10)
        )

        self.btn_inspect = ttk.Button(action_frame, text="現在地を見る（更新）", command=self._on_inspect_live)
        self.btn_inspect.pack(side=tk.LEFT, padx=3)

        ttk.Separator(action_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(action_frame, text="メモ:").pack(side=tk.LEFT)
        ttk.Entry(action_frame, textvariable=self.note_var, width=18).pack(side=tk.LEFT, padx=(4, 4))
        self.btn_observe = ttk.Button(action_frame, text="いまの状態を履歴に記録", command=self._on_observe)
        self.btn_observe.pack(side=tk.LEFT, padx=3)

        self.btn_cmp_live = ttk.Button(action_frame, text="最新履歴 vs いま", command=self._on_compare_live)
        self.btn_cmp_live.pack(side=tk.LEFT, padx=3)

        self.btn_cmp_other = ttk.Button(action_frame, text="別フォルダーと比較...", command=self._on_compare_other_dir)
        self.btn_cmp_other.pack(side=tk.LEFT, padx=3)

        # メインペイン: 左=ビジュアル構成マップ / 右=詳細タブ
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左: ビジュアルカット構成マップ
        left_frame = ttk.LabelFrame(paned, text="カット構成マップ（クリックで選択）", padding=4)
        paned.add(left_frame, weight=1)

        map_ctrl = ttk.Frame(left_frame)
        map_ctrl.pack(fill=tk.X, padx=2, pady=(0, 3))
        ttk.Checkbutton(
            map_ctrl,
            text="データの無いスロットも表示",
            variable=self.show_empty_var,
            command=lambda: self.cut_map.set_show_empty(self.show_empty_var.get()),
        ).pack(side=tk.LEFT)

        map_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL)
        self.cut_map = CutMapCanvas(left_frame, on_select_slot=self._focus_slot_in_tree)
        self.cut_map.configure(yscrollcommand=map_scroll.set)
        map_scroll.configure(command=self.cut_map.yview)
        self.cut_map.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        map_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 右: タブ（普段は今の状態、必要なときだけ履歴タブへ）
        self.right_notebook = ttk.Notebook(paned)
        paned.add(self.right_notebook, weight=3)

        # タブ1: カット俯瞰（スロット×塊）
        slot_tab = ttk.Frame(self.right_notebook, padding=6)
        self.right_notebook.add(slot_tab, text="カット俯瞰（スロット×塊）")

        slot_top = ttk.Frame(slot_tab)
        slot_top.pack(fill=tk.X, pady=(0, 4))
        self.slot_summary_var = tk.StringVar(
            value="「現在地を見る」でスロットごとの塊一覧を表示します。2つの塊を選んで比較できます。"
        )
        ttk.Label(slot_top, textvariable=self.slot_summary_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            slot_top,
            text="開く",
            command=lambda: self._open_selected_tree_item(self.slot_tree, self._slot_item_paths),
        ).pack(side=tk.RIGHT, padx=2)
        self.btn_cmp_pkgs = ttk.Button(
            slot_top, text="選択した2つの塊を比較", command=self._on_compare_selected_packages
        )
        self.btn_cmp_pkgs.pack(side=tk.RIGHT, padx=2)
        ttk.Button(slot_top, text="全展開", command=lambda: self._toggle_tree(self.slot_tree, True)).pack(
            side=tk.RIGHT, padx=2
        )
        ttk.Button(slot_top, text="全閉", command=lambda: self._toggle_tree(self.slot_tree, False)).pack(
            side=tk.RIGHT, padx=2
        )

        self.slot_tree = ttk.Treeview(
            slot_tab,
            columns=("state", "detail", "size", "note"),
            show="tree headings",
            selectmode="extended",
        )
        self.slot_tree.heading("#0", text="スロット / 塊（Ctrl+クリックで2つ選択可）")
        self.slot_tree.heading("state", text="配置")
        self.slot_tree.heading("detail", text="内容（連番・ファイル数）")
        self.slot_tree.heading("size", text="容量")
        self.slot_tree.heading("note", text="塊ID / 同一塊")
        self.slot_tree.column("#0", width=270, anchor=tk.W)
        self.slot_tree.column("state", width=85, anchor=tk.CENTER)
        self.slot_tree.column("detail", width=170, anchor=tk.W)
        self.slot_tree.column("size", width=85, anchor=tk.E)
        self.slot_tree.column("note", width=160, anchor=tk.W)
        self.slot_tree.tag_configure("ok", foreground="#0a6e2d")
        self.slot_tree.tag_configure("multiple", foreground="#9c6500")
        self.slot_tree.tag_configure("empty", foreground="#888888")
        self.slot_tree.tag_configure("old", foreground="#6e6e6e")
        self.slot_tree.tag_configure("dup", foreground="#b31b1b")

        slot_scroll = ttk.Scrollbar(slot_tab, orient=tk.VERTICAL, command=self.slot_tree.yview)
        self.slot_tree.configure(yscrollcommand=slot_scroll.set)
        self.slot_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        slot_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.slot_tree.bind(
            "<Double-1>", lambda e: self._on_tree_double_click(e, self.slot_tree, self._slot_item_paths)
        )
        self.slot_tree.bind(
            "<Button-3>", lambda e: self._on_tree_right_click(e, self.slot_tree, self._slot_item_paths)
        )

        # タブ2: フォルダー階層・素材
        inv_tab = ttk.Frame(self.right_notebook, padding=6)
        self.right_notebook.add(inv_tab, text="フォルダー階層・素材")

        inv_top = ttk.Frame(inv_tab)
        inv_top.pack(fill=tk.X, pady=(0, 4))
        self.inv_summary_var = tk.StringVar(value="フォルダー階層ごとに連番・テイクを表示します。")
        ttk.Label(inv_top, textvariable=self.inv_summary_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            inv_top,
            text="開く",
            command=lambda: self._open_selected_tree_item(self.inv_tree, self._inv_item_paths),
        ).pack(side=tk.RIGHT, padx=2)
        ttk.Button(inv_top, text="全展開", command=lambda: self._toggle_tree(self.inv_tree, True)).pack(
            side=tk.RIGHT, padx=2
        )
        ttk.Button(inv_top, text="全閉", command=lambda: self._toggle_tree(self.inv_tree, False)).pack(
            side=tk.RIGHT, padx=2
        )

        self.inv_tree = ttk.Treeview(
            inv_tab,
            columns=("kind", "detail", "size", "dup"),
            show="tree headings",
        )
        self.inv_tree.heading("#0", text="フォルダー / 素材（連番まとめ）")
        self.inv_tree.heading("kind", text="種別")
        self.inv_tree.heading("detail", text="枚数 / 構成")
        self.inv_tree.heading("size", text="容量")
        self.inv_tree.heading("dup", text="重複（単一ファイルのみ）")
        self.inv_tree.column("#0", width=280, anchor=tk.W)
        self.inv_tree.column("kind", width=120, anchor=tk.W)
        self.inv_tree.column("detail", width=150, anchor=tk.W)
        self.inv_tree.column("size", width=85, anchor=tk.E)
        self.inv_tree.column("dup", width=160, anchor=tk.W)
        self.inv_tree.tag_configure("dup", foreground="#b31b1b")
        self.inv_tree.tag_configure("old", foreground="#6e6e6e")
        self.inv_tree.tag_configure("folder", foreground="#1a4b8c")

        inv_scroll = ttk.Scrollbar(inv_tab, orient=tk.VERTICAL, command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=inv_scroll.set)
        self.inv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inv_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.inv_tree.bind(
            "<Double-1>", lambda e: self._on_tree_double_click(e, self.inv_tree, self._inv_item_paths)
        )
        self.inv_tree.bind(
            "<Button-3>", lambda e: self._on_tree_right_click(e, self.inv_tree, self._inv_item_paths)
        )

        # タブ3: 差分・照合結果
        diff_tab = ttk.Frame(self.right_notebook, padding=6)
        self.right_notebook.add(diff_tab, text="差分・照合結果")

        self.diff_summary_var = tk.StringVar(value="比較を実行するとここに結果が表示されます。")
        ttk.Label(diff_tab, textvariable=self.diff_summary_var).pack(fill=tk.X, pady=(0, 4))

        self.diff_tree = ttk.Treeview(
            diff_tab,
            columns=("relation", "confidence", "path", "detail"),
            show="headings",
        )
        self.diff_tree.heading("relation", text="状態")
        self.diff_tree.heading("confidence", text="証拠")
        self.diff_tree.heading("path", text="パス / 連番")
        self.diff_tree.heading("detail", text="詳細 / 移動元")
        self.diff_tree.column("relation", width=95, anchor=tk.CENTER)
        self.diff_tree.column("confidence", width=95, anchor=tk.CENTER)
        self.diff_tree.column("path", width=280, anchor=tk.W)
        self.diff_tree.column("detail", width=240, anchor=tk.W)
        self.diff_tree.tag_configure("added", foreground="#0a6e2d")
        self.diff_tree.tag_configure("removed", foreground="#b31b1b")
        self.diff_tree.tag_configure("updated", foreground="#9c6500")
        self.diff_tree.tag_configure("moved", foreground="#1a5fb4")
        self.diff_tree.tag_configure("archived", foreground="#613583")

        diff_scroll = ttk.Scrollbar(diff_tab, orient=tk.VERTICAL, command=self.diff_tree.yview)
        self.diff_tree.configure(yscrollcommand=diff_scroll.set)
        self.diff_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        diff_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # タブ4: 観測履歴（必要なときだけ開く）
        hist_tab = ttk.Frame(self.right_notebook, padding=6)
        self.right_notebook.add(hist_tab, text="観測履歴（過去比較）")

        hist_top = ttk.Frame(hist_tab)
        hist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hist_top, text="過去の観測を1つ選んで現在地を見るか、2つ選んで比較できます。").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        self.btn_hist_inspect = ttk.Button(
            hist_top, text="選んだ時点の現在地を見る", command=self._on_inspect_selected_history
        )
        self.btn_hist_inspect.pack(side=tk.RIGHT, padx=2)
        self.btn_cmp_pair = ttk.Button(
            hist_top, text="選んだ2時点を比較", command=self._on_compare_selected
        )
        self.btn_cmp_pair.pack(side=tk.RIGHT, padx=2)

        self.obs_tree = ttk.Treeview(
            hist_tab,
            columns=("taken_at", "who", "depth", "note"),
            show="headings",
            selectmode="extended",
        )
        self.obs_tree.heading("taken_at", text="観測日時")
        self.obs_tree.heading("who", text="観測者")
        self.obs_tree.heading("depth", text="深さ")
        self.obs_tree.heading("note", text="メモ")
        self.obs_tree.column("taken_at", width=170, anchor=tk.W)
        self.obs_tree.column("who", width=150, anchor=tk.W)
        self.obs_tree.column("depth", width=80, anchor=tk.CENTER)
        self.obs_tree.column("note", width=250, anchor=tk.W)

        obs_scroll = ttk.Scrollbar(hist_tab, orient=tk.VERTICAL, command=self.obs_tree.yview)
        self.obs_tree.configure(yscrollcommand=obs_scroll.set)
        self.obs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        obs_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # タブ5: 工程管理メモ
        note_tab = ttk.Frame(self.right_notebook, padding=6)
        self.right_notebook.add(note_tab, text="工程管理メモ")

        form = ttk.Frame(note_tab)
        form.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(form, text="カット/ユニット:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form, textvariable=self.unit_var, width=16).grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(form, text="状態:").grid(row=0, column=2, sticky=tk.W, pady=2)
        ttk.Combobox(form, textvariable=self.work_status_var, values=STATUS_PRESETS, width=14).grid(
            row=0, column=3, sticky=tk.W, padx=4
        )
        ttk.Label(form, text="正(採用)パス:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form, textvariable=self.pinned_var, width=40).grid(
            row=1, column=1, columnspan=3, sticky=tk.EW, padx=4
        )
        ttk.Label(form, text="コメント:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(form, textvariable=self.comment_var, width=40).grid(
            row=2, column=1, columnspan=3, sticky=tk.EW, padx=4
        )
        ttk.Button(form, text="工程メモを追記", command=self._on_add_note).grid(
            row=0, column=4, rowspan=3, padx=8, sticky=tk.NS
        )
        form.columnconfigure(3, weight=1)

        self.note_tree = ttk.Treeview(
            note_tab,
            columns=("unit", "status", "pinned", "comment", "author", "created_at"),
            show="headings",
        )
        self.note_tree.heading("unit", text="カット/ユニット")
        self.note_tree.heading("status", text="状態")
        self.note_tree.heading("pinned", text="正(採用)パス")
        self.note_tree.heading("comment", text="コメント")
        self.note_tree.heading("author", text="記入者")
        self.note_tree.heading("created_at", text="更新日時")
        self.note_tree.column("unit", width=90, anchor=tk.W)
        self.note_tree.column("status", width=90, anchor=tk.CENTER)
        self.note_tree.column("pinned", width=150, anchor=tk.W)
        self.note_tree.column("comment", width=180, anchor=tk.W)
        self.note_tree.column("author", width=80, anchor=tk.W)
        self.note_tree.column("created_at", width=130, anchor=tk.W)

        note_scroll = ttk.Scrollbar(note_tab, orient=tk.VERTICAL, command=self.note_tree.yview)
        self.note_tree.configure(yscrollcommand=note_scroll.set)
        self.note_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        note_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 下部ステータスバー
        status_bar = ttk.Frame(self, padding=(10, 4))
        status_bar.pack(fill=tk.X)
        self.progress = ttk.Progressbar(status_bar, mode="determinate", length=180)
        self.progress.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(status_bar, textvariable=self.status_msg_var).pack(side=tk.LEFT, fill=tk.X)

    def _browse_dir(self) -> None:
        chosen = filedialog.askdirectory(title="対象フォルダーを選択")
        if chosen:
            self.dir_var.set(chosen)
            is_cut_self = self._detect_cut_candidates(chosen)
            self.refresh_ledger()
            if is_cut_self or self.subpath_var.get().strip():
                self._on_inspect_live()
            else:
                self.status_msg_var.set("話数フォルダーを検出しました。上の「カット選択」からカットを選んでください。")

    def _detect_cut_candidates(self, target_dir: str) -> bool:
        """
        対象フォルダー直下1階層だけを見て、カット自体か話数フォルダーかを軽量判定する。
        戻り値: True=カットフォルダー自体 / False=話数など親フォルダー
        """
        p = Path(target_dir)
        if not p.exists() or not p.is_dir():
            return True

        slot_names = {s.folder.lower() for s in CutProfile.default().slots if s.folder}
        subdirs: list[str] = []
        looks_like_cut = False

        try:
            with os.scandir(p) as it:
                for entry in it:
                    if entry.is_dir():
                        if entry.name in DEFAULT_EXCLUDE_DIRS:
                            continue
                        if entry.name.lower() in slot_names:
                            looks_like_cut = True
                        subdirs.append(entry.name)
                    elif entry.is_file() and entry.name.lower().endswith((".aep", ".aepx")):
                        looks_like_cut = True
        except OSError:
            return True

        subdirs.sort()
        if looks_like_cut:
            self.subpath_combo["values"] = [""]
            self.subpath_var.set("")
            return True

        # 話数フォルダー等の場合、直下のサブフォルダーをカット候補に並べる（全体走査はさせない）
        self.subpath_combo["values"] = subdirs
        if subdirs:
            self.subpath_var.set(subdirs[0])
        else:
            self.subpath_var.set("")
        return False

    def _browse_ledger(self) -> None:
        chosen = filedialog.askdirectory(title="台帳フォルダーを選択")
        if chosen:
            self.ledger_var.set(chosen)
            self.refresh_ledger()

    def _get_ledger(self) -> Ledger:
        target = self.dir_var.get().strip()
        if not target:
            raise ValueError("対象フォルダーを指定してください。")
        return Ledger(resolve_ledger_dir(target, self.ledger_var.get().strip() or None))

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (
            self.btn_observe,
            self.btn_inspect,
            self.btn_cmp_live,
            self.btn_cmp_pair,
            self.btn_cmp_other,
            self.btn_cmp_pkgs,
            self.btn_hist_inspect,
        ):
            btn.configure(state=state)
        if msg:
            self.status_msg_var.set(msg)

    def _run_async(self, work: Callable[[], object], on_done: Callable[[object], None]) -> None:
        if self._busy:
            return
        self._set_busy(True, "処理中...")

        def _worker() -> None:
            try:
                res = work()
                self.after(0, lambda: self._finish_async(res, on_done))
            except Exception as exc:
                self.after(0, lambda e=exc: self._fail_async(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_async(self, res: object, on_done: Callable[[object], None]) -> None:
        self._set_busy(False)
        self.progress["value"] = 0
        on_done(res)

    def _fail_async(self, exc: Exception) -> None:
        self._set_busy(False, f"エラー: {exc}")
        self.progress["value"] = 0
        messagebox.showerror("エラー", str(exc))

    def refresh_ledger(self) -> None:
        target = self.dir_var.get().strip()
        if not target:
            return
        try:
            ledger = self._get_ledger()
            self._headers = ledger.list_observations()
            latest_notes = ledger.get_latest_status_map()
        except Exception as exc:
            self.status_msg_var.set(f"読込エラー: {exc}")
            return

        for row in self.obs_tree.get_children():
            self.obs_tree.delete(row)
        for h in self._headers:
            self.obs_tree.insert(
                "",
                tk.END,
                iid=h.id,
                values=(h.taken_at[:19].replace("T", " "), f"{h.observer_user}@{h.observer_host}", h.depth, h.note),
            )

        for row in self.note_tree.get_children():
            self.note_tree.delete(row)
        for _, note in sorted(latest_notes.items()):
            self.note_tree.insert(
                "",
                tk.END,
                values=(
                    note.target_unit or "(全体)",
                    note.status,
                    note.pinned_path,
                    note.comment,
                    note.author,
                    note.created_at[:19].replace("T", " "),
                ),
            )

        self.status_msg_var.set(f"観測 {len(self._headers)} 件 / ユニット {len(latest_notes)} 件")

    def _on_observe(self) -> None:
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showwarning("未指定", "対象フォルダーを指定してください。")
            return
        depth = self.depth_var.get()
        note = self.note_var.get().strip()
        subpath = self.subpath_var.get().strip()

        def _work() -> tuple[str, int, int]:
            ledger = self._get_ledger()
            prev = ledger.get_latest_observation()

            def _prog(done: int, total: int) -> None:
                pct = (done / total * 100) if total > 0 else 100
                self.after(0, lambda p=pct, d=done, t=total: self._update_progress(p, f"走査中: {d}/{t}"))

            obs = observe_directory(
                target,
                subpath=subpath,
                depth=depth,
                note=note,
                previous=prev,
                progress_cb=_prog,
            )
            ledger.save_observation(obs)
            reused = sum(1 for e in obs.entries if e.hash_reused)
            return obs.header.id, len(obs.entries), reused

        def _done(res: object) -> None:
            obs_id, total, reused = res  # type: ignore[misc]
            self.note_var.set("")
            self.refresh_ledger()
            self.status_msg_var.set(f"履歴に記録しました: {obs_id} ({total}件 / 指紋再利用 {reused}件)")

        self._run_async(_work, _done)

    def _update_progress(self, pct: float, msg: str) -> None:
        self.progress["value"] = pct
        self.status_msg_var.set(msg)

    def _on_inspect_live(self) -> None:
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showwarning("未指定", "対象フォルダーを指定してください。")
            return
        self._inspect_with_obs_id(None)

    def _on_inspect_selected_history(self) -> None:
        selected = list(self.obs_tree.selection())
        if len(selected) != 1:
            messagebox.showinfo("選択", "現在地を見たい観測を1つ選択してください。")
            return
        self._inspect_with_obs_id(selected[0])

    def _inspect_with_obs_id(self, obs_id: str | None) -> None:
        target = self.dir_var.get().strip()
        depth = self.depth_var.get()
        subpath = self.subpath_var.get().strip()

        def _work() -> tuple[Observation, CutOverviewReport, InventoryReport]:
            ledger_dir = resolve_ledger_dir(target, self.ledger_var.get().strip() or None)
            ledger = Ledger(ledger_dir)
            if obs_id is not None:
                obs = ledger.load_observation(obs_id)
            else:
                def _prog(done: int, total: int) -> None:
                    pct = (done / total * 100) if total > 0 else 100
                    self.after(0, lambda p=pct, d=done, t=total: self._update_progress(p, f"走査中: {d}/{t}"))

                obs = observe_directory(
                    target,
                    subpath=subpath,
                    depth=depth,
                    previous=ledger.get_latest_observation(),
                    progress_cb=_prog,
                    trigger="inspect",
                )
            profile = load_profile(target, ledger_dir)
            slot_rep = build_slot_overview(obs, profile, subpath=subpath)
            inv_rep = build_inventory(obs, subpath=subpath)
            if subpath:
                slot_rep.label = f"{obs.header.root_label}/{subpath}"
                inv_rep.label = f"{obs.header.root_label}/{subpath}"
            return obs, slot_rep, inv_rep

        self._run_async(_work, lambda res: self._show_inspect_reports(res))  # type: ignore[arg-type]

    def _show_inspect_reports(self, reports: tuple[Observation, CutOverviewReport, InventoryReport]) -> None:
        obs, slot_rep, inv_rep = reports
        self._current_obs = obs
        self.cut_map.render(slot_rep)
        self._show_slot_overview(slot_rep)
        self._show_inventory_report(inv_rep)
        self.right_notebook.select(0)
        self.status_msg_var.set("現在のカット構成を表示しました。")

    def _focus_slot_in_tree(self, slot_name: str) -> None:
        iid = self._slot_node_iids.get(slot_name)
        if not iid:
            return
        self.right_notebook.select(0)
        self.slot_tree.item(iid, open=True)
        self.slot_tree.selection_set(iid)
        self.slot_tree.focus(iid)
        self.slot_tree.see(iid)

    def _toggle_tree(self, tree: ttk.Treeview, expand: bool) -> None:
        def _walk(parent: str) -> None:
            for child in tree.get_children(parent):
                if tree.get_children(child):
                    tree.item(child, open=expand)
                    _walk(child)

        _walk("")

    def _show_slot_overview(self, report: CutOverviewReport) -> None:
        for row in self.slot_tree.get_children():
            self.slot_tree.delete(row)
        self._slot_node_iids.clear()
        self._pkg_rel_paths.clear()
        self._pkg_hashes.clear()
        self._slot_item_paths.clear()

        state_labels = {"ok": "1件", "multiple": "⚠ 複数", "empty": "- 空"}
        ok_cnt = sum(1 for s in report.slots if s.state == "ok")
        mult_cnt = sum(1 for s in report.slots if s.state == "multiple")

        for slot in report.slots:
            total_sz = sum(p.total_size for p in slot.active_packages)
            summary_text = f"通常 {len(slot.active_packages)}件"
            if slot.archived_packages:
                summary_text += f" / (old) {len(slot.archived_packages)}件"

            slot_iid = self.slot_tree.insert(
                "",
                tk.END,
                text=f"📂 {slot.slot_label} ({slot.folder})",
                values=(
                    state_labels.get(slot.state, slot.state),
                    summary_text,
                    _format_size(total_sz) if total_sz else "-",
                    "",
                ),
                open=(slot.state != "empty"),
                tags=(slot.state,),
            )
            self._slot_node_iids[slot.slot_name] = slot_iid
            self._slot_item_paths[slot_iid] = ("" if slot.folder == "(ルート)" else slot.folder, False)

            for pkg in slot.active_packages:
                self._insert_slot_package(slot_iid, pkg, archived=False)

            if slot.archived_packages:
                old_sz = sum(p.total_size for p in slot.archived_packages)
                old_iid = self.slot_tree.insert(
                    slot_iid,
                    tk.END,
                    text="📁 (old) 退避",
                    values=("(old)", f"{len(slot.archived_packages)}件", _format_size(old_sz), ""),
                    open=False,
                    tags=("old",),
                )
                for pkg in slot.archived_packages:
                    self._insert_slot_package(old_iid, pkg, archived=True)

        if report.unclassified_paths:
            self.slot_tree.insert(
                "",
                tk.END,
                text="📁 プロファイル外のファイル",
                values=("対象外", f"{len(report.unclassified_paths)}件", "-", ""),
                open=False,
                tags=("old",),
            )

        self.slot_summary_var.set(
            f"{report.label} | 1件揃い: {ok_cnt} / 複数混在: {mult_cnt} / 全{len(report.slots)}スロット"
        )

    def _insert_slot_package(self, parent_iid: str, pkg: SlotPackage, *, archived: bool) -> None:
        icon = "📦" if pkg.is_folder else "📄"
        detail = f"{pkg.file_count}ファイル (連番{pkg.seq_count})" if pkg.is_folder else "単一ファイル"
        note_parts: list[str] = []
        if pkg.package_hash:
            note_parts.append(f"ID:{pkg.package_hash[:8]}")
        if pkg.duplicate_of:
            note_parts.append(f"同一塊: {', '.join(pkg.duplicate_of)}")
        dup_note = " | ".join(note_parts)
        tags: tuple[str, ...] = ("dup",) if pkg.duplicate_of else (("old",) if archived else ())

        pkg_iid = self.slot_tree.insert(
            parent_iid,
            tk.END,
            text=f"{icon} {pkg.name}",
            values=("(old)" if archived else "通常", detail, _format_size(pkg.total_size), dup_note),
            open=False,
            tags=tags,
        )
        self._slot_item_paths[pkg_iid] = (pkg.rel_path, False)
        if pkg.package_hash:
            self._pkg_hashes[pkg_iid] = pkg.package_hash
        if not pkg.is_folder:
            return

        self._pkg_rel_paths[pkg_iid] = pkg.rel_path

        # 塊内部のサブフォルダーを階層ツリーとして組み立てる
        prefix = pkg.rel_path + "/"
        inner_items: list[tuple[str, InventoryItem]] = []
        dir_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"seq": 0, "single": 0, "size": 0})

        for item in sorted(pkg.items, key=lambda it: it.path):
            rel = item.path[len(prefix):] if item.path.startswith(prefix) else item.path
            inner_items.append((rel, item))
            parts = rel.split("/")
            for depth in range(1, len(parts)):
                sub_dir = "/".join(parts[:depth])
                if item.is_sequence:
                    dir_stats[sub_dir]["seq"] += 1
                else:
                    dir_stats[sub_dir]["single"] += 1
                dir_stats[sub_dir]["size"] += item.total_size

        sub_nodes: dict[str, str] = {}

        def _ensure_sub_folder(sub_path: str) -> str:
            if not sub_path:
                return pkg_iid
            if sub_path in sub_nodes:
                return sub_nodes[sub_path]
            if "/" in sub_path:
                p_dir, name = sub_path.rsplit("/", 1)
                p_iid = _ensure_sub_folder(p_dir)
            else:
                p_iid = pkg_iid
                name = sub_path

            st = dir_stats[sub_path]
            parts_str: list[str] = []
            if st["seq"]:
                parts_str.append(f"連番 {st['seq']}本")
            if st["single"]:
                parts_str.append(f"単一 {st['single']}件")
            dir_tags: tuple[str, ...] = ("old",) if (archived or "(old)" in sub_path.lower()) else ()
            iid = self.slot_tree.insert(
                p_iid,
                tk.END,
                text=f"📁 {name}",
                values=("フォルダー", " / ".join(parts_str), _format_size(st["size"]), ""),
                open=False,
                tags=dir_tags,
            )
            self._slot_item_paths[iid] = (f"{pkg.rel_path}/{sub_path}", False)
            sub_nodes[sub_path] = iid
            return iid

        for rel, item in inner_items:
            if "/" in rel:
                sub_dir, leaf_name = rel.rsplit("/", 1)
                target_parent = _ensure_sub_folder(sub_dir)
            else:
                target_parent = pkg_iid
                leaf_name = rel

            leaf_icon = "🎞" if item.is_sequence else "📄"
            leaf_iid = self.slot_tree.insert(
                target_parent,
                tk.END,
                text=f"{leaf_icon} {leaf_name}",
                values=(item.kind, item.detail, _format_size(item.total_size), ""),
                tags=tags,
            )
            self._slot_item_paths[leaf_iid] = (item.path, item.is_sequence)

    def _resolve_full_path(self, rel_path: str, is_sequence: bool) -> Path:
        base = Path(self.dir_var.get().strip())
        sub = self.subpath_var.get().strip().strip("/")
        if sub:
            base = base / sub
        full = (base / rel_path) if rel_path else base
        return full.parent if is_sequence else full

    def _open_tree_iid(
        self,
        tree: ttk.Treeview,
        path_map: dict[str, tuple[str, bool]],
        iid: str,
        *,
        open_parent_dir: bool = False,
    ) -> None:
        info = path_map.get(iid)
        if info is None:
            return
        rel_path, is_seq = info
        try:
            target = self._resolve_full_path(rel_path, is_seq)
            if open_parent_dir and not is_seq and target.is_file():
                target = target.parent
            _open_with_default_app(target)
            self.status_msg_var.set(f"開きました: {target}")
        except Exception as exc:
            messagebox.showerror("開けません", str(exc))

    def _open_selected_tree_item(
        self, tree: ttk.Treeview, path_map: dict[str, tuple[str, bool]]
    ) -> None:
        selected = tree.selection()
        if not selected:
            messagebox.showinfo("未選択", "開きたいファイルまたはフォルダーを選択してください。")
            return
        self._open_tree_iid(tree, path_map, selected[0])

    def _on_tree_double_click(
        self, event: tk.Event, tree: ttk.Treeview, path_map: dict[str, tuple[str, bool]]
    ) -> None:
        iid = tree.identify_row(event.y)
        if not iid or tree.get_children(iid):
            # 子を持つフォルダー行は標準の展開/折りたたみに任せる
            return
        self._open_tree_iid(tree, path_map, iid)

    def _on_tree_right_click(
        self, event: tk.Event, tree: ttk.Treeview, path_map: dict[str, tuple[str, bool]]
    ) -> None:
        iid = tree.identify_row(event.y)
        if not iid or iid not in path_map:
            return
        tree.selection_set(iid)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="関連付けアプリで開く",
            command=lambda: self._open_tree_iid(tree, path_map, iid, open_parent_dir=False),
        )
        menu.add_command(
            label="親フォルダーを開く",
            command=lambda: self._open_tree_iid(tree, path_map, iid, open_parent_dir=True),
        )
        if tree is self.slot_tree and iid in self._pkg_hashes:
            pkg_hash = self._pkg_hashes[iid]
            menu.add_separator()
            menu.add_command(
                label=f"塊ハッシュをコピー ({pkg_hash[:8]}...)",
                command=lambda h=pkg_hash: self._copy_hash_to_clipboard(h),
            )
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_hash_to_clipboard(self, pkg_hash: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(pkg_hash)
        self.status_msg_var.set(f"塊ハッシュをコピーしました: {pkg_hash}")

    def _on_compare_selected_packages(self) -> None:
        if self._current_obs is None:
            messagebox.showinfo("案内", "先に「現在地を見る」を実行してください。")
            return
        selected = [iid for iid in self.slot_tree.selection() if iid in self._pkg_rel_paths]
        if len(selected) != 2:
            messagebox.showinfo(
                "塊を2つ選択",
                "比較したいフォルダーの塊（📦）を Ctrl+クリックで2つ選択してください。\n"
                "（例: 現在の CELL フォルダーと (old) 内の旧フォルダー）",
            )
            return

        sub_prefix = self.subpath_var.get().strip().strip("/")
        p1 = self._pkg_rel_paths[selected[0]]
        p2 = self._pkg_rel_paths[selected[1]]
        left_sub = f"{sub_prefix}/{p1}" if sub_prefix else p1
        right_sub = f"{sub_prefix}/{p2}" if sub_prefix else p2

        obs = self._current_obs
        res = compare_observations(obs, obs, left_subpath=left_sub, right_subpath=right_sub)
        res.left_label = left_sub
        res.right_label = right_sub
        self._show_compare_result(res)
        self.right_notebook.select(2)

    def _show_inventory_report(self, report: InventoryReport) -> None:
        for row in self.inv_tree.get_children():
            self.inv_tree.delete(row)
        self._inv_item_paths.clear()

        dir_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"seq": 0, "single": 0, "size": 0, "dup": 0}
        )
        for item in report.items:
            parts = item.path.split("/")
            for depth in range(1, len(parts)):
                folder_key = "/".join(parts[:depth])
                if item.is_sequence:
                    dir_stats[folder_key]["seq"] += 1
                else:
                    dir_stats[folder_key]["single"] += 1
                dir_stats[folder_key]["size"] += item.total_size
                if item.duplicate_paths:
                    dir_stats[folder_key]["dup"] += 1

        folder_nodes: dict[str, str] = {}

        def _ensure_folder(folder_path: str) -> str:
            if not folder_path:
                return ""
            if folder_path in folder_nodes:
                return folder_nodes[folder_path]
            if "/" in folder_path:
                parent_path, name = folder_path.rsplit("/", 1)
                parent_iid = _ensure_folder(parent_path)
            else:
                parent_iid = ""
                name = folder_path

            st = dir_stats[folder_path]
            summary_parts: list[str] = []
            if st["seq"]:
                summary_parts.append(f"連番 {st['seq']}本")
            if st["single"]:
                summary_parts.append(f"単一 {st['single']}件")
            dup_text = f"重複 {st['dup']}件" if st["dup"] else ""
            is_top = "/" not in folder_path
            tags: tuple[str, ...] = ("old",) if "(old)" in folder_path.lower() else ("folder",)
            iid = self.inv_tree.insert(
                parent_iid,
                tk.END,
                text=f"📁 {name}",
                values=("フォルダー", " / ".join(summary_parts), _format_size(st["size"]), dup_text),
                open=is_top,
                tags=tags,
            )
            self._inv_item_paths[iid] = (folder_path, False)
            folder_nodes[folder_path] = iid
            return iid

        for item in sorted(report.items, key=lambda it: it.path):
            if "/" in item.path:
                folder_path, leaf_name = item.path.rsplit("/", 1)
                parent_iid = _ensure_folder(folder_path)
            else:
                parent_iid = ""
                leaf_name = item.path

            display_name = f"🎞 {leaf_name}" if item.is_sequence else f"📄 {leaf_name}"
            dup_label = f"重複: {', '.join(item.duplicate_paths)}" if item.duplicate_paths else ""
            tags_list: list[str] = []
            if item.duplicate_paths:
                tags_list.append("dup")
            elif item.kind.startswith("(old)"):
                tags_list.append("old")

            leaf_iid = self.inv_tree.insert(
                parent_iid,
                tk.END,
                text=display_name,
                values=(item.kind, item.detail, _format_size(item.total_size), dup_label),
                tags=tuple(tags_list),
            )
            self._inv_item_paths[leaf_iid] = (item.path, item.is_sequence)

        counts_str = ", ".join(f"{k}: {v}" for k, v in sorted(report.by_kind_counts.items()))
        dup_str = (
            f" | 単一重複 {len(report.duplicate_groups)}組"
            if report.duplicate_groups
            else " | 単一重複なし"
        )
        self.inv_summary_var.set(f"{report.label} ({report.total_files}件)  [{counts_str}{dup_str}]")

    def _on_compare_live(self) -> None:
        target = self.dir_var.get().strip()
        if not target:
            return
        depth = self.depth_var.get()
        subpath = self.subpath_var.get().strip()

        def _work() -> CompareResult:
            ledger = self._get_ledger()
            left = ledger.get_latest_observation()
            if left is None:
                raise FileNotFoundError("観測履歴がまだありません。先に「いまの状態を履歴に記録」を実行してください。")
            right = observe_directory(
                target, subpath=subpath, depth=depth, previous=left, trigger="compare_live"
            )
            return compare_observations(left, right, left_subpath=subpath, right_subpath=subpath)

        self._run_async(_work, lambda res: self._show_compare_and_switch(res))  # type: ignore[arg-type]

    def _on_compare_selected(self) -> None:
        selected = list(self.obs_tree.selection())
        if len(selected) != 2:
            messagebox.showinfo("選択", "比較したい観測を2つ選択してください（Ctrl+クリック）。")
            return

        idx_map = {h.id: i for i, h in enumerate(self._headers)}
        selected.sort(key=lambda oid: idx_map.get(oid, 0), reverse=True)
        left_id, right_id = selected[0], selected[1]

        def _work() -> CompareResult:
            ledger = self._get_ledger()
            return compare_observations(
                ledger.load_observation(left_id),
                ledger.load_observation(right_id),
            )

        self._run_async(_work, lambda res: self._show_compare_and_switch(res))  # type: ignore[arg-type]

    def _on_compare_other_dir(self) -> None:
        other = filedialog.askdirectory(title="比較する別フォルダー（届いた素材など）を選択")
        if not other:
            return
        depth = self.depth_var.get()

        def _work() -> CompareResult:
            ledger = self._get_ledger()
            left = ledger.get_latest_observation()
            if left is None:
                left = observe_directory(self.dir_var.get().strip(), depth=depth)
            right = observe_directory(other, depth=depth, previous=left, trigger="compare_other")
            return compare_observations(left, right)

        self._run_async(_work, lambda res: self._show_compare_and_switch(res))  # type: ignore[arg-type]

    def _show_compare_and_switch(self, res: CompareResult) -> None:
        self._show_compare_result(res)
        self.right_notebook.select(2)

    def _show_compare_result(self, res: CompareResult) -> None:
        for row in self.diff_tree.get_children():
            self.diff_tree.delete(row)

        rel_labels = {
            "added": "+ 増えた",
            "removed": "- 消えた",
            "updated": "* 変わった",
            "moved": "> 移った",
            "archived": "@ (old)へ",
            "same": "= 同じ",
        }
        conf_labels = {
            "verified": "中身確認",
            "stat_only": "サイズ日時のみ",
            "n/a": "-",
        }

        for item in res.items:
            detail = f"元: {item.old_path}" if item.old_path else item.detail
            path_label = f"{item.path} (連番)" if item.is_sequence else item.path
            self.diff_tree.insert(
                "",
                tk.END,
                values=(
                    rel_labels.get(item.relation, item.relation),
                    conf_labels.get(item.confidence, item.confidence),
                    path_label,
                    detail,
                ),
                tags=(item.relation,),
            )

        summary_str = ", ".join(f"{rel_labels.get(k, k)}: {v}" for k, v in sorted(res.summary.items()))
        dup_str = f" | 重複: {len(res.duplicates)}組" if res.duplicates else ""
        self.diff_summary_var.set(f"{res.left_label} ⇔ {res.right_label}  [{summary_str or '変更なし'}{dup_str}]")
        self.status_msg_var.set("比較が完了しました。")

    def _on_add_note(self) -> None:
        try:
            ledger = self._get_ledger()
            ledger.add_note(
                target_unit=self.unit_var.get().strip(),
                status=self.work_status_var.get().strip() or "作業中",
                pinned_path=self.pinned_var.get().strip(),
                comment=self.comment_var.get().strip(),
            )
            self.comment_var.set("")
            self.refresh_ledger()
            self.status_msg_var.set("工程メモを追記しました。")
        except Exception as exc:
            messagebox.showerror("エラー", str(exc))


def launch_gui(initial_dir: str = "", initial_ledger: str | None = None) -> None:
    """GUI アプリケーションを起動する。"""
    app = ACFVSApp(initial_dir=initial_dir, initial_ledger=initial_ledger)
    app.mainloop()
