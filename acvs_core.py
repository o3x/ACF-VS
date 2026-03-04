# Version: 0.3.0
# Last Updated: Wed Mar 04 10:57:36 JST 2026

import os
import hashlib
import json
import argparse
import time
import re
import sys
import concurrent.futures
from datetime import datetime

class ACVSCore:
    def __init__(self, target_dir):
        self.target_dir = os.path.abspath(target_dir)
        self.manifest_path = os.path.join(self.target_dir, '.cut_manifest.json')
        self.history_dir = os.path.join(self.target_dir, '.acvs_history')

    def _ensure_history_dir(self):
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)

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
        files_to_process = []
        
        # 除外するディレクトリ名
        exclude_dirs = {'.git', '.acvs_history', '__pycache__', 'test_env'}
        
        # 正規表現：プレフィックス(任意の文字) + 数字(4桁以上) . 拡張子
        # _0001 だけでなく i0001 のようなアンダーバー無しも許容するが、テイク番号（t01など）と区別するため4桁以上とする
        seq_pattern = re.compile(r'^(.*?)([0-9]{4,})\.([a-zA-Z0-9]+)$')

        # 1. ファイル一覧の収集
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
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
                        parent_rel_path = os.path.dirname(rel_path)
                        seq_groups.setdefault(parent_rel_path, {}).setdefault(prefix, {}).setdefault(ext, []).append({
                            'filename': file, 'path': file_path, 'rel_path': rel_path, 'num': int(num_str), 'num_str': num_str
                        })
                        continue
                
                files_to_process.append((rel_path, file_path))

        # 2. ハッシュ計算（並列実行）
        total_files = len(files_to_process)
        def process_single_file(item):
            rel_path, file_path = item
            h = self.calculate_hash(file_path, fast_mode=fast_mode)
            if h:
                st = os.stat(file_path)
                return rel_path, {"hash": h, "mtime": st.st_mtime, "size": st.st_size, "is_archived": "(old)" in rel_path.lower(), "type": "file"}
            return None

        print(f"Scanning {total_files} files...")
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_single_file, f) for f in files_to_process]
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                result = future.result()
                if result:
                    path, info = result
                    state[path] = info
                # プログレス出力
                if (i + 1) % 10 == 0 or (i + 1) == total_files:
                    print(f"PROGRESS: {i+1}/{total_files}")

        # 3. 連番グループの処理
        if group_seq:
            for parent_dir, prefixes in seq_groups.items():
                for prefix, exts in prefixes.items():
                    for ext, items in exts.items():
                        # グループ構成の閾値を2枚以上に緩和
                        if len(items) >= 2:
                            items.sort(key=lambda x: x['num'])
                            first_item = items[0]
                            last_item = items[-1]
                            num_format_len = len(first_item['num_str'])
                            
                            clean_prefix = prefix[:-1] if prefix.endswith('_') else prefix
                            seq_base = f"{clean_prefix}_[{str(first_item['num']).zfill(num_format_len)}-{str(last_item['num']).zfill(num_format_len)}].{ext}"
                            seq_name = f"{parent_dir}/{seq_base}" if parent_dir else seq_base
                            
                            total_size = sum(os.stat(i['path']).st_size for i in items)
                            max_mtime = max(os.stat(i['path']).st_mtime for i in items)
                            group_hash = f"seq:{total_size}:{max_mtime}:{len(items)}"
                            state[seq_name] = {
                                "hash": group_hash, "mtime": max_mtime,
                                "size": total_size,
                                "is_archived": "(old)" in seq_name.lower(), "type": "sequence", "count": len(items)
                            }
                        else:
                            for item in items:
                                res = process_single_file((item['rel_path'], item['path']))
                                if res: state[res[0]] = res[1]
        return state
                            
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
        processed_new_paths = set()

        # Pass 1: 完全一致（パスもハッシュも同じ）のファイルを先に処理済みにする
        for path, info in new_state.items():
            if path in old_state and old_state[path]["hash"] == info["hash"]:
                processed_old_paths.add(path)
                processed_new_paths.add(path)

        # Pass 2: 移動の検出（パスは違うがハッシュが同じ）
        for path, info in new_state.items():
            if path in processed_new_paths:
                continue
                
            h = info["hash"]
            if h in old_hashes:
                # 同じハッシュを持つ古いファイルの中で、まだ処理されていないものを探す
                moved_from = None
                for op in old_hashes[h]:
                    if op not in processed_old_paths:
                        moved_from = op
                        break
                
                if moved_from:
                    processed_old_paths.add(moved_from)
                    processed_new_paths.add(path)
                    if not old_state[moved_from]['is_archived'] and info['is_archived']:
                        changes["moved_to_archive"].append({"from": moved_from, "to": path})
                    else:
                        changes["moved"].append({"from": moved_from, "to": path})

        # Pass 3: 新規・更新の判定
        for path, info in new_state.items():
            if path not in processed_new_paths:
                if path in old_state:
                    changes["updated"].append(path)
                    processed_old_paths.add(path)
                else:
                    changes["new"].append(path)
                    
        # Pass 4: 削除の判定
        for path in old_state:
            if path not in processed_old_paths:
                changes["deleted"].append(path)
                
        return changes

    def load_manifest(self):
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 新仕様（_meta入り）か、旧仕様（直下state）かを吸収する
                if "_meta" in data and "state" in data:
                    return data["state"]
                return data
        return {}

    def save_manifest(self, state):
        # キー（ファイルパス）でソートして保存
        sorted_state = {k: state[k] for k in sorted(state.keys())}
        
        # マニフェストファイルにもバージョン情報を付加する
        manifest_data = {
            "_meta": {
                "generator": "ACF-VS",
                "schema_version": "1.0.1",
                "updated_at": datetime.now().strftime("%Y%m%d_%H%M%S")
            },
            "state": sorted_state
        }
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=4, ensure_ascii=False)

    def init(self, fast_mode=False, group_seq=False):
        if os.path.exists(self.manifest_path):
            print("Already initialized.")
            return False
        state = self.scan_directory(fast_mode=fast_mode, group_seq=group_seq)
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
            
        old_state = self.load_manifest()
        changes, new_state = self.scan(fast_mode=fast_mode, group_seq=group_seq)
        
        has_changes = any(len(v) > 0 for k, v in changes.items() if k != "redundant_copies")
        
        if not has_changes:
            print("No changes detected since last commit. Commit skipped.")
            return
        
        self._ensure_history_dir()
        
        # 履歴の保存ロジック
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = os.path.join(self.history_dir, f"{timestamp}.json")
        
        # メタデータを付加して保存
        sorted_state = {k: new_state[k] for k in sorted(new_state.keys())}
        save_data = {
            "_meta": {
                "generator": "ACF-VS",
                "schema_version": "1.0.1",
                "timestamp": timestamp,
                "has_changes": True,
                "fast_mode": fast_mode,
                "seq_grouped": group_seq
            },
            "state": sorted_state
        }
        
        # 今回の状態を履歴としてバックアップ
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
            
        # 最新の .cut_manifest.json を上書き
        self.save_manifest(new_state)
        
        print(f"Manifest updated successfully. Backup saved to .acvs_history/{timestamp}.json")

    def log(self):
        """履歴(History)の一覧を表示する"""
        if not os.path.exists(self.history_dir):
            print("No history found.")
            return
            
        history_files = sorted([f for f in os.listdir(self.history_dir) if f.endswith('.json')], reverse=True)
        
        if not history_files:
            print("No history found.")
            return
            
        print("--- ACVS Local History ---")
        for hf in history_files:
            hp = os.path.join(self.history_dir, hf)
            try:
                with open(hp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("_meta", {})
                    ts = meta.get("timestamp", hf.replace('.json', ''))
                    # 日時フォーマットを読みやすく
                    readable_time = datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                    status = "Changed" if meta.get("has_changes", True) else "No changes (Checked)"
                    files_count = len(data.get("state", {}))
                    
                    print(f"[{ts}] {readable_time} | Status: {status} | Files: {files_count}")
            except Exception as e:
                print(f"Error reading {hf}: {e}")

    def diff(self, target1=None, target2=None, fast_mode=False, group_seq=False):
        """指定した過去の日時の状態と現在の状態、または2つの過去の状態を比較して差分を表示する"""
        if not os.path.exists(self.history_dir) or not os.listdir(self.history_dir):
            if not target1 and not target2:
                print("No history found. Comparing with the latest manifest instead (same as status).")
                self.status(fast_mode=fast_mode, group_seq=group_seq)
                return
            else:
                print("Fatal: No history directory found.")
                return

        def get_history_state(ts):
            target_file = os.path.join(self.history_dir, f"{ts}.json")
            if not os.path.exists(target_file):
                print(f"Fatal: History for '{ts}' not found.")
                return None
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    if "_meta" in history_data and "state" in history_data:
                        return history_data["state"]
                    return history_data
            except Exception as e:
                print(f"Error reading history file '{ts}': {e}")
                return None

        # Determine old_state and new_state
        if target1 and target2:
            # 2 targets: sort them so old is first
            t_list = sorted([target1, target2])
            older_ts = t_list[0]
            newer_ts = t_list[1]
            print(f"Comparing two historical states: {older_ts} (old) -> {newer_ts} (new) ...\n")
            old_state = get_history_state(older_ts)
            new_state = get_history_state(newer_ts)
            if old_state is None or new_state is None:
                return
        elif target1 and not target2:
            # 1 target: target1 vs current
            print(f"Comparing historical state: {target1} (old) -> Current State (new) ...\n")
            old_state = get_history_state(target1)
            if old_state is None:
                return
            new_state = self.scan_directory(fast_mode=fast_mode, group_seq=group_seq)
        else:
            # 0 targets: latest history vs current
            history_files = sorted([f for f in os.listdir(self.history_dir) if f.endswith('.json')], reverse=True)
            if not history_files:
                print("No history found. Comparing with the latest manifest instead (same as status).")
                self.status(fast_mode=fast_mode, group_seq=group_seq)
                return
            latest_ts = history_files[0].replace('.json', '')
            print(f"Comparing latest history: {latest_ts} (old) -> Current State (new) ...\n")
            old_state = get_history_state(latest_ts)
            if old_state is None:
                return
            new_state = self.scan_directory(fast_mode=fast_mode, group_seq=group_seq)

        # 比較
        changes = self.compare_states(old_state, new_state)
        
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
            print("\nWarning: Redundant copies detected in newer state:")
            for copies in changes["redundant_copies"]:
                print(f"  [DUPLICATE] Identical files: {', '.join(copies)}")
                
        if not has_changes:
            print("No changes compared to the specified state.")

def main():
    # 強制的に標準出力をUTF-8にして、PowerShell側での文字化け（Mojibake）を防ぐ
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass # Python 3.7 未満等の場合は無視

    parser = argparse.ArgumentParser(description="ACF-VS (Anime Cut Folder Versioning System)")
    parser.add_argument('command', choices=['init', 'scan', 'status', 'commit', 'verify', 'log', 'diff'], help='Command to execute')
    parser.add_argument('--dir', default='.', help='Target directory (default: current directory)')
    parser.add_argument('--fast', action='store_true', help='Use fast mode (size+mtime instead of full hash)')
    parser.add_argument('--seq', action='store_true', help='Group sequence files (e.g. name_001.tga) into a single entry')
    parser.add_argument('--target', nargs='*', help='Target timestamp(s) for diff command (0 to 2 targets)')
    
    args = parser.parse_args()
    
    acvs = ACVSCore(args.dir)
    
    if args.command == 'init':
        acvs.init(fast_mode=args.fast, group_seq=args.seq)
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
    elif args.command == 'log':
        acvs.log()
    elif args.command == 'diff':
        targets = args.target if args.target else []
        if len(targets) > 2:
            print("Error: Too many targets specified for diff. Maximum is 2.")
            acvs.log()
        else:
            t1 = targets[0] if len(targets) > 0 else None
            t2 = targets[1] if len(targets) > 1 else None
            acvs.diff(t1, t2, fast_mode=args.fast, group_seq=args.seq)

if __name__ == "__main__":
    main()
