import os
import argparse

def generate_sequence(target_dir, prefix, start, end, ext, zero_pad=4, content="dummy"):
    """指定されたディレクトリに連番ファイルを生成する"""
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    count = 0
    for i in range(start, end + 1):
        # 0埋めフォーマット
        padded_num = str(i).zfill(zero_pad)
        filename = f"{prefix}_{padded_num}.{ext}"
        filepath = os.path.join(target_dir, filename)
        
        # 中抜けのシミュレーション（意図的に一部をスキップする場合などに拡張可能）
        # if i == start + 5: continue
        
        with open(filepath, 'w') as f:
            # 擬似的なバイナリを模すため、インデックス番号などを含める
            f.write(f"{content}_{i}")
        count += 1
        
    print(f"Generated {count} files in {target_dir}")
    print(f"Example: {prefix}_{str(start).zfill(zero_pad)}.{ext} to {prefix}_{str(end).zfill(zero_pad)}.{ext}")

def main():
    parser = argparse.ArgumentParser(description="ACF-VS Test Sequence Generator")
    parser.add_argument('--dir', default='./test_env', help='Target root directory')
    parser.add_argument('--count', type=int, default=1000, help='Number of sequence files to generate per folder')
    
    args = parser.parse_args()
    
    base_dir = os.path.abspath(args.dir)
    
    # テスト用のフォルダ構成
    cell_dir = os.path.join(base_dir, 'CELL', 'A_cell')
    bg_dir = os.path.join(base_dir, 'BG', 'A_bg')
    
    # 正常な連番の生成 (1000枚)
    generate_sequence(cell_dir, 'A_cell', 1, args.count, 'tga')
    
    # 中抜けや拡張子違いなどの複雑なケース用 (オプション)
    generate_sequence(bg_dir, 'bg_anim', 1, 50, 'png')

if __name__ == "__main__":
    main()
