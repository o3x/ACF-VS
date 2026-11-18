"""
ACF-VS v0.4.0 再設計プロトタイプの自動テスト。

バージョン: 0.4.0
更新日時: Wed Nov 18 11:28:37 JST 2026
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from acfvs.comparer import compare_observations
from acfvs.ledger import Ledger
from acfvs.observer import load_observation, observe_directory, save_observation

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_SCRIPT = REPO_ROOT / "acfvs_cli.py"


class TestACFVSV2(unittest.TestCase):
    """再設計プロトタイプ（acfvs パッケージ）の単体・結合テスト。"""

    def test_observe_reuse_hash_and_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "work"
            (root / "BG").mkdir(parents=True)
            (root / "BG" / "背景_01.psd").write_bytes(b"bg-data-v1")

            obs1 = observe_directory(root, depth="content", note="初回")
            self.assertEqual(len(obs1.entries), 1)
            self.assertIsNotNone(obs1.entries[0].sha256)
            self.assertFalse(obs1.entries[0].hash_reused)

            saved = save_observation(obs1, Path(tmp) / "ledger" / "observations")
            loaded = load_observation(saved)
            self.assertEqual(loaded.header.id, obs1.header.id)
            self.assertEqual(loaded.entries[0].path, "BG/背景_01.psd")

            # 2回目: 変更がなければ sha256 が再利用される
            obs2 = observe_directory(root, depth="content", previous=loaded)
            self.assertTrue(obs2.entries[0].hash_reused)
            self.assertEqual(obs2.entries[0].sha256, obs1.entries[0].sha256)

    def test_sequence_add_frame_is_updated_not_deleted_and_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "c001"
            cell = root / "CELL" / "A"
            cell.mkdir(parents=True)
            for i in range(1, 4):
                (cell / f"A_{i:04d}.tga").write_bytes(f"frame-{i}".encode("utf-8"))
            # テイク番号（2桁）は連番にしない
            (root / "cut_t01.aep").write_bytes(b"aep1")
            (root / "cut_t02.aep").write_bytes(b"aep2")

            obs1 = observe_directory(root, depth="content")

            # 4枚目を1枚だけ追加
            (cell / "A_0004.tga").write_bytes(b"frame-4")
            obs2 = observe_directory(root, depth="content", previous=obs1)

            res = compare_observations(obs1, obs2)
            self.assertEqual(len(res.items), 1)
            item = res.items[0]
            self.assertEqual(item.relation, "updated")
            self.assertTrue(item.is_sequence)
            self.assertEqual(item.path, "CELL/A/A_####.tga")
            self.assertIn("3枚 → 4枚", item.detail)
            self.assertIn("+1枚(0004)", item.detail)

    def test_archived_and_stat_mode_no_false_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "c002"
            root.mkdir()
            (root / "comp.aep").write_bytes(b"project-v1")
            (root / "other.txt").write_bytes(b"hello")

            obs1 = observe_directory(root, depth="content")

            old_dir = root / "(old)"
            old_dir.mkdir()
            (root / "comp.aep").rename(old_dir / "comp.aep")
            (root / "comp.aep").write_bytes(b"project-v2")

            obs2 = observe_directory(root, depth="content", previous=obs1)
            res = compare_observations(obs1, obs2)

            by_rel = {i.relation: i for i in res.items}
            self.assertIn("archived", by_rel)
            self.assertEqual(by_rel["archived"].confidence, "verified")
            self.assertEqual(by_rel["archived"].old_path, "comp.aep")
            self.assertEqual(by_rel["archived"].path, "(old)/comp.aep")
            self.assertIn("added", by_rel)

            # stat モードでは duplicates を誤検知しない
            obs_stat = observe_directory(root, depth="stat")
            res_stat = compare_observations(obs_stat, obs_stat)
            self.assertEqual(res_stat.duplicates, [])

    def test_subpath_partial_compare_episode_vs_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ep = Path(tmp) / "ep01"
            (ep / "c001" / "BG").mkdir(parents=True)
            (ep / "c002" / "BG").mkdir(parents=True)
            (ep / "c001" / "BG" / "bg.psd").write_bytes(b"bg-v1")
            (ep / "c002" / "BG" / "bg2.psd").write_bytes(b"bg2")

            delivered = Path(tmp) / "received_c001"
            (delivered / "BG").mkdir(parents=True)
            (delivered / "BG" / "bg.psd").write_bytes(b"bg-v2-retake")

            obs_ep = observe_directory(ep, depth="content")
            obs_deliv = observe_directory(delivered, depth="content")

            res = compare_observations(obs_ep, obs_deliv, left_subpath="c001")
            self.assertEqual(len(res.items), 1)
            self.assertEqual(res.items[0].relation, "updated")
            self.assertEqual(res.items[0].path, "BG/bg.psd")
            self.assertEqual(res.items[0].confidence, "verified")

    def test_ledger_work_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "ledger")
            ledger.add_note(target_unit="c001", status="素材待ち", comment="BG待ち")
            ledger.add_note(
                target_unit="c001",
                status="撮影中",
                pinned_path="c001/comp_t02.aep",
                comment="BG揃った",
            )
            status_map = ledger.get_latest_status_map()
            self.assertEqual(status_map["c001"].status, "撮影中")
            self.assertEqual(status_map["c001"].pinned_path, "c001/comp_t02.aep")

    def test_cli_json_workflow_and_error_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "ep02"
            (work / "c001").mkdir(parents=True)
            (work / "c001" / "a.txt").write_text("v1", encoding="utf-8")

            def _run(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, str(CLI_SCRIPT), *args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

            # 未観測状態で compare すると exit code 1 + JSON error
            r_err = _run("compare", "--dir", str(work), "--json")
            self.assertEqual(r_err.returncode, 1)
            self.assertFalse(json.loads(r_err.stdout)["ok"])

            # observe -> note -> compare -> list
            r_obs = _run("observe", "--dir", str(work), "--note", "開始", "--json")
            self.assertEqual(r_obs.returncode, 0, r_obs.stderr)
            self.assertTrue(json.loads(r_obs.stdout)["ok"])

            r_note = _run(
                "note", "--dir", str(work), "--unit", "c001", "--status", "撮影中", "--json"
            )
            self.assertEqual(r_note.returncode, 0, r_note.stderr)

            (work / "c001" / "b.txt").write_text("v2", encoding="utf-8")
            r_cmp = _run("compare", "--dir", str(work), "--json")
            self.assertEqual(r_cmp.returncode, 0, r_cmp.stderr)
            cmp_data = json.loads(r_cmp.stdout)
            self.assertEqual(cmp_data["summary"].get("added"), 1)

            r_lst = _run("list", "--dir", str(work), "--json")
            self.assertEqual(r_lst.returncode, 0, r_lst.stderr)
            lst_data = json.loads(r_lst.stdout)
            self.assertEqual(len(lst_data["observations"]), 1)
            self.assertEqual(lst_data["unit_statuses"]["c001"]["status"], "撮影中")

    def test_inspect_inventory_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "c010"
            (root / "BG").mkdir(parents=True)
            (root / "MONITOR").mkdir(parents=True)
            (root / "CELL" / "A").mkdir(parents=True)
            (root / "BG" / "bg.psd").write_bytes(b"same-bg")
            (root / "MONITOR" / "bg_copy.psd").write_bytes(b"same-bg")
            (root / "comp.aep").write_bytes(b"aep-body")
            for i in range(1, 3):
                (root / "CELL" / "A" / f"A_{i:04d}.tga").write_bytes(f"f{i}".encode())

            r = subprocess.run(
                [sys.executable, str(CLI_SCRIPT), "inspect", "--dir", str(root), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertTrue(data["ok"])
            self.assertIn("BG (背景)", data["by_kind_counts"])
            self.assertIn("モニター素材", data["by_kind_counts"])
            self.assertIn("AEP (コンポ)", data["by_kind_counts"])
            self.assertIn("CELL (セル)", data["by_kind_counts"])
            self.assertEqual(len(data["duplicate_groups"]), 1)

    def test_sequence_frames_with_same_content_do_not_spam_duplicates(self) -> None:
        """セルの止めコマ・空コマや旧テイク間で同一内容の連番フレームが大量にあっても重複警告に羅列しない。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "c020"
            t1 = root / "CELL" / "take01" / "A"
            t2 = root / "CELL" / "take02" / "A"
            t1.mkdir(parents=True)
            t2.mkdir(parents=True)
            for i in range(1, 6):
                # すべて同じ空コマ・止めコマの内容
                (t1 / f"A_{i:04d}.tga").write_bytes(b"blank-frame")
                (t2 / f"A_{i:04d}.tga").write_bytes(b"blank-frame")

            obs = observe_directory(root, depth="content")
            from acfvs.interpreter import build_inventory

            rep = build_inventory(obs)
            self.assertEqual(rep.duplicate_groups, [])

            res = compare_observations(obs, obs)
            self.assertEqual(res.duplicates, [])

    def test_slot_overview_and_package_identity(self) -> None:
        """カットフォルダー構成（スロット×塊）の俯瞰と、塊単位の同一性判定を検証する。"""
        with tempfile.TemporaryDirectory() as tmp:
            cut = Path(tmp) / "c0000"
            (cut / "(old)").mkdir(parents=True)
            (cut / "BG" / "(old)").mkdir(parents=True)
            (cut / "CELL" / "(old)" / "proj_0000_old").mkdir(parents=True)
            (cut / "CELL" / "proj_0000").mkdir(parents=True)
            (cut / "3D" / "A").mkdir(parents=True)
            (cut / "TS").mkdir(parents=True)

            (cut / "proj_0000_t01.aep").write_bytes(b"aep-t01")
            (cut / "(old)" / "proj_0000_t00.aep").write_bytes(b"aep-t00")
            (cut / "BG" / "proj_0000_bg.psd").write_bytes(b"bg-psd")
            (cut / "TS" / "proj_0000_t01.tdts").write_bytes(b"ts-data")

            for i in range(1, 4):
                (cut / "CELL" / "proj_0000" / f"A_{i:04d}.tga").write_bytes(f"cell-{i}".encode())
                # (old) にまったく同じ内容の塊がある場合
                (cut / "CELL" / "(old)" / "proj_0000_old" / f"A_{i:04d}.tga").write_bytes(
                    f"cell-{i}".encode()
                )
            for i in range(1, 3):
                (cut / "3D" / "A" / f"cg_{i:04d}.exr").write_bytes(f"cg-{i}".encode())

            r = subprocess.run(
                [sys.executable, str(CLI_SCRIPT), "inspect", "--dir", str(cut), "--slots", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertTrue(data["ok"])

            slots = {s["slot_name"]: s for s in data["slots"]}
            self.assertEqual(slots["AEP"]["state"], "ok")
            self.assertEqual(len(slots["AEP"]["archived_packages"]), 1)
            self.assertEqual(slots["CELL"]["state"], "ok")
            cell_pkg = slots["CELL"]["active_packages"][0]
            self.assertEqual(cell_pkg["name"], "proj_0000")
            self.assertTrue(cell_pkg["is_folder"])
            self.assertEqual(cell_pkg["file_count"], 3)
            self.assertEqual(cell_pkg["seq_count"], 1)
            self.assertEqual(cell_pkg["duplicate_of"], ["CELL/(old)/proj_0000_old"])
            self.assertEqual(slots["3D"]["state"], "ok")
            self.assertEqual(slots["FX"]["state"], "empty")

    def test_observe_with_subpath_scans_only_target_cut(self) -> None:
        """話数フォルダーを指定しても subpath を指定すれば対象カットのみ走査し、他カットを読まない。"""
        with tempfile.TemporaryDirectory() as tmp:
            ep = Path(tmp) / "ep03"
            (ep / "c0001" / "BG").mkdir(parents=True)
            (ep / "c0001" / "BG" / "bg1.psd").write_bytes(b"bg1")
            (ep / "c0002" / "CELL").mkdir(parents=True)
            for i in range(1, 5):
                (ep / "c0002" / "CELL" / f"A_{i:04d}.tga").write_bytes(b"cell")

            obs = observe_directory(ep, subpath="c0001", depth="content")
            self.assertEqual(len(obs.entries), 1)
            self.assertEqual(obs.entries[0].path, "c0001/BG/bg1.psd")

            from acfvs.interpreter import build_slot_overview

            rep = build_slot_overview(obs, subpath="c0001")
            slots = {s.slot_name: s for s in rep.slots}
            self.assertEqual(slots["BG"].state, "ok")
            self.assertEqual(slots["CELL"].state, "empty")


if __name__ == "__main__":
    unittest.main()
