# ACF-VS Manifest Format Specification (v1.0)

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
このファイルを生成したシステムの情報とスキーマバージョンが格納されます。

*   **`generator`** (String): 常に `"ACF-VS"` となります。ファイルがACF-VSによって生成されたことを示すタグです。
*   **`schema_version`** (String): このJSONの構造バージョンです。現在は `"1.0"` です。
*   **`updated_at`** (String): ファイルが生成（commit）された日時です。フォーマットは `YYYYMMDD_HHMMSS` (例: `"20260227_182939"`) となります。
*   *(履歴バックアップファイルの場合のみ)* `has_changes` (Boolean): 前回の状態から差分があったかどうか。
*   *(履歴バックアップファイルの場合のみ)* `fast_mode` (Boolean): 高速モードでスキャンされたかどうか。
*   *(履歴バックアップファイルの場合のみ)* `seq_grouped` (Boolean): 連番最適化モードでスキャンされたかどうか。

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

## 2. アイテムプロパティ (Item Properties)

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
