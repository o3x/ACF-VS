"""
ACF-VS (v0.4.0) CLI 起動スクリプト。

使い方:
  python acfvs_cli.py gui
  python acfvs_cli.py observe --dir <フォルダー>
  python acfvs_cli.py compare --dir <フォルダー>
  python acfvs_cli.py list --dir <フォルダー>
  python acfvs_cli.py note --dir <フォルダー> --unit c001 --status 撮影中

バージョン: 0.4.0
更新日時: Wed Nov 18 11:28:37 JST 2026
"""

from __future__ import annotations

import sys

from acfvs.cli import main

if __name__ == "__main__":
    sys.exit(main())
