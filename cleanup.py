import os
import shutil
import subprocess

def force_remove_dir_contents(path):
    print(f"Cleaning {path}...")
    if not os.path.exists(path):
        return
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
        except Exception:
            pass

def force_remove_dir(path):
    print(f"Removing {path}...")
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)

# 1. System Temp Folders
force_remove_dir_contents(r"C:\Users\Lucas\AppData\Local\Temp")
force_remove_dir_contents(r"C:\Windows\Temp")

# 2. Dev Caches
print("Cleaning npm cache...")
subprocess.run(["npm", "cache", "clean", "--force"], shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
force_remove_dir_contents(r"C:\Users\Lucas\.nuget\packages")

# 3. Windows.old (might need admin, but we try)
force_remove_dir(r"C:\Windows.old")

# 4. Gemini Caches
force_remove_dir(r"C:\Users\Lucas\.gemini\antigravity")
force_remove_dir(r"C:\Users\Lucas\.gemini\antigravity-ide")

print("Cleanup script finished.")
