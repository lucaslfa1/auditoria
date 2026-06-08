import os

def check_env(path):
    print(f"Checking {path}...")
    try:
        with open(path, 'rb') as f:
            content = f.read()
            if b'\x00' in content:
                print(f"FOUND NULL BYTE at index {content.find(b'\x00')}")
                # Replace null bytes with nothing
                new_content = content.replace(b'\x00', b'')
                with open(path, 'wb') as f2:
                    f2.write(new_content)
                print("Fixed null bytes.")
            else:
                print("No null bytes found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_env('backend/.env')
    check_env('.env')
