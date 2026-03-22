"""Write fixed hook scripts to Claude hooks directory."""
import os

HOOKS_DIR = os.path.join(os.environ['USERPROFILE'], '.claude', 'hooks')

# Read each template and write it
for name in ['session-end.ps1', 'session-safety-net.ps1']:
    src = os.path.join(os.path.dirname(__file__), name)
    dst = os.path.join(HOOKS_DIR, name)
    if os.path.exists(src):
        with open(src, 'r') as f:
            content = f.read()
        with open(dst, 'w', newline='\r\n') as f:
            f.write(content)
        print(f"Written: {name} ({os.path.getsize(dst)} bytes)")
    else:
        print(f"MISSING: {src}")
