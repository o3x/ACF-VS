# Changelog

すべての顕著な変更はこのファイルに記録されます。

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
