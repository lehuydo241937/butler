import os

file_path = r"d:\Agent AI\butler\backup_zalo_02_03_2026.zl.zip"
try:
    with open(file_path, "rb") as f:
        header = f.read(16)
        print(f"Header (hex): {header.hex(' ')}")
        print(f"Header (text): {repr(header)}")
        
        # Check common magic numbers
        if header.startswith(b"PK\x03\x04"):
            print("Detected: ZIP file")
        elif header.startswith(b"7z\xbc\xaf\x27\x1c"):
            print("Detected: 7z archive")
        elif header.startswith(b"Rar!"):
            print("Detected: RAR archive")
        elif header.startswith(b"SQLite format 3"):
            print("Detected: SQLite database (Zalo backup often uses .zl for SQLite)")
        else:
            print("Detected: Unknown format")
except Exception as e:
    print(f"Error: {e}")
