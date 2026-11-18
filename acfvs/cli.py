"""
ACF-VS コマンドラインインターフェース（CLI）。

人向けの整形出力と、他アプリ・スクリプト向けの JSON 出力（--json）の両方を提供する。
終了コードは 0=正常、1=エラー。

バージョン: 0.4.8
更新日時: Wed Nov 18 20:52:58 JST 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .comparer import compare_observations
from .interpreter import CutOverviewReport, InventoryReport, build_inventory, build_slot_overview
from .ledger import Ledger, resolve_ledger_dir
from .models import CompareResult
from .observer import observe_directory
from .profile import load_profile

RELATION_LABELS = {
    "added": "[+増えた]",
    "removed": "[-消えた]",
    "updated": "[*変わった]",
    "moved": "[>移った]",
    "archived": "[@(old)へ]",
    "same": "[=同じ]",
}

CONFIDENCE_LABELS = {
    "verified": "中身確認",
    "stat_only": "サイズ・日時のみ",
    "n/a": "-",
}


def _configure_stdio() -> None:
    """Windows 環境での日本語出力文字化けを防ぐ。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_compare_human(res: CompareResult) -> None:
    print(f"比較元 (Left) : {res.left_label}")
    print(f"比較先 (Right): {res.right_label}")
    print("-" * 60)

    if not res.items and not res.duplicates:
        print("差分はありません。")
        return

    for item in res.items:
        rel_tag = RELATION_LABELS.get(item.relation, f"[{item.relation}]")
        conf_tag = CONFIDENCE_LABELS.get(item.confidence, item.confidence)
        seq_mark = " (連番)" if item.is_sequence else ""

        if item.old_path:
            print(f"{rel_tag} {item.old_path} -> {item.path}  ({conf_tag})")
        else:
            detail_part = f" | {item.detail}" if item.detail else ""
            print(f"{rel_tag}{seq_mark} {item.path}{detail_part}  ({conf_tag})")

    if res.duplicates:
        print("\n[重複（同じ中身の写し）]")
        for dup in res.duplicates:
            print(f"  sha256={dup['sha256'][:12]}... : {', '.join(dup['paths'])}")

    print("-" * 60)
    summary_str = ", ".join(f"{k}={v}" for k, v in sorted(res.summary.items()))
    print(f"集計: {summary_str or '変更なし'}")


def _cmd_observe(args: argparse.Namespace) -> int:
    ledger = Ledger(resolve_ledger_dir(args.dir, args.ledger))
    previous = ledger.get_latest_observation()

    def _progress(done: int, total: int) -> None:
        if not args.json:
            print(f"\r走査中: {done}/{total}", end="", flush=True)

    obs = observe_directory(
        args.dir,
        subpath=args.subpath,
        label=args.label,
        depth=args.depth,
        note=args.note,
        trigger=args.trigger,
        previous=previous,
        progress_cb=_progress if not args.json else None,
    )
    if not args.json:
        print()

    saved_path = ledger.save_observation(obs)
    reused_count = sum(1 for e in obs.entries if e.hash_reused)
    err_count = sum(1 for e in obs.entries if e.error)

    if args.json:
        _print_json({
            "ok": True,
            "observation_id": obs.header.id,
            "saved_path": str(saved_path),
            "file_count": len(obs.entries),
            "hash_reused_count": reused_count,
            "error_count": err_count,
            "header": obs.header.to_dict(),
        })
    else:
        print(f"観測を記録しました: {obs.header.id}")
        print(f"  保存先  : {saved_path}")
        print(f"  ファイル: {len(obs.entries)} 件 (指紋再利用: {reused_count} 件, エラー: {err_count} 件)")
        print(f"  観測者  : {obs.header.observer_user}@{obs.header.observer_host} ({obs.header.depth})")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    ledger = Ledger(resolve_ledger_dir(args.dir, args.ledger))

    # Left の解決
    if args.left:
        left_obs = ledger.load_observation(args.left)
    else:
        left_obs = ledger.get_latest_observation()
        if left_obs is None:
            raise FileNotFoundError("基準となる観測がまだありません。先に observe を実行してください。")

    # Right の解決
    if args.right_dir:
        right_obs = observe_directory(
            args.right_dir,
            depth=args.depth,
            previous=left_obs,
            trigger="compare_live",
        )
    elif args.right:
        right_obs = ledger.load_observation(args.right)
    else:
        right_obs = observe_directory(
            args.dir,
            depth=args.depth,
            previous=left_obs,
            trigger="compare_live",
        )

    res = compare_observations(
        left_obs,
        right_obs,
        left_subpath=args.left_subpath,
        right_subpath=args.right_subpath,
        include_same=args.include_same,
    )

    if args.json:
        _print_json({"ok": True, **res.to_dict()})
    else:
        _print_compare_human(res)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    ledger = Ledger(resolve_ledger_dir(args.dir, args.ledger))
    headers = ledger.list_observations()
    notes = ledger.get_latest_status_map()

    if args.json:
        _print_json({
            "ok": True,
            "ledger_dir": str(ledger.base_dir),
            "observations": [h.to_dict() for h in headers],
            "unit_statuses": {k: v.to_dict() for k, v in notes.items()},
        })
        return 0

    print(f"台帳: {ledger.base_dir}")
    print("\n[観測一覧]")
    if not headers:
        print("  (観測はまだありません)")
    else:
        for h in headers:
            note_part = f" | {h.note}" if h.note else ""
            print(f"  {h.id}  {h.taken_at}  {h.observer_user}@{h.observer_host}  [{h.depth}]{note_part}")

    print("\n[ユニット工程ステータス（最新）]")
    if not notes:
        print("  (工程メモはまだありません)")
    else:
        for unit, n in sorted(notes.items()):
            pin_part = f"  正={n.pinned_path}" if n.pinned_path else ""
            cmt_part = f"  ({n.comment})" if n.comment else ""
            print(f"  {unit or '(全体)'}: [{n.status}]{pin_part}{cmt_part}  <{n.author} {n.created_at}>")
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    ledger = Ledger(resolve_ledger_dir(args.dir, args.ledger))
    note = ledger.add_note(
        target_unit=args.unit,
        status=args.status,
        pinned_path=args.pin,
        comment=args.comment,
    )
    if args.json:
        _print_json({"ok": True, "note": note.to_dict()})
    else:
        print(f"工程メモを追記しました: {note.target_unit or '(全体)'} -> [{note.status}]")
    return 0


def _print_inventory_human(report: InventoryReport) -> None:
    print(f"現在地: {report.label} ({report.taken_at}) | 総ファイル数: {report.total_files}")
    print("-" * 60)
    if not report.items:
        print("ファイルはありません。")
        return

    current_kind = None
    for item in report.items:
        if item.kind != current_kind:
            current_kind = item.kind
            cnt = report.by_kind_counts.get(current_kind, 0)
            print(f"\n[{current_kind}] ({cnt}件)")
        seq_mark = " (連番)" if item.is_sequence else ""
        dup_mark = f"  [重複あり: {', '.join(item.duplicate_paths)}]" if item.duplicate_paths else ""
        print(f"  - {item.path}{seq_mark}  ({item.detail}){dup_mark}")

    if report.duplicate_groups:
        print(f"\n[重複サマリ] 同じ中身のファイルが {len(report.duplicate_groups)} 組あります。")


def _print_slot_overview_human(report: CutOverviewReport) -> None:
    state_labels = {"ok": "[✓ 1件]", "multiple": "[! 複数]", "empty": "[  空 ]"}
    print(f"カット俯瞰: {report.label} ({report.taken_at}) | プロファイル: {report.profile_name}")
    print("-" * 60)
    for slot in report.slots:
        st = state_labels.get(slot.state, slot.state)
        print(f"{st} {slot.slot_label} ({slot.folder})")
        for pkg in slot.active_packages:
            id_part = f" [ID:{pkg.package_hash[:8]}]" if pkg.package_hash else ""
            dup = f"  [同一塊あり: {', '.join(pkg.duplicate_of)}]" if pkg.duplicate_of else ""
            kind_str = f"塊/{pkg.file_count}ファイル" if pkg.is_folder else "単一"
            print(f"    -> {pkg.name}{id_part} ({kind_str}, 連番{pkg.seq_count}){dup}")
        if slot.archived_packages:
            names = ", ".join(p.name for p in slot.archived_packages[:5])
            more = "..." if len(slot.archived_packages) > 5 else ""
            print(f"    (old): {len(slot.archived_packages)}件 [{names}{more}]")
    if report.unclassified_paths:
        print(f"\n[プロファイル外のファイル] {len(report.unclassified_paths)}件")


def _cmd_inspect(args: argparse.Namespace) -> int:
    ledger_dir = resolve_ledger_dir(args.dir, args.ledger)
    ledger = Ledger(ledger_dir)
    if args.obs:
        obs = ledger.load_observation(args.obs)
    else:
        obs = observe_directory(
            args.dir,
            depth=args.depth,
            previous=ledger.get_latest_observation(),
            trigger="inspect",
        )

    if args.slots:
        profile = load_profile(args.dir, ledger_dir)
        slot_rep = build_slot_overview(obs, profile, subpath=args.subpath)
        if args.json:
            _print_json({"ok": True, **slot_rep.to_dict()})
        else:
            _print_slot_overview_human(slot_rep)
        return 0

    report = build_inventory(obs, subpath=args.subpath)
    if args.json:
        _print_json({"ok": True, **report.to_dict()})
    else:
        _print_inventory_human(report)
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui import launch_gui

    launch_gui(initial_dir=args.dir, initial_ledger=args.ledger)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acfvs",
        description="ACF-VS: アニメ撮影・フォルダー観測＆工程管理ツール (v0.4.0)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # observe
    p_obs = sub.add_parser("observe", help="フォルダーの現在の状態を観測して記録する")
    p_obs.add_argument("--dir", required=True, help="対象フォルダー")
    p_obs.add_argument("--ledger", default=None, help="台帳フォルダー（未指定時は対象内の .acfvs）")
    p_obs.add_argument("--subpath", default="", help="一部だけ観測する場合のサブパス")
    p_obs.add_argument("--label", default="", help="場所の表示名")
    p_obs.add_argument("--depth", choices=("content", "stat"), default="content", help="確認の深さ")
    p_obs.add_argument("--note", default="", help="ひとことメモ")
    p_obs.add_argument("--trigger", default="manual", help="きっかけ（manual/received/submitted 等）")
    p_obs.add_argument("--json", action="store_true", help="JSON形式で出力")

    # compare
    p_cmp = sub.add_parser("compare", help="2つの状態（観測同士・観測といま・別フォルダー）を比べる")
    p_cmp.add_argument("--dir", required=True, help="対象フォルダー")
    p_cmp.add_argument("--ledger", default=None, help="台帳フォルダー")
    p_cmp.add_argument("--left", default=None, help="比較元の観測ID（未指定時は最新観測）")
    p_cmp.add_argument("--right", default=None, help="比較先の観測ID（未指定時は現在のフォルダー）")
    p_cmp.add_argument("--right-dir", default=None, help="比較先の別フォルダー（届いたデータ等）")
    p_cmp.add_argument("--left-subpath", default="", help="比較元で切り出すサブパス")
    p_cmp.add_argument("--right-subpath", default="", help="比較先で切り出すサブパス")
    p_cmp.add_argument("--depth", choices=("content", "stat"), default="content", help="ライブ走査時の確認の深さ")
    p_cmp.add_argument("--include-same", action="store_true", help="変更がない項目も表示する")
    p_cmp.add_argument("--json", action="store_true", help="JSON形式で出力")

    # list
    p_lst = sub.add_parser("list", help="観測履歴と工程ステータスの一覧を表示する")
    p_lst.add_argument("--dir", required=True, help="対象フォルダー")
    p_lst.add_argument("--ledger", default=None, help="台帳フォルダー")
    p_lst.add_argument("--json", action="store_true", help="JSON形式で出力")

    # note
    p_note = sub.add_parser("note", help="カットやユニットの工程ステータス・正ファイルを記録する")
    p_note.add_argument("--dir", required=True, help="対象フォルダー")
    p_note.add_argument("--ledger", default=None, help="台帳フォルダー")
    p_note.add_argument("--unit", default="", help="カット番号やサブフォルダー名（例: c001）")
    p_note.add_argument("--status", required=True, help="工程ステータス（例: 撮影中, 素材待ち, チェック待ち, 完了）")
    p_note.add_argument("--pin", default="", help="正（採用）として指し示すファイル・フォルダーのパス")
    p_note.add_argument("--comment", default="", help="ひとことメモ")
    p_note.add_argument("--json", action="store_true", help="JSON形式で出力")

    # inspect
    p_ins = sub.add_parser("inspect", help="素材種別ごとの現在地と重複・整理状況を表示する")
    p_ins.add_argument("--dir", required=True, help="対象フォルダー")
    p_ins.add_argument("--ledger", default=None, help="台帳フォルダー")
    p_ins.add_argument("--obs", default=None, help="過去のある時点の観測ID（未指定時は現在のフォルダー）")
    p_ins.add_argument("--subpath", default="", help="切り出すサブパス")
    p_ins.add_argument("--slots", action="store_true", help="カットのスロット×塊単位で俯瞰表示する")
    p_ins.add_argument("--depth", choices=("content", "stat"), default="content", help="確認の深さ")
    p_ins.add_argument("--json", action="store_true", help="JSON形式で出力")

    # gui
    p_gui = sub.add_parser("gui", help="簡易デスクトップGUIを起動する")
    p_gui.add_argument("--dir", default="", help="初期フォルダー")
    p_gui.add_argument("--ledger", default=None, help="初期台帳フォルダー")

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    use_json = getattr(args, "json", False)

    try:
        if args.command == "observe":
            return _cmd_observe(args)
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "note":
            return _cmd_note(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "gui":
            return _cmd_gui(args)
    except Exception as exc:
        if use_json:
            _print_json({"ok": False, "error": str(exc)})
        else:
            print(f"エラー: {exc}", file=sys.stderr)
        return 1

    return 0
