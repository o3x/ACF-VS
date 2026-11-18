"""
ACF-VS 台帳（Ledger）モジュール。

観測ファイル（observations/*.jsonl）と工程メモ（notes.jsonl）の保存・一覧・検索を行う。
台帳は対象フォルダー内の `.acfvs` でも、外部の任意のフォルダーでも同じ形式で扱える。

バージョン: 0.4.0
更新日時: Wed Nov 18 11:28:37 JST 2026
"""

from __future__ import annotations

import getpass
import json
import secrets
import socket
from datetime import datetime, timezone
from pathlib import Path

from .models import Observation, ObservationHeader, WorkNote
from .observer import load_observation, save_observation


def resolve_ledger_dir(target_dir: str | Path, ledger_dir: str | Path | None = None) -> Path:
    """台帳ディレクトリを決定する。未指定時は対象フォルダー内の `.acfvs` を使う。"""
    if ledger_dir is not None and str(ledger_dir).strip():
        return Path(ledger_dir).resolve()
    return Path(target_dir).resolve() / ".acfvs"


class Ledger:
    """観測と工程メモを管理する台帳。"""

    def __init__(self, ledger_dir: str | Path) -> None:
        self.base_dir = Path(ledger_dir).resolve()
        self.obs_dir = self.base_dir / "observations"
        self.notes_file = self.base_dir / "notes.jsonl"

    def save_observation(self, obs: Observation) -> Path:
        """観測を台帳に保存する。"""
        return save_observation(obs, self.obs_dir)

    def list_observations(self) -> list[ObservationHeader]:
        """台帳内の観測ヘッダー一覧を新しい順で返す（1行目のみ読むため高速）。"""
        if not self.obs_dir.exists():
            return []

        headers: list[ObservationHeader] = []
        for path in self.obs_dir.glob("*.jsonl"):
            if path.name.startswith(".tmp."):
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                if not first_line:
                    continue
                raw = json.loads(first_line)
                headers.append(ObservationHeader.from_dict(raw))
            except (OSError, json.JSONDecodeError, KeyError):
                continue

        headers.sort(key=lambda h: h.taken_at, reverse=True)
        return headers

    def load_observation(self, obs_id: str) -> Observation:
        """ID指定（前方一致も可）で観測を読み込む。"""
        exact = self.obs_dir / f"{obs_id}.jsonl"
        if exact.exists():
            return load_observation(exact)

        if self.obs_dir.exists():
            matches = [
                p
                for p in self.obs_dir.glob(f"{obs_id}*.jsonl")
                if not p.name.startswith(".tmp.")
            ]
            if len(matches) == 1:
                return load_observation(matches[0])
            if len(matches) > 1:
                raise ValueError(f"観測ID '{obs_id}' に複数候補が一致しました: {[m.stem for m in matches]}")

        raise FileNotFoundError(f"観測が見つかりません: {obs_id}")

    def get_latest_observation(self) -> Observation | None:
        """最新の観測を1件返す。存在しなければ None。"""
        headers = self.list_observations()
        if not headers:
            return None
        return self.load_observation(headers[0].id)

    def add_note(
        self,
        *,
        target_unit: str,
        status: str,
        pinned_path: str = "",
        comment: str = "",
        author: str = "",
    ) -> WorkNote:
        """工程メモ（状態・正ファイル指定・コメント）を追記する。"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")
        note = WorkNote(
            note_id=f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}",
            created_at=now,
            author=author or getpass.getuser(),
            host=socket.gethostname(),
            target_unit=target_unit.strip("/").replace("\\", "/"),
            status=status,
            pinned_path=pinned_path.strip().replace("\\", "/"),
            comment=comment,
        )
        with self.notes_file.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(note.to_dict(), ensure_ascii=False) + "\n")
        return note

    def list_notes(self, target_unit: str | None = None) -> list[WorkNote]:
        """工程メモを新しい順で返す。"""
        if not self.notes_file.exists():
            return []

        indexed_notes: list[tuple[int, WorkNote]] = []
        with self.notes_file.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                text = line.strip()
                if not text:
                    continue
                try:
                    raw = json.loads(text)
                    note = WorkNote.from_dict(raw)
                except (json.JSONDecodeError, KeyError):
                    continue
                if target_unit is not None and note.target_unit != target_unit:
                    continue
                indexed_notes.append((idx, note))

        indexed_notes.sort(key=lambda item: (item[1].created_at, item[0]), reverse=True)
        return [note for _, note in indexed_notes]

    def get_latest_status_map(self) -> dict[str, WorkNote]:
        """ユニット（カット等）ごとの最新の工程メモを返す。"""
        latest: dict[str, WorkNote] = {}
        # list_notes は新しい順なので、最初に出現したものが最新
        for note in self.list_notes():
            if note.target_unit not in latest:
                latest[note.target_unit] = note
        return latest
