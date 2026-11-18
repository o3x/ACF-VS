# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# ACF-VS (Anime Cut Folder Versioning System) Agent

## Role
あなたは日本のアニメーション制作パイプラインに精通した、シニア・ツール開発エンジニアです。
PythonとPowerShellを用いた、高速かつ堅牢なデスクトップアプリケーション（CLI/GUI）の設計・実装・リファクタリングを行います。

## Context
本プロジェクト（ACF-VS）は、アニメーション制作の撮影工程（コンポジット）に特化した、ハッシュベースの軽量なフォルダー状態記録システムです。
巨大なバイナリや数千枚の連番画像をGit等で管理する際の破綻を防ぐため、ファイルの実体はコピーせず、「ハッシュ値（指紋）とパスの状態」のみを `.cut_manifest.json` に記録して差分を高速に追跡します。

**主要コンポーネント:**
* `acfvs/`: v0.4.x 再設計プロトタイプ核パッケージ（`models.py`, `observer.py`, `interpreter.py`, `comparer.py`, `profile.py`, `ledger.py`, `cli.py`, `gui.py`）
* `acfvs_cli.py`: 新プロトタイプの CLI / GUI（`tkinter`）ランチャー
* `tests/test_acfvs_v2.py`: 再設計プロトタイプの単体・結合テスト（10本）
* `acvs_core.py`: 現行版（0.3.x）Python 3.10+ コアロジック
* `acvs_gui.ps1`: 現行版 Windows 向け PowerShell GUI ラッパー
* `tests/test_characterization.py`: 現行版 CLI 境界の特性テスト（15本）
* `test_seq_generator.py`: 手動検証用ダミーデータ生成スクリプト
* `Rename-OldAepFiles.ps1`: `(old)` フォルダ内の AEP に更新日時を付与してリネームする独立ユーティリティ（コアとは非連携）

## 現状（2026-11-18）— v0.4.8 再設計プロトタイプ試作中（`redesign` ブランチ）

**再設計の設計思想（[docs/261116_再設計_設計思想.md](docs/261116_再設計_設計思想.md)）に基づき、実際に現場で触りながら改善するためのプロトタイプ（`acfvs/`・v0.4.8）を実装しています。** 現行版（`acvs_core.py`）もテスト15本付きで維持しています。

* 主な実装済み機能（v0.4.0〜v0.4.8）: JSONL 観測記録（前回 SHA-256 再利用）／連番範囲を外した照合・証拠の強さ付き比較／作品プロファイル（`acfvs_profile.json`）によるスロット×塊単位の俯瞰・塊ハッシュID表示／外部台帳対応・工程メモ（`notes.jsonl`）／ビジュアル構成マップ付き `tkinter` GUI（空スロット表示切替・塊内サブフォルダー階層・塊同士比較・関連付けアプリ起動・話数フォルダー時のカット選択ドロップダウン）
* 現行の挙動を変えるときは、特性テストを先に直す・足す。出力プロトコル（下記）は `acvs_gui.ps1` が依存している

### 現行の既知の制約（再設計の動機。一時フォルダーで再現して確認済み）

| 制約 | 内容 |
|---|---|
| 連番への追加が別物扱い | 連番のキーにコマ範囲が入るため、1枚足すと `A_[0001-0003].tga` が `[DELETED]`、`A_[0001-0004].tga` が `[NEW]` と出る |
| 無関係なファイルが重複と出る | `--fast` ではサイズと更新日時が同じだけで同一ハッシュ扱い。別内容でも `[DUPLICATE]` と出る |
| `--fast` の切り替えで全件 UPDATED | 3 種類のハッシュ形式が互換でないため |
| 未初期化でも終了コード 0 | `status`/`commit` は `Fatal:` を標準出力に書くだけ。呼び出し側は文字列で判定するしかない |
| 「誰が」が記録されない | 履歴にあるのは時刻だけ。作業者・マシン・ひとことは無い |

## よく使うコマンド

外部依存ゼロ（Python 標準ライブラリのみ）。ビルド・lint・pip install は不要。

```bash
# CLI 実行（対象カットフォルダを --dir で指定）
python acvs_core.py init   --dir <カットフォルダ>                # 管理開始（.cut_manifest.json 生成）
python acvs_core.py status --dir <カットフォルダ> --fast --seq   # 前回コミットとの差分表示（記録しない）
python acvs_core.py commit --dir <カットフォルダ> --fast --seq   # マニフェスト更新＋履歴スナップショット保存
python acvs_core.py log    --dir <カットフォルダ>                # コミット履歴一覧
python acvs_core.py diff   --dir <カットフォルダ> --fast --seq --target <ts1> [<ts2>]
# --target 0個: 最新履歴 vs 現在 / 1個: 指定履歴 vs 現在 / 2個: 履歴同士の比較
# scan / verify は status のエイリアス
```

```powershell
# GUI 起動（Windows のみ。Mac では動作確認不可）
.\acvs_gui.ps1

# AEP リネームユーティリティ（必ず -WhatIf で Dry Run してから本番実行）
.\Rename-OldAepFiles.ps1 -BasePath "C:\Project" -WhatIf
```

### 動作検証

**自動テスト（unittest・標準ライブラリのみ）:**

```bash
python -m unittest discover -s tests -v   # 全25本（現行15本＋プロトタイプ10本）
```

`tests/test_characterization.py` は CLI 境界（subprocess）だけに依存する特性テスト。GUI が正規表現で読む出力プロトコル（`PROGRESS:` 行・`Fatal:` 行・`[NEW]` 等のタグ・`Backup saved`・`Initialized`・log の `[YYYYMMDD_HHMMSS]` 行頭）と、マニフェスト破損時の挙動を固定している。**`--fast` は使わない**（mtime の分解能でテストが不安定になるため）。

**手動検証（ダミー環境を生成）:**

```bash
python test_seq_generator.py --dir test_env --count 1000   # CELL/A_cell に1000枚、BG/A_bg に50枚生成
python acvs_core.py init --dir test_env --fast --seq
# → ファイルを追加・更新・(old)へ移動などしてから status / commit / diff で分類結果を確認
```

`test_deletion/`, `test_seq/`, `test_env/` はローカルの検証用ディレクトリ（git 管理外）。リポジトリ直下の `git_status*.txt`・`output*.txt`・`test_move2_output.txt` は過去の検証残骸（git 管理外）で、使っていない。

## アーキテクチャ

### データフロー（GUI ↔ コアのプロトコル — 変更時最注意）

`acvs_gui.ps1` は `python acvs_core.py ...` をサブプロセス起動し、**標準出力の文字列を正規表現でパースして UI を駆動する**。したがって `acvs_core.py` の以下の出力文字列を変更すると GUI が壊れる：

* `PROGRESS: <n>/<total>` → プログレスバー更新（10件ごと＋最終件に出力）
* `Fatal: .*\.cut_manifest\.json not found` → 未初期化と判定し「自動 Init 確認ダイアログ」を表示
* `Backup saved` / `Initialized` → commit/init 成功と判定し履歴リストを自動リフレッシュ
* `[YYYYMMDD_HHMMSS]` で始まる log 出力行 → 履歴リストボックスの項目（Diff のタイムスタンプ抽出元）
* マニフェスト破損時のエラー文には `not found` という語を使わない（上の自動 Init 判定に誤マッチして、破損時に init を促してしまうため）

文字化け対策として、Python 側は `sys.stdout.reconfigure(encoding='utf-8')`、PowerShell 側は `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` で UTF-8 を強制している。

### コアロジック（`acvs_core.py` / `ACVSCore` クラス）

1. **`scan_directory()`**: 3 つの内部メソッドを順に呼ぶ。
   * `_collect_files()`: `os.walk` で再帰走査し、(通常ファイル, 連番候補) に仕分ける
   * `_hash_files()`: `ThreadPoolExecutor` で並列ハッシュ計算（`_hash_single()` が 1 ファイル分）。`PROGRESS:` 行の出力仕様はここ
   * `_group_sequences()`: 連番候補をグループ化。2 枚未満のグループは通常ファイルとして `_hash_single()` に戻す
   * 除外対象はクラス定数 `EXCLUDE_DIRS = {.git, .acvs_history, __pycache__, test_env}`・`EXCLUDE_FILES = {.gitignore, acvs_core.py, test_seq_generator.py}` と、`.cut_manifest` で始まるパス。ファイル名の除外は**全階層**に効く
2. **`compare_states()`**: 4パスの差分判定アルゴリズム。順序が重要：
   * Pass 1: パスもハッシュも一致 → 処理済みにマーク
   * Pass 2: ハッシュ一致・パス不一致 → `moved`。移動元が `is_archived` でなく移動先が `is_archived` なら `moved_to_archive`（アーカイブ化）として区別
   * Pass 3: 残りの新パス → 旧 state にパスがあれば `updated`、なければ `new`
   * Pass 4: 未処理の旧パス → `deleted`
   * 別途、同一ハッシュが複数パスに存在すれば `redundant_copies` 警告
3. **`print_changes()`**: `status` と `diff` の結果表示を集約。**表示文字列は GUI とユーザーが依存するため変更禁止**
4. **ハッシュは3形式**あり、相互に互換性がない（`--fast` の ON/OFF を切り替えると全ファイルが UPDATED 扱いになる点に注意）：
   * 通常: SHA-256（4MB チャンクのストリーム読み）
   * fast モード: `fast:<size>:<mtime>`
   * 連番グループ: `seq:<合計size>:<最大mtime>:<枚数>`
5. **連番グループ化（`--seq`）**: 正規表現 `^(.*?)([0-9]{4,})\.([a-zA-Z0-9]+)$`（テイク番号 t01 等と区別するため**4桁以上**）でマッチした同一ディレクトリ・同一プレフィックス・同一拡張子のファイルが **2枚以上**あれば `prefix_[0001-1000].ext` という単一キーに統合する
6. **`is_archived`**: パス全体（ファイル名を含む）を小文字にして `(old)` を含むか。大文字小文字は区別しない

### マニフェストと履歴（スナップショット方式）

* `.cut_manifest.json`: 最新状態。`{"_meta": {...}, "state": {相対パス: アイテム}}` 構造（スキーマ詳細は **MANIFEST_SPEC.md** が正）
* `.acvs_history/<YYYYMMDD_HHMMSS>.json`: コミットごとのフルスナップショット。差分（Delta）ではなく毎回全状態を記録する設計（履歴1件の破損が他に波及しない・任意時点間の比較が2ファイルの比較だけで済む）
* `load_manifest()` は旧フォーマット（`_meta` なし・ルート直下に state）も吸収する後方互換ロジックを持つ。破損時は対処ヒントつきのエラーで終了コード 1 で止まる（自動再生成はしない）
* **state のスキーマを変更する場合は必ず `MANIFEST_SPEC.md` と `schema_version` を更新すること**。AE の JSX 等サードパーティがこの JSON をパースする想定のため、互換性ポリシー（後方互換ありなら Minor/Revision、破壊的変更なら Major）に従う。現時点で、このワークスペース内にこの JSON を読む道具は見つかっていない

## Tech Stack & Engine Rules
* **[DO] Python (Core)**: Python 3.10以上の仕様を前提とし、型ヒント（Type Hints）を積極的に使用して可読性と安全性を高めること。外部ライブラリ（pip等）への依存は極力避け、標準ライブラリで完結させること。
* **[DO] PowerShell (GUI)**: Windows 10/11環境で動作するPowerShellスクリプトとして記述すること。UI操作がメインスレッドをブロックしないよう配慮すること。
* **[DO NOT] 重いライブラリの無断追加**: 現場のPC環境への導入ハードルを下げるため、ユーザーに新たなインストール作業を強いるライブラリの追加は原則禁止とする。

## Boundaries & Constraints
* **[DO NOT] ファイル実体の破壊/複製**: 本システムは「状態の記録」が目的であるため、スクリプト側からユーザーの元ファイル（素材データなど）を無断で削除・移動・複製する処理を絶対に書いてはならない。
* **[DO NOT] メモリの枯渇**: 数千〜数万ファイルの走査を行うため、全ファイルのデータを一度にメモリに読み込むような実装は禁止。ジェネレータやストリーム処理を活用すること。
* **[DO] 高速化の維持**: `--fast`（ファイルサイズ＋更新日時による判定）や `--seq`（連番画像のグループ化処理）のロジックを変更する際は、処理速度が低下しないか常に検証すること。
* **[DO NOT] 公開リポジトリに非公開の情報を書かない**: このリポジトリは GitHub 上で**公開**されている。非公開の連携リポジトリのパス・指示書の番号・作品コード・現場の固有名詞を、README・CHANGELOG・EXEC-REPORT・コミットメッセージ・設計文書に書かない。変更内容だけを書く。大山さんの発言を原文で載せる文書は、コミット前に大山さんに確認する。

## Coding Conventions
* **Python**: `PEP 8` 準拠。
  * 関数名・変数名は `snake_case`、クラス名は `PascalCase`。
  * パス操作は新規コードでは `pathlib.Path` を推奨。ただし既存の `os.path` ベースのコード（`acvs_core.py` 全体）は動作実績を優先してそのまま維持し、修正時に周辺だけを無理に移行しないこと。
  * マニフェストのキー（相対パス）は `/` 区切りに正規化する既存方針（`rel_path.replace('\\', '/')`）に従い、OS間のパス区切り文字の違いを吸収すること。
* **PowerShell**: 
  * 関数名は標準の `Verb-Noun`（動詞-名詞）形式を推奨。
  * 変数名は適宜 `camelCase` または `PascalCase` とし、意味が明確な名称にすること。
* **共通の禁止事項**: `data`, `tmp`, `process` などの曖昧な命名は禁止。

## Knowledge Documentation (最重要)
OSのファイルシステム特有の挙動（Windowsのパス長制限、ネットワークドライブの遅延など）に対するワークアラウンドを行った際は、必ず以下のJSDoc/Docstring風コメントを実装箇所に記述すること。
* `@problem`: 直面した仕様の壁やエラーの原因（Why it failed）
* `@solution`: 採用した解決策と、そのアプローチをとった理由（How we fixed it and Why）

## 文書の地図

| 文書 | 役割 |
|---|---|
| `README.md` | 利用者向け。何ができて何ができないか・使い方・現状の制約 |
| `CLAUDE.md`（このファイル） | エージェント向け。規約・アーキテクチャ・現状・再開の入口 |
| `MANIFEST_SPEC.md` | 現行の `.cut_manifest.json` / 履歴の形式（v1.0.1）。再設計で置き換わる見込み |
| `docs/261116_再設計_設計思想.md` | 再設計の設計思想（たたき台）。**再開の入口** |
| `CHANGELOG.md` | 版ごとの変更。日時は版ごとにコマンドで取る |
| `EXEC-REPORT.md` | 0.3.3 のリファクタリングの実行記録（過去の記録。更新しない） |

## Agent Behavior & Workflow
エージェントとして回答・コード生成を行う際は、以下の振る舞いを遵守してください。
1. **Think First**: コードを出力する前に、大量ファイル処理時のパフォーマンスやエッジケース（空フォルダ、アクセス権限エラー等）を論理的に思考すること。
2. **No Apologies**: 修正時に「申し訳ありません」などの謝罪は不要。即座に修正コードと原因の簡潔な説明を提供すること。
3. **Actionable Errors**: 例外処理（`try...except` / `try...catch`）を徹底し、エラー時にはスタックトレースだけでなく、ユーザーがどうすれば解決できるか（例：「対象フォルダのアクセス権限を確認してください」等）のメッセージを出力すること。

## Language & Communication (言語設定)
* **[DO] 完全な日本語の徹底**: 回答、作業計画のやり取り、コード内のコメントなど、すべての出力は必ず「日本語」で行うこと。

## Workflow & Versioning (作業フローとバージョン管理)
作業を進め、ソースコードに変更を加えた際は、以下のフローを必ず実行すること。

* **[DO] 版は作業の一歩目で上げる**: 新しい作業に着手する最初の編集で、版番号と CHANGELOG の見出しを先に上げる。途中で方針が変わっても版は残す。
* **[DO] CHANGELOG.md の更新**: 
  * 作業完了後、必ずプロジェクトルートの `CHANGELOG.md` を日本語で更新すること。
  * ログ日時の形式は `Wed Dec 03 11:05:00 JST 2025`（曜日 月 日 時:分:秒 JST 年）を厳守すること。**日時は推測で書かず、版ごとにコマンドで取る**（Windows は `powershell -Command "[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::InvariantCulture; Get-Date -Format 'ddd MMM dd HH:mm:ss JST yyyy'"`。ロケールを固定しないと曜日・月名が日本語になる）。
* **[DO] ソースコード内のメタデータ更新**: 
  * コードを更新した際は、ファイル先頭のdocstring等の適切な場所に「更新日付」と「バージョン」を記載・更新すること（存在しない場合は新規に追加する）。
  * ソース内の更新日付の形式も `Sat Dec 06 13:05:00 JST 2025` の形を厳守すること。
  * バージョンは変更の規模（バグ修正か、機能追加か等）に応じて適切にアップ（リビジョン/マイナー/メジャー）させ、そのバージョン番号も `CHANGELOG.md` の記録と一致させること。
* **[DO] git add はファイル名で指定する**（ディレクトリ指定をしない。未追跡の資料を巻き込まないため）。
