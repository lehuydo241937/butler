import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

file_path = r"d:\Agent AI\butler\backup_zalo_02_03_2026.zl.zip"
eocd_sig = b"PK\x05\x06"

try:
    with open(file_path, "rb") as f:
        f.seek(0, 2) # Go to end
        size = f.tell()
        if size > 1024:
            f.seek(-1024, 2)
            data = f.read()
            pos = data.find(eocd_sig)
            if pos != -1:
                print(f"EOCD signature found at offset from end: {len(data) - pos}")
            else:
                print("EOCD signature NOT found in last 1KB.")
        else:
            print("File too small to check end.")
except Exception as e:
    print(f"Error: {e}")
