import os, base64
HOOKS = os.path.join(os.environ["USERPROFILE"], ".claude", "hooks")

# Read session-end.ps1 current content and patch it
se_path = os.path.join(HOOKS, "session-end.ps1")
with open(se_path, "r") as f: content = f.read()

# Patch 1: Add changed files capture after git context
old1 = """    }
} catch {}"""

new1 = """        $committedFiles = @()
        try { $committedFiles = @(git diff --name-only HEAD~1 2>$null) } catch {}
        $uncommittedFiles = @(git diff --name-only 2>$null)
        $stagedFiles = @(git diff --cached --name-only 2>$null)
        $untrackedFiles = @(git ls-files --others --exclude-standard 2>$null)
        $changedFiles = @($committedFiles + $uncommittedFiles + $stagedFiles + $untrackedFiles |
            Where-Object { $_ } | Select-Object -Unique | Select-Object -First 20)
    }
} catch {}"""
