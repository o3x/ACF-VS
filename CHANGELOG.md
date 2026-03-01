# Changelog

すべての顕著な変更はこのファイルに記録されます。

## [0.2.12] - Sun Mar 01 18:25:56 JST 2026
### Changed
- `acvs_core.py`: `.cut_manifest.json` および `.acvs_history/` の履歴JSONファイルを保存する際、辞書のキー（ファイルパス）でアルファベット順にソートして出力するように改善しました。
- `acvs_core.py`: 「Group Seq Images」の連番グループ化判定の正規表現を緩和し、数字の前にアンダーバーがないファイル（例: `i0001.tga`）も正しく連番としてグループ化されるように修正しました。

## [0.2.11] - Sun Mar 01 17:53:17 JST 2026
### Changed
- `acvs_core.py`: `.cut_manifest.json` に加え、`.acvs_history/` 内に保存される履歴用のJSON内にも `generator` と `schema_version` (v1.0.1) を記録するように改善しました。
- `MANIFEST_SPEC.md`: 履歴ファイルへのメタデータ追加に対応し、スキーマレベルを `1.0.1` へ更新しました。また、今後のバージョンアップに備えたスキーマのバージョニングポリシーと、冗長性を確保するスナップショットアーキテクチャの解説を追記しました。

## [0.2.10] - Sat Feb 28 15:57:13 JST 2026
### Fixed
- `acvs_core.py`: `init`（初期化）時に Fast Mode や Group Seq の引数を受け継いでいなかったバグを修正。これにより、初期化直後のスキャンで「すべて変更された」と誤検知される問題を解消しました。
- `acvs_core.py` / `acvs_gui.ps1`: Pythonの標準出力エンコーディングを強制的にUTF-8化する処理を追加し、日本語（2バイト文字）のファイル名・フォルダ名が画面上で文字化け（Mojibake）する問題を修正しました。

## [0.2.9] - Sat Feb 28 15:48:42 JST 2026
### Added
- `acvs_gui.ps1`: 処理の進捗を視覚化するプログレスバーを導入。
- `acvs_gui.ps1`: マニフェスト不在時に自動で初期化を提案する対話型ダイアログを実装。
- `acvs_core.py`: `concurrent.futures` を使用した並列ハッシュ計算を実装し、大量のファイル処理を高速化。
- `acvs_core.py`: リアルタイム進捗報告機能（`PROGRESS: n/total`）を追加。

### Changed
- `acvs_gui.ps1`: 独立した「Init」ボタンを廃止し、スキャン時の自動検知ワークフローに統合。

## [0.2.7] - Sat Feb 28 15:41:57 JST 2026
### Added
- `acvs_gui.ps1`: 初回利用時のための「Init (Setup)」ボタンを追加。
- `acvs_core.py`: スキャン時に `.git`, `.acvs_history`, `__pycache__` などのシステムディレクトリを除外するように改善（パフォーマンス向上）。

### Fixed
- `acvs_gui.ps1`: チェックボックス `Group Seq Images` の論理エラーを修正。
- `acvs_gui.ps1`: コマンド完了時に「Done.」メッセージを表示するように改善。

## [0.2.6] - Sat Feb 28 15:29:42 JST 2026
### Changed
- `acvs_gui.ps1`: フォルダ選択ダイアログを、従来のツリー形式から「ファイル選択」スタイルのモダンなエクスプローラー形式に変更し、操作性を向上させました。

## [0.2.5] - Sat Feb 28 15:01:48 JST 2026
### Fixed
- `acvs_gui.ps1`: エンコーディング修復作業において発生した二重エンコード（文字化けの固定化）を修正し、オリジナルの日本語文字列を復旧。確実にBOM付きUTF-8として保存しました。

## [0.2.4] - Sat Feb 28 15:00:24 JST 2026
### Fixed
- `acvs_gui.ps1`: 日本語環境での文字化けを解消するため、ファイルのエンコーディングを UTF-8 (BOM付き) に変更しました。

## [0.2.3] - Sat Feb 28 11:38:45 JST 2026
### Fixed
- `acvs_gui.ps1`: Pythonプロセス実行中にGUIが応答なし（フリーズ）になる問題を修正。非同期待ちループとUI状態制御を導入しました。

## [0.2.2] - Sat Feb 28 11:33:36 JST 2026
### Changed
- GitHubリポジトリからの同期（クローン）を完了
- `acvs_core.py` および `acvs_gui.ps1` にバージョン情報と最終更新日時のヘッダーを追加

## [0.2.1] - Fri Feb 27 20:34:25 JST 2026
### Added
- Phase 4: マニフェストファイル (`.cut_manifest.json`) にバージョン情報を含むメタデータ (`_meta`) セクションを追加
- 外部連携用にJSONのデータ構造を定義した仕様書 `MANIFEST_SPEC.md` を作成

## [0.2.0] - Fri Feb 27 18:31:39 JST 2026
### Added
- Phase 3: GUIツールとバージョン履歴管理機能の実装
  - `acvs_gui.ps1`: Windows標準のPowerShellで動作する使いやすいGUI（エピソードルート指定＋カット検索機能付き）を追加。
  -履歴管理 `log` コマンド: `commit` 時に `.acvs_history/` へ過去のJSONを保存。変更がない場合（Smart Archive）は一時保存のみで次回の変更時に破棄・整理される機能を追加。
  -履歴差分 `diff` コマンド: 指定した過去のタイムスタンプと現在の状態を比較できる機能を追加。

## [0.1.0] - Fri Feb 27 17:10:21 JST 2026
### Added
- Phase 2: 連番画像のハッシュ最適化処理機能を追加 (Fri Feb 27 16:22:26 JST 2026)
  - `acvs_core.py`: `status` と `scan` に `--seq` オプションを追加。連番ファイルを自動グループ化して軽量化（`seq_name_[0001-1000].ext` 形式）。
  - `test_seq_generator.py`: ベンチマーク・テスト用のダミー連番画像生成スクリプト。
- 初期プロジェクト構造の作成 (Fri Feb 27 15:47:36 JST 2026)
  - `acvs_core.py`: ハッシュ計算、ディレクトリ走査、状態比較のプロトタイプ実装。
  - `.gitignore`: アニメーション素材用の除外設定を追加。
