import string
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

file_path = r"d:\Agent AI\butler\backup_zalo_02_03_2026.zl.zip"

def get_strings(data, min_length=4):
    result = ""
    current = ""
    for b in data:
        c = chr(b)
        if c in string.printable:
            current += c
        else:
            if len(current) >= min_length:
                result += current + "\n"
            current = ""
    if len(current) >= min_length:
        result += current + "\n"
    return result

try:
    with open(file_path, "rb") as f:
        data = f.read(10240) # Read first 10KB
        print("--- Readable Strings in first 10KB ---")
        print(get_strings(data))
except Exception as e:
    print(f"Error: {e}")
