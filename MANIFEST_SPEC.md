# ACF-VS Manifest Format Specification (v1.0.1)

ACF-VS (Anime Cut Folder Versioning System) が出力する JSON マニフェストファイル（`.cut_manifest.json` および `.acvs_history/` 内の履歴ファイル）のデータ構造仕様です。

サードパーティ・スクリプト（AfterEffectsの JSX や各種DCCツールのプラグイン等）からカットの素材状態を読み取る際のリファレンスとして使用してください。

## 1. ルート構造 (Root Structure)

JSON ファイルのルートレベルは以下の2つのオブジェクトを持ちます。

```json
{
  "_meta": { ... },
  "state": { ... }
}
```

### 1-A. `_meta` (Metadata Object)
このファイルを生成したシステムの情報とスキーマバージョンが格納されます。`.cut_manifest.json` と `.acvs_history/` 内のファイルの両方に共通して付与されます。

*   **`generator`** (String): 常に `"ACF-VS"` となります。ファイルがACF-VSによって生成されたことを示すタグです。
*   **`schema_version`** (String): このJSONの構造バージョンです（例: `"1.0.1"`）。
*   **`updated_at`** (String): *(マニフェストのみ)* ファイルが生成された日時です。フォーマットは `YYYYMMDD_HHMMSS` となります。
*   **`timestamp`** (String): *(履歴バックアップファイルのみ)* 保存された日時です。フォーマットは `YYYYMMDD_HHMMSS` となります。
*   **`has_changes`** (Boolean): *(履歴バックアップファイルのみ)* 前回の状態から差分があったかどうか。
*   **`fast_mode`** (Boolean): *(履歴バックアップファイルのみ)* 高速モードでスキャンされたかどうか。
*   **`seq_grouped`** (Boolean): *(履歴バックアップファイルのみ)* 連番最適化モードでスキャンされたかどうか。

### 1-B. `state` (State Object)
カットディレクトリ内の全ファイル（および連番グループ）の状態を保持する連想配列です。
キーは「ターゲットディレクトリからの相対パス（`/` 区切り）」、値は各アイテムのプロパティオブジェクトとなります。

```json
"state": {
  "BG/bg_001.psd": { ... },
  "CELL/A_cell/A_cell_[0001-1000].tga": { ... }
}
```

---

## 2. スキーマのバージョニングポリシー

ACF-VSのJSONデータ構造は、セマンティックバージョニング（`Major.Minor.Revision`、現在は実質 `Major.Minor.Patch` 形式として解釈可能）に基づいて管理されます。サードパーティ製ツール等でJSONを読み込む際は、この `schema_version` の値を確認して互換性を維持してください。

*   **Minor / Revision バージョンアップ (例: `1.0` -> `1.0.1` または `1.1`)**:
    *   後方互換性 **あり**。
    *   新しいフィールドの追加など、既存のパーサーが未知のフィールドを無視すればそのまま読み込めるレベルの変更。
*   **Major バージョンアップ (例: `1.0.x` -> `2.0.0`)**:
    *   後方互換性 **なし** (破壊的変更)。
    *   既存のフィールド名の変更、`state` 構造の抜本的な変更など、古いパーサーではエラーになるか正しく解釈できなくなるレベルの変更。読み込み側でマイグレーション（コンバート）処理等が必要になります。

---

## 3. スナップショットアーキテクチャについて

ACF-VSは、最新状態を示す `.cut_manifest.json` だけでなく、過去の履歴として保存される `.acvs_history/*.json` の**両方に、そのディレクトリ内の全ファイル状態（フルJSON）を記録**しています。

これはGitのコアオブジェクトと同じ「スナップショット（Snapshot）」アーキテクチャを採用しているためです。「前回の履歴からの差分（Delta）」だけを記録する方式に比べ、以下の利点があります。

1.  **堅牢性の高さ**: 過去の履歴ファイルが1つ破損したり削除されたりしても、他の履歴データは完全に独立しているため影響を受けません。
2.  **比較処理の高速化**: 任意の過去（例: 3日前の履歴）と現在を比較する場合、遡って差分を計算し直す必要がなく、単に「3日前のフルJSON」と「現在のフルJSON」の2つを比較するだけで高速に差分を抽出できます。

ファイルは全てテキスト（JSON）形式であり、容量も軽微であるため、このスナップショット方式によって安全かつ高速なバージョン管理を実現しています。

---

## 4. アイテムプロパティ (Item Properties)

各キー（相対パス）に紐づく値は、ファイルまたは連番画像のグループ（シーケンス）によって内容が変化します。

### 2-A. 通常のファイル (File Item)
単体のファイル（`.psd`, `.png`, スクリプトなど）に関するプロパティです。

```json
"BG/bg_001.psd": {
  "type": "file",
  "hash": "8ae4...",
  "size": 1048576,
  "mtime": 1709025000.5,
  "is_archived": false
}
```
*   **`type`** (String): `"file"`
*   **`hash`** (String): 
    *   通常のSHA-256ハッシュのフルストリング（例: `e3b0c442...`）
    *   または `fast_mode` 実行時の疑似ハッシュ (`"fast:<size>:<mtime>"`)
*   **`size`** (Integer): ファイルサイズ（バイト）
*   **`mtime`** (Float): 最終更新日時（UNIXタイムスタンプ）
*   **`is_archived`** (Boolean): パスの中に `(old)` というフォルダ名が含まれている場合は `true` となります。

### 2-B. 連番グループ (Sequence Item)
`--seq` オプションによって自動グループ化された、3ファイル以上連続する連番画像のプロパティです。

サードパーティツールから読み取る場合、キー名のパターン `_[0001-1000].ext` を正規表現でパースして開始・終了フレーム番号を推測することが可能です。

```json
"CELL/A_cell/A_cell_[0001-1000].tga": {
  "type": "sequence",
  "hash": "seq:fast:4194304:1709025000.5:1000",
  "size": 4194304000,
  "mtime": 1709026000.0,
  "is_archived": false,
  "count": 1000
}
```
*   **`type`** (String): `"sequence"`
*   **`hash`** (String): 連番代表ハッシュ (`"seq:<先頭フレームのfast_hash>:<枚数>"`)
*   **`size`** (Integer): グループ内の全ファイルの合計サイズ（バイト）
*   **`mtime`** (Float): グループの中で一番最後に更新されたファイルの更新日時（UNIXタイムスタンプ）
*   **`is_archived`** (Boolean): パスの中に `(old)` が含まれている場合は `true`。
*   **`count`** (Integer): グループに含まれる画像ファイルの枚数。

---

## 3. パーサーの実装例 (AfterEffects / ExtendScript_JSX)

ACF-VS のJSONをAdobe系のスクリプト等で読み取る場合の擬似コード例です。

```javascript
// ExtendScript (JSX) Example
var jsonFile = new File(Folder.current.fsName + "/.cut_manifest.json");
if(jsonFile.exists) {
    jsonFile.open('r');
    var rawString = jsonFile.read();
    jsonFile.close();
    
    // JSONのパース (json2.js等のポリフィルが必要)
    var manifest = JSON.parse(rawString);
    
    // スキーマバージョンの確認
    if(manifest._meta && manifest._meta.generator === "ACF-VS") {
        var state = manifest.state;
        for (var pathKey in state) {
            var item = state[pathKey];
            if(item.is_archived) {
                // (old) フォルダに入っているファイルへの警告処理など
            }
        }
    }
}
```
