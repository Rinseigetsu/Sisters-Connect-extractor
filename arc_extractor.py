import struct
import os
import zlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse

class ArcExtractor:
    """.arc 文件解包工具"""
    
    def __init__(self):
        self.file_map = {}
    
    def read_string(self, data: bytes, offset: int) -> Tuple[str, int]:
        """读取以null结尾的UTF-8字符串"""
        end = offset
        while end < len(data) and data[end] != 0:
            end += 1
        string = data[offset:end].decode('utf-8', errors='ignore')
        return string, end - offset + 1  # +1 for null terminator
    
    def parse_arc_header(self, data: bytes) -> Tuple[int, int, int]:
        """
        解析ARC文件头
        返回: (table_offset, table_size, file_count)
        """
        # 小端序解析
        table_offset = struct.unpack_from('<q', data, 0)[0]  # 8字节
        table_size = struct.unpack_from('<i', data, 8)[0]    # 4字节
        file_count = struct.unpack_from('<i', data, 12)[0]   # 4字节
        return table_offset, table_size, file_count
    
    def parse_file_table(self, data: bytes, table_offset: int, table_size: int) -> List[Dict]:
        """
        解析文件表
        返回: 文件信息列表
        """
        files = []
        pos = 0
        table_data = data[table_offset:table_offset + table_size]
        
        while pos < len(table_data):
            try:
                # 读取文件名
                filename, name_len = self.read_string(table_data, pos)
                pos += name_len
                
                # 检查是否还有足够数据
                if pos + 16 > len(table_data):  # 16 = 8+4+4
                    break
                
                # 读取文件信息
                file_offset = struct.unpack_from('<q', table_data, pos)[0]
                pos += 8
                uncomp_size = struct.unpack_from('<i', table_data, pos)[0]
                pos += 4
                comp_size = struct.unpack_from('<i', table_data, pos)[0]
                pos += 4
                
                files.append({
                    'name': filename,
                    'offset': file_offset,
                    'uncompressed_size': uncomp_size,
                    'compressed_size': comp_size,
                    'is_compressed': comp_size > 0
                })
                
            except Exception as e:
                print(f"Warning: Error parsing file entry at position {pos}: {e}")
                break
        
        return files
    
    def extract_file(self, data: bytes, file_info: Dict) -> bytes:
        """
        提取单个文件数据
        """
        start = file_info['offset']
        size = file_info['compressed_size'] if file_info['is_compressed'] else file_info['uncompressed_size']
        
        file_data = data[start:start + size]
        
        # 如果文件被压缩，使用LZ4解压
        if file_info['is_compressed']:
            try:
                file_data = self.decompress_lz4(file_data, file_info['uncompressed_size'])
            except Exception as e:
                print(f"Warning: Failed to decompress {file_info['name']}: {e}")
                # 返回原始压缩数据
                return file_data
        
        return file_data
    
    def decompress_lz4(self, data: bytes, uncompressed_size: int) -> bytes:
        """
        LZ4解压
        需要安装: pip install lz4
        """
        try:
            import lz4.block
            return lz4.block.decompress(data, uncompressed_size)
        except ImportError:
            # 如果没有lz4库，尝试使用python-lz4的另一种方式
            try:
                import lz4.frame
                # 有些实现使用frame格式
                return lz4.frame.decompress(data)
            except:
                print("Warning: lz4 library not found. Install with: pip install lz4")
                return data
    
    def decompress_zlib(self, data: bytes) -> bytes:
        """
        Zlib解压 (备用)
        """
        try:
            # 跳过头部2字节，去掉尾部4字节校验和
            return zlib.decompress(data[2:-4])
        except:
            return zlib.decompress(data)
    
    def extract_arc(self, arc_path: str, output_dir: str, overwrite: bool = False):
        """
        提取整个ARC文件
        """
        print(f"Processing: {arc_path}")
        
        # 读取文件
        with open(arc_path, 'rb') as f:
            data = f.read()
        
        # 解析头
        table_offset, table_size, file_count = self.parse_arc_header(data)
        print(f"  File count: {file_count}")
        print(f"  Table offset: {table_offset}, Table size: {table_size}")
        
        # 解析文件表
        files = self.parse_file_table(data, table_offset, table_size)
        print(f"  Found {len(files)} files")
        
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 提取文件
        success_count = 0
        for file_info in files:
            try:
                file_data = self.extract_file(data, file_info)
                
                # 创建子目录结构
                file_path = output_path / file_info['name']
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 检查是否已存在
                if file_path.exists() and not overwrite:
                    print(f"  Skipping existing: {file_info['name']}")
                    continue
                
                # 保存文件
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                
                status = "compressed" if file_info['is_compressed'] else "uncompressed"
                print(f"  Extracted: {file_info['name']} ({len(file_data)} bytes, {status})")
                success_count += 1
                
            except Exception as e:
                print(f"  Error extracting {file_info['name']}: {e}")
        
        print(f"Successfully extracted {success_count}/{len(files)} files")
        return success_count


class CGExtractor(ArcExtractor):
    """专门用于提取CG资源的工具"""
    
    def extract_cg_files(self, arc_dir: str, output_dir: str):
        """
        提取所有CG相关的arc文件
        """
        arc_files = [
            "data_cgs_realn.arc",
            "data_cgs_real.arc",
            "data_cgs.arc",
            "data_stn.arc",
            "data_st.arc",
            "data_game_sc_standn.arc",
            "data_game_sc_stand.arc"
        ]
        
        arc_dir_path = Path(arc_dir)
        cg_output = Path(output_dir) / "cg_files"
        cg_output.mkdir(parents=True, exist_ok=True)
        
        all_extracted = 0
        
        for arc_name in arc_files:
            # 检查多个可能的路径
            possible_paths = [
                arc_dir_path / "n" / arc_name,
                arc_dir_path / "patch" / arc_name,
                arc_dir_path / arc_name
            ]
            
            for arc_path in possible_paths:
                if arc_path.exists():
                    print(f"\nFound CG archive: {arc_path}")
                    count = self.extract_arc(str(arc_path), str(cg_output / arc_path.stem), overwrite=True)
                    all_extracted += count
        
        print(f"\nTotal CG files extracted: {all_extracted}")
        return all_extracted


def decode_co_file(co_path: str, output_dir: str):
    """
    解码 .co.bytes 文件
    这是实验性的，需要完整的解码器实现
    """
    print(f"Decoding: {co_path}")
    
    with open(co_path, 'rb') as f:
        data = f.read()
    
    # 读取基础文件名
    pos = 0
    base_name = ""
    while pos < len(data) and data[pos] != 0:
        base_name += chr(data[pos])
        pos += 1
    pos += 1  # 跳过null
    
    # 读取解码后大小
    if pos + 4 > len(data):
        print(f"  Error: Invalid .co file format")
        return
    
    decoded_size = struct.unpack_from('<i', data, pos)[0]
    pos += 4
    
    print(f"  Base file: {base_name}")
    print(f"  Decoded size: {decoded_size}")
    
    # 查找基础文件
    base_path = Path(co_path).parent / base_name
    if base_path.exists():
        print(f"  Found base file: {base_path}")
        # 这里需要实现 proc_dec 解码算法
        # 目前只保存原始数据
        output_path = Path(output_dir) / f"{Path(co_path).stem}.decoded"
        with open(output_path, 'wb') as f:
            f.write(data)
        print(f"  Saved raw data to: {output_path}")
    else:
        print(f"  Warning: Base file not found: {base_name}")


def main():
    parser = argparse.ArgumentParser(description='ARC File Extractor')
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument('-o', '--output', default='extracted', help='Output directory')
    parser.add_argument('--cg', action='store_true', help='Extract CG files only')
    parser.add_argument('--decode-co', action='store_true', help='Try to decode .co.bytes files')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing files')
    parser.add_argument('--recursive', action='store_true', help='Process directory recursively')
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if args.cg:
        # CG模式 - 查找所有CG相关的arc文件
        extractor = CGExtractor()
        if input_path.is_dir():
            extractor.extract_cg_files(str(input_path), str(output_path))
        else:
            print("Error: --cg mode requires a directory input")
        return
    
    if args.decode_co:
        # 解码.co文件
        if input_path.is_file() and input_path.suffix == '.bytes':
            decode_co_file(str(input_path), str(output_path))
        else:
            print("Error: --decode-co requires a .co.bytes file")
        return
    
    # 普通模式 - 处理单个ARC文件或目录
    extractor = ArcExtractor()
    
    if input_path.is_file():
        # 处理单个文件
        if input_path.suffix == '.arc':
            extractor.extract_arc(str(input_path), str(output_path), args.overwrite)
        else:
            print(f"Error: {input_path} is not a .arc file")
    elif input_path.is_dir() and args.recursive:
        # 递归处理目录
        for arc_file in input_path.rglob('*.arc'):
            rel_path = arc_file.relative_to(input_path)
            out_dir = output_path / rel_path.parent / arc_file.stem
            extractor.extract_arc(str(arc_file), str(out_dir), args.overwrite)
    else:
        print(f"Usage: python arc_extractor.py <file.arc|directory> [options]")
        print("  --cg: Extract CG files only")
        print("  --decode-co: Decode .co.bytes file")
        print("  --overwrite: Overwrite existing files")
        print("  --recursive: Process directory recursively")


if __name__ == "__main__":
    main()
