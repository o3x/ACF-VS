"""
ACF-VS (Anime Cut Folder Versioning System) 再設計プロトタイプ核パッケージ。

ファイルに触れず（読むだけ）、フォルダー状態の「観測（Observation）」、
二つの状態の「照合（Compare）」、現場規則による「解釈（Interpret）」、
および工程メモ・状態管理（Ledger）を提供する。

バージョン: 0.4.8
更新日時: Wed Nov 18 20:52:58 JST 2026
"""

__version__ = "0.4.8"
__updated__ = "Wed Nov 18 20:52:58 JST 2026"

from .models import (
    CompareResult,
    DiffItem,
    FileEntry,
    Observation,
    ObservationHeader,
    SequenceGroup,
    WorkNote,
)
from .observer import load_observation, observe_directory, save_observation
from .comparer import compare_observations
from .ledger import Ledger

__all__ = [
    "__version__",
    "__updated__",
    "FileEntry",
    "ObservationHeader",
    "Observation",
    "SequenceGroup",
    "DiffItem",
    "CompareResult",
    "WorkNote",
    "observe_directory",
    "save_observation",
    "load_observation",
    "compare_observations",
    "Ledger",
]
