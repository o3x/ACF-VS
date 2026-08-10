# ACF-VS 特性テスト（characterization tests）
# 目的: リファクタリング前の現状挙動を CLI 境界（subprocess）で固定する。
# GUI (acvs_gui.ps1) が標準出力を正規表現でパースするため、
# 出力プロトコル（PROGRESS 行・Fatal 行・タグ表記など）ごとテストで保護する。
# 外部依存ゼロの規約に従い unittest + tempfile + subprocess のみを使用する。

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).parent.parent / "acvs_core.py"


def run_acvs(workdir, *args):
    """acvs_core.py を CLI 境界（subprocess）で実行し CompletedProcess を返す"""
    return subprocess.run(
        [sys.executable, str(CORE), *args, "--dir", str(workdir)],
        capture_output=True, text=True, encoding="utf-8",
    )


def write_file(workdir, rel_path, content):
    """作業フォルダ内にテキストファイルを作成する（親フォルダも作る）"""
    path = Path(workdir) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class CharacterizationTest(unittest.TestCase):
    """各テストが独立した一時フォルダで init/status/commit/log/diff を実行して現状挙動を確認する"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_init_creates_manifest(self):
        write_file(self.workdir, "a.txt", "init_creates_manifest 用の内容")
        result = run_acvs(self.workdir, "init")
        self.assertIn("Initialized manifest with 1 files.", result.stdout)
        self.assertTrue((Path(self.workdir) / ".cut_manifest.json").exists())

    def test_init_twice_refuses(self):
        write_file(self.workdir, "a.txt", "init_twice_refuses 用の内容")
        run_acvs(self.workdir, "init")
        result = run_acvs(self.workdir, "init")
        self.assertIn("Already initialized.", result.stdout)

    def test_status_uninitialized_fatal(self):
        # GUI の自動 Init 確認ダイアログのトリガー（正規表現マッチ対象）
        result = run_acvs(self.workdir, "status")
        self.assertIn("Fatal:", result.stdout)
        self.assertIn(".cut_manifest.json not found", result.stdout)

    def test_status_clean(self):
        write_file(self.workdir, "a.txt", "status_clean 用の内容")
        run_acvs(self.workdir, "init")
        result = run_acvs(self.workdir, "status")
        self.assertIn("Nothing to commit, working tree clean", result.stdout)

    def test_status_new_file(self):
        write_file(self.workdir, "a.txt", "status_new_file 用の内容")
        run_acvs(self.workdir, "init")
        write_file(self.workdir, "b.txt", "status_new_file 用の追加ファイル")
        result = run_acvs(self.workdir, "status")
        self.assertIn("[NEW] b.txt", result.stdout)

    def test_status_updated(self):
        write_file(self.workdir, "a.txt", "status_updated 用の内容")
        run_acvs(self.workdir, "init")
        # 内容だけでなくサイズも変える（ハッシュ変化を確実にする）
        write_file(self.workdir, "a.txt", "status_updated 用の内容を書き換えてサイズも変更した")
        result = run_acvs(self.workdir, "status")
        self.assertIn("[UPDATED] a.txt", result.stdout)

    def test_status_moved(self):
        write_file(self.workdir, "a.txt", "status_moved 用の内容")
        run_acvs(self.workdir, "init")
        dest = Path(self.workdir) / "sub" / "a.txt"
        dest.parent.mkdir()
        shutil.move(str(Path(self.workdir) / "a.txt"), str(dest))
        result = run_acvs(self.workdir, "status")
        self.assertIn("[MOVED] a.txt -> sub/a.txt", result.stdout)

    def test_status_archived(self):
        write_file(self.workdir, "a.txt", "status_archived 用の内容")
        run_acvs(self.workdir, "init")
        dest = Path(self.workdir) / "(old)" / "a.txt"
        dest.parent.mkdir()
        shutil.move(str(Path(self.workdir) / "a.txt"), str(dest))
        result = run_acvs(self.workdir, "status")
        self.assertIn("[ARCHIVED (old)] a.txt -> (old)/a.txt", result.stdout)

    def test_status_deleted(self):
        write_file(self.workdir, "a.txt", "status_deleted 用の内容")
        run_acvs(self.workdir, "init")
        (Path(self.workdir) / "a.txt").unlink()
        result = run_acvs(self.workdir, "status")
        self.assertIn("[DELETED] a.txt", result.stdout)

    def test_duplicate_warning(self):
        write_file(self.workdir, "a.txt", "duplicate_warning 用の同一内容")
        run_acvs(self.workdir, "init")
        # init 後に同一内容のファイルをもう1つ追加 → 重複警告
        write_file(self.workdir, "copy.txt", "duplicate_warning 用の同一内容")
        result = run_acvs(self.workdir, "status")
        self.assertIn("[DUPLICATE]", result.stdout)

    def test_progress_protocol(self):
        # GUI のプログレスバーが依存する PROGRESS 行（10件ごと＋最終件）
        for i in range(12):
            write_file(self.workdir, f"file_{i}.txt", f"progress_protocol 用の内容 {i}")
        result = run_acvs(self.workdir, "init")
        self.assertIn("PROGRESS: 12/12", result.stdout)

    def test_seq_grouping(self):
        for i in range(1, 4):
            write_file(self.workdir, f"cut_{i:04d}.tga", f"seq_grouping 用の内容 {i}")
        run_acvs(self.workdir, "init", "--seq")
        manifest = json.loads(
            (Path(self.workdir) / ".cut_manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("cut_[0001-0003].tga", manifest["state"])
        result = run_acvs(self.workdir, "status", "--seq")
        self.assertIn("Nothing to commit, working tree clean", result.stdout)

    def test_commit_and_log(self):
        write_file(self.workdir, "a.txt", "commit_and_log 用の内容")
        run_acvs(self.workdir, "init")
        write_file(self.workdir, "b.txt", "commit_and_log 用の追加ファイル")
        commit_result = run_acvs(self.workdir, "commit")
        self.assertIn("Backup saved", commit_result.stdout)
        log_result = run_acvs(self.workdir, "log")
        # 履歴リスト項目の行頭 [YYYYMMDD_HHMMSS]（GUI のタイムスタンプ抽出元）
        self.assertRegex(log_result.stdout, r"(?m)^\[\d{8}_\d{6}\]")

    def test_corrupt_manifest_actionable_error(self):
        # マニフェスト破損時は Traceback で即死せず、対処ヒントつきのエラーで停止する（R3）
        write_file(self.workdir, "a.txt", "corrupt_manifest 用の内容")
        run_acvs(self.workdir, "init")
        (Path(self.workdir) / ".cut_manifest.json").write_text("{broken", encoding="utf-8")
        result = run_acvs(self.workdir, "status")
        self.assertEqual(result.returncode, 1)
        self.assertIn("corrupted", result.stdout)
        self.assertIn("Hint:", result.stdout)
        self.assertNotIn("Traceback", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_diff_with_target(self):
        write_file(self.workdir, "a.txt", "diff_with_target 用の内容")
        run_acvs(self.workdir, "init")
        write_file(self.workdir, "b.txt", "diff_with_target 用の追加ファイル")
        run_acvs(self.workdir, "commit")
        write_file(self.workdir, "c.txt", "diff_with_target 用のさらに追加したファイル")
        history_files = sorted(os.listdir(Path(self.workdir) / ".acvs_history"))
        self.assertTrue(history_files)
        ts = history_files[-1].replace(".json", "")
        self.assertRegex(ts, r"^\d{8}_\d{6}$")
        result = run_acvs(self.workdir, "diff", "--target", ts)
        self.assertIn("[NEW] c.txt", result.stdout)


if __name__ == "__main__":
    unittest.main()
