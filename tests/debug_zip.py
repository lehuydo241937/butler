import zipfile
import sys

file_path = r"d:\Agent AI\butler\backup_zalo_02_03_2026.zl.zip"
try:
    with zipfile.ZipFile(file_path, 'r') as z:
        print(f"✅ {file_path} is a valid zip file.")
        print("Files inside:")
        for name in z.namelist()[:10]:
            print(f" - {name}")
except zipfile.BadZipFile:
    print(f"❌ {file_path} is NOT a valid zip file.")
except Exception as e:
    print(f"⚠️ Error: {e}")
