import os
import hashlib
import json
import argparse
import time
import re
from datetime import datetime

class ACVSCore:
    def __init__(self, target_dir):
        self.target_dir = os.path.abspath(target_dir)
        self.manifest_path = os.path.join(self.target_dir, '.cut_manifest.json')

    def calculate_hash(self, file_path, fast_mode=False):
        """ファイルのSHA-256ハッシュを計算する。速さ優先のfast_modeもサポート。"""
        if fast_mode:
            try:
                stat = os.stat(file_path)
                return f"fast:{stat.st_size}:{stat.st_mtime}"
            except OSError:
                return None
        
        hasher = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096 * 1024), b""): # 4MB chunks
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    def scan_directory(self, fast_mode=False, group_seq=False):
        """ディレクトリ以下を再帰的に走査し、現在の状態を取得する。"""
        state = {}
        seq_groups = {} # src_dir -> { prefix: { ext: [files...] } }
        
        # 正規表現：プレフィックス _ 数字(1桁以上) . 拡張子
        seq_pattern = re.compile(r'^(.*?)_([0-9]+)\.([a-zA-Z0-9]+)$')

        for root, dirs, files in os.walk(self.target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.target_dir)
                
                if rel_path.startswith('.cut_manifest') or rel_path == '.gitignore' or file == 'acvs_core.py' or file == 'test_seq_generator.py':
                    continue
                
                rel_path = rel_path.replace('\\', '/')
                
                if group_seq:
                    match = seq_pattern.match(file)
                    if match:
                        prefix, num_str, ext = match.groups()
                        # 親ディレクトリの相対パス
                        parent_rel_path = os.path.dirname(rel_path)
                        
                        seq_groups.setdefault(parent_rel_path, {}).setdefault(prefix, {}).setdefault(ext, []).append({
                            'filename': file,
                            'path': file_path,
                            'rel_path': rel_path,
                            'num': int(num_str),
                            'num_str': num_str
                        })
                        continue # 連番ファイルは個別のファイルとしては state に追加しない

                file_hash = self.calculate_hash(file_path, fast_mode=fast_mode)
                if not file_hash:
                    continue
                
                stat = os.stat(file_path)
                state[rel_path] = {
                    "hash": file_hash,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "is_archived": "(old)" in rel_path.lower(),
                    "type": "file"
                }

        # 連番グループの処理
        if group_seq:
            for parent_dir, prefixes in seq_groups.items():
                for prefix, exts in prefixes.items():
                    for ext, items in exts.items():
                        # グループ構成の閾値 (例: 3枚以上なら連番とみなす)
                        if len(items) >= 3:
                            items.sort(key=lambda x: x['num'])
                            first_item = items[0]
                            last_item = items[-1]
                            
                            num_format_len = len(first_item['num_str'])
                            seq_name = f"{parent_dir}/{prefix}_[{str(first_item['num']).zfill(num_format_len)}-{str(last_item['num']).zfill(num_format_len)}].{ext}"
                            
                            # 代表ハッシュの計算 (先頭のファイルの fast_mode + 枚数)
                            head_hash = self.calculate_hash(first_item['path'], fast_mode=True)
                            group_hash = f"seq:{head_hash}:{len(items)}"
                            
                            state[seq_name] = {
                                "hash": group_hash,
                                "mtime": os.stat(last_item['path']).st_mtime,
                                "size": sum(os.stat(i['path']).st_size for i in items),
                                "is_archived": "(old)" in seq_name.lower(),
                                "type": "sequence",
                                "count": len(items)
                            }
                        else:
                            # 3枚未満なら通常のファイルとして扱う
                            for item in items:
                                file_hash = self.calculate_hash(item['path'], fast_mode=fast_mode)
                                if file_hash:
                                    stat = os.stat(item['path'])
                                    state[item['rel_path']] = {
                                        "hash": file_hash,
                                        "mtime": stat.st_mtime,
                                        "size": stat.st_size,
                                        "is_archived": "(old)" in item['rel_path'].lower(),
                                        "type": "file"
                                    }
                            
        return state

    def compare_states(self, old_state, new_state):
        """古い状態と新しい状態を比較し、差分を判定する。"""
        changes = {
            "new": [],
            "updated": [],
            "deleted": [],
            "moved_to_archive": [], # Activeから(old)への移動
            "moved": [],            # その他の移動
            "redundant_copies": []  # 警告用：ハッシュが同じファイルが複数存在
        }
        
        # 移動検出のための古い状態のハッシュインデックス
        old_hashes = {}
        for path, info in old_state.items():
            h = info["hash"]
            if h not in old_hashes:
                old_hashes[h] = []
            old_hashes[h].append(path)
            
        # 重複チェック用
        new_hashes = {}
        for path, info in new_state.items():
            h = info["hash"]
            if h not in new_hashes:
                new_hashes[h] = []
            new_hashes[h].append(path)
            
        # 重複警告（同じファイルが複数ある場合）
        for h, paths in new_hashes.items():
            if len(paths) > 1:
                changes["redundant_copies"].append(paths)

        processed_old_paths = set()

        # 新規・更新・移動の判定
        for path, info in new_state.items():
            if path not in old_state:
                # 移動したかどうかのチェック
                h = info["hash"]
                if h in old_hashes:
                    # 同じハッシュを持つ古いファイルを探す
                    moved_from = None
                    for op in old_hashes[h]:
                        if op not in new_state and op not in processed_old_paths:
                            moved_from = op
                            break
                    
                    if moved_from:
                        processed_old_paths.add(moved_from)
                        if not old_state[moved_from]['is_archived'] and info['is_archived']:
                            changes["moved_to_archive"].append({"from": moved_from, "to": path})
                        else:
                            changes["moved"].append({"from": moved_from, "to": path})
                    else:
                        changes["new"].append(path)
                else:
                    changes["new"].append(path)
            else:
                # パスが同じ場合
                if old_state[path]["hash"] != info["hash"]:
                    changes["updated"].append(path)
                processed_old_paths.add(path)
                    
        # 削除の判定
        for path, info in old_state.items():
            if path not in processed_old_paths:
                changes["deleted"].append(path)
                
        return changes

    def load_manifest(self):
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_manifest(self, state):
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)

    def init(self):
        if os.path.exists(self.manifest_path):
            print("Already initialized.")
            return False
        state = self.scan_directory()
        self.save_manifest(state)
        print(f"Initialized manifest with {len(state)} files.")
        return True

    def scan(self, fast_mode=False, group_seq=False):
        old_state = self.load_manifest()
        new_state = self.scan_directory(fast_mode=fast_mode, group_seq=group_seq)
        changes = self.compare_states(old_state, new_state)
        return changes, new_state

    def status(self, fast_mode=False, group_seq=False):
        if not os.path.exists(self.manifest_path):
            print("Fatal: Not an ACVS directory (or any of the parent directories): .cut_manifest.json not found")
            return
            
        changes, _ = self.scan(fast_mode=fast_mode, group_seq=group_seq)
        
        has_changes = False
        
        if changes["new"]:
            has_changes = True
            print("New files:")
            for p in changes["new"]:
                print(f"  [NEW] {p}")
                
        if changes["updated"]:
            has_changes = True
            print("\nUpdated files:")
            for p in changes["updated"]:
                print(f"  [UPDATED] {p}")
                
        if changes["moved"]:
            has_changes = True
            print("\nMoved files:")
            for m in changes["moved"]:
                print(f"  [MOVED] {m['from']} -> {m['to']}")
                
        if changes["moved_to_archive"]:
            has_changes = True
            print("\nArchived files:")
            for m in changes["moved_to_archive"]:
                print(f"  [ARCHIVED (old)] {m['from']} -> {m['to']}")
                
        if changes["deleted"]:
            has_changes = True
            print("\nDeleted files:")
            for p in changes["deleted"]:
                print(f"  [DELETED] {p}")
                
        if changes["redundant_copies"]:
            print("\nWarning: Redundant copies detected:")
            for copies in changes["redundant_copies"]:
                print(f"  [DUPLICATE] Identical files: {', '.join(copies)}")
                
        if not has_changes:
            print("Nothing to commit, working tree clean")

    def commit(self, fast_mode=False, group_seq=False):
        if not os.path.exists(self.manifest_path):
            print("Fatal: Not an ACVS directory (or any of the parent directories): .cut_manifest.json not found")
            return
            
        _, new_state = self.scan(fast_mode=fast_mode, group_seq=group_seq)
        self.save_manifest(new_state)
        print("Manifest updated successfully.")

def main():
    parser = argparse.ArgumentParser(description="ACF-VS (Anime Cut Folder Versioning System)")
    parser.add_argument('command', choices=['init', 'scan', 'status', 'commit', 'verify'], help='Command to execute')
    parser.add_argument('--dir', default='.', help='Target directory (default: current directory)')
    parser.add_argument('--fast', action='store_true', help='Use fast mode (size+mtime instead of full hash)')
    parser.add_argument('--seq', action='store_true', help='Group sequence files (e.g. name_001.tga) into a single entry')
    
    args = parser.parse_args()
    
    acvs = ACVSCore(args.dir)
    
    if args.command == 'init':
        acvs.init()
    elif args.command == 'status':
        acvs.status(fast_mode=args.fast, group_seq=args.seq)
    elif args.command == 'scan':
        # Alias for status but can be used for dry-run inspection in scripts
        acvs.status(fast_mode=args.fast, group_seq=args.seq)
    elif args.command == 'commit':
        acvs.commit(fast_mode=args.fast, group_seq=args.seq)
    elif args.command == 'verify':
        # Same as status for now, visually verifies state
        acvs.status(fast_mode=args.fast, group_seq=args.seq)

if __name__ == "__main__":
    main()
