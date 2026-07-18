import struct
import sys
from pathlib import Path
from typing import Optional

def proc_dec(buf_base: bytes, buf_now: bytes) -> Optional[bytes]:
    """
    实现与C#完全相同的 proc_dec 解码算法
    """
    i = 0
    # 跳过基础文件名 (null-terminated)
    while i < len(buf_now) and buf_now[i] != 0:
        i += 1
    i += 1
    
    # 读取解码后的大小 (小端序)
    if i + 4 > len(buf_now):
        print("Error: Invalid .co file format")
        return None
    
    # 小端序读取
    decoded_size = struct.unpack_from('<I', buf_now, i)[0]
    i += 4
    
    print(f"  Decoded size from file: {decoded_size}")
    
    # 创建结果数组
    result = bytearray(decoded_size)
    result_pos = 0  # num
    base_pos = 0    # num2
    
    while i < len(buf_now):
        b = buf_now[i]
        i += 1
        
        if b & 0x80:  # 直接复制
            length = b & 0x7F
            if i + length <= len(buf_now) and result_pos + length <= decoded_size:
                result[result_pos:result_pos + length] = buf_now[i:i + length]
                i += length
                result_pos += length
                base_pos += length
            else:
                print(f"Error: Direct copy overflow at position {i}")
                return None
                
        elif b == 0:  # 跳过数据
            if i >= len(buf_now):
                print("Error: Unexpected end of data")
                return None
            skip = buf_now[i]
            i += 1
            skip &= 0xFF
            if skip & 0x80:
                skip &= 0x7F
                skip -= 128
            base_pos += skip
            
        elif b == 1:  # 从基础文件复制 (1字节长度)
            if i >= len(buf_now):
                print("Error: Unexpected end of data")
                return None
            length = buf_now[i]
            i += 1
            # 检查边界
            if base_pos + length > len(buf_base):
                print(f"Error: Base overflow at position {i}")
                print(f"  base_pos={base_pos}, length={length}, base_len={len(buf_base)}")
                # 截断到base末尾
                length = len(buf_base) - base_pos
            if result_pos + length > decoded_size:
                print(f"Error: Result overflow at position {i}")
                print(f"  result_pos={result_pos}, length={length}, decoded_size={decoded_size}")
                length = decoded_size - result_pos
            if length > 0:
                result[result_pos:result_pos + length] = buf_base[base_pos:base_pos + length]
                base_pos += length
                result_pos += length
                
        elif b == 2:  # 从基础文件复制 (2字节长度) - 大端序
            if i + 1 >= len(buf_now):
                print("Error: Unexpected end of data")
                return None
            length = (buf_now[i] << 8) | buf_now[i + 1]
            i += 2
            if base_pos + length > len(buf_base):
                print(f"Error: Base overflow at position {i}")
                print(f"  base_pos={base_pos}, length={length}, base_len={len(buf_base)}")
                length = len(buf_base) - base_pos
            if result_pos + length > decoded_size:
                print(f"Error: Result overflow at position {i}")
                print(f"  result_pos={result_pos}, length={length}, decoded_size={decoded_size}")
                length = decoded_size - result_pos
            if length > 0:
                result[result_pos:result_pos + length] = buf_base[base_pos:base_pos + length]
                base_pos += length
                result_pos += length
                
        elif b == 3:  # 从基础文件复制 (4字节长度) - 大端序
            if i + 3 >= len(buf_now):
                print("Error: Unexpected end of data")
                return None
            length = 0
            for _ in range(4):
                length = (length << 8) | buf_now[i]
                i += 1
            if base_pos + length > len(buf_base):
                print(f"Error: Base overflow at position {i}")
                print(f"  base_pos={base_pos}, length={length}, base_len={len(buf_base)}")
                length = len(buf_base) - base_pos
            if result_pos + length > decoded_size:
                print(f"Error: Result overflow at position {i}")
                print(f"  result_pos={result_pos}, length={length}, decoded_size={decoded_size}")
                length = decoded_size - result_pos
            if length > 0:
                result[result_pos:result_pos + length] = buf_base[base_pos:base_pos + length]
                base_pos += length
                result_pos += length
        else:
            print(f"Error: Unknown command 0x{b:02X} at position {i-1}")
            return None
    
    # 只返回实际写入的部分
    result = result[:result_pos]
    print(f"  Actual decoded size: {result_pos}")
    print(f"  Decoded size from file: {decoded_size}")
    
    return bytes(result)


def decode_co_file(co_path: str, output_dir: str) -> bool:
    """解码单个 .co.bytes 文件"""
    co_path = Path(co_path)
    base_dir = co_path.parent
    
    # 读取.co文件
    with open(co_path, 'rb') as f:
        buf_now = f.read()
    
    # 提取基础文件名
    pos = 0
    base_name = ""
    while pos < len(buf_now) and buf_now[pos] != 0:
        base_name += chr(buf_now[pos])
        pos += 1
    
    if not base_name:
        print(f"Error: Invalid .co file: {co_path}")
        return False
    
    # 查找基础文件 (.un.bytes)
    base_path = base_dir / base_name
    if not base_path.exists():
        print(f"Error: Base file not found: {base_path}")
        return False
    
    # 读取基础文件
    with open(base_path, 'rb') as f:
        buf_base = f.read()
    
    print(f"  Base: {base_name} ({len(buf_base)} bytes)")
    print(f"  CO: {co_path.name} ({len(buf_now)} bytes)")
    
    # 解码
    decoded = proc_dec(buf_base, buf_now)
    if decoded is None:
        return False
    
    # 保存解码后的文件
    output_path = Path(output_dir) / f"{co_path.stem}.decoded"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(decoded)
    
    print(f"  Saved: {output_path.name} ({len(decoded)} bytes)")
    return True


def batch_decode_co_files(input_dir: str, output_dir: str):
    """批量解码所有 .co.bytes 文件"""
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"Error: Directory not found: {input_path}")
        return
    
    co_files = list(input_path.rglob('*.co.bytes'))
    
    if not co_files:
        print(f"No .co.bytes files found in: {input_path}")
        return
    
    print(f"Found {len(co_files)} .co.bytes files\n")
    
    success_count = 0
    for co_file in co_files:
        rel_path = co_file.relative_to(input_path)
        print(f"Processing: {rel_path}")
        try:
            if decode_co_file(str(co_file), output_dir):
                success_count += 1
        except Exception as e:
            print(f"  Error: {e}")
        print()
    
    print(f"Successfully decoded {success_count}/{len(co_files)} files")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python proc_dec.py <input_dir> <output_dir>")
        print("  python proc_dec.py <co_file> <output_dir>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    output_dir = sys.argv[2]
    
    if not input_path.exists():
        print(f"Error: Input not found: {input_path}")
        sys.exit(1)
    
    if input_path.is_file() and input_path.suffix == '.bytes':
        decode_co_file(str(input_path), output_dir)
    elif input_path.is_dir():
        batch_decode_co_files(str(input_path), output_dir)
    else:
        print(f"Error: Unknown input type: {input_path}")
