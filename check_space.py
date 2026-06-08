import os

def get_size(path):
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_size(entry.path)
            except Exception:
                pass
    except Exception:
        pass
    return total

def print_top_items(base_path, limit=15):
    sizes = []
    try:
        for entry in os.scandir(base_path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    s = get_size(entry.path)
                    if s > 0:
                        sizes.append((entry.name + "/", s))
                elif entry.is_file(follow_symlinks=False):
                    s = entry.stat(follow_symlinks=False).st_size
                    if s > 0:
                        sizes.append((entry.name, s))
            except Exception:
                pass
    except Exception as e:
        print(f"Could not scan {base_path}: {e}")
        return

    sizes.sort(key=lambda x: x[1], reverse=True)
    print(f"--- Top items in {base_path} ---")
    for name, size in sizes[:limit]:
        print(f"{name}: {size / (1024*1024*1024):.2f} GB")
    print("\n")

print_top_items("C:\\Users\\Lucas")
print_top_items("C:\\Users\\Lucas\\.gemini")
print_top_items("C:\\Users\\Lucas\\Downloads")
print_top_items("C:\\Users\\Lucas\\AppData\\Roaming")
