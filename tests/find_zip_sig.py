import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

file_path = r"d:\Agent AI\butler\backup_zalo_02_03_2026.zl.zip"
zip_sig = b"PK\x03\x04"

try:
    with open(file_path, "rb") as f:
        data = f.read(1024 * 1024) # Read first 1MB
        pos = data.find(zip_sig)
        if pos != -1:
            print(f"ZIP signature found at offset: {pos}")
            # print(f"Header before ZIP: {data[:pos].hex(' ')}")
        else:
            print("ZIP signature NOT found in first 1MB.")
except Exception as e:
    print(f"Error: {e}")
