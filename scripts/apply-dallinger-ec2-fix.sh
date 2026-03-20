#!/usr/bin/env bash
# Apply dallinger ec2 list instances fixes:
# 1. Pagination + missing-field handling + tqdm + index reset (lib/ec2.py)
# 2. --all flag to list all instances, not just those matching your PEM (command_line/ec2.py)
# Run this after: pip install dallinger  OR  pip install -r requirements.txt

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Find site-packages (handles python3.11, python3.12, etc.)
SP="$PROJECT_ROOT/.venv/lib/python3.12/site-packages"
[[ -d "$SP" ]] || SP=$(ls -d "$PROJECT_ROOT/.venv/lib/python"*"/site-packages" 2>/dev/null | head -1)
# Fallback: find dallinger via current python (system, conda, or activated venv)
[[ -d "$SP" ]] || SP=$(python3 -c "import dallinger, os; print(os.path.dirname(os.path.dirname(dallinger.__file__)))" 2>/dev/null) || true
if [[ ! -d "$SP" ]] || [[ ! -f "$SP/dallinger/command_line/lib/ec2.py" ]]; then
    echo "Error: dallinger not found. Activate venv and run: pip install dallinger"
    exit 1
fi

EC2_LIB="$SP/dallinger/command_line/lib/ec2.py"
EC2_CLI="$SP/dallinger/command_line/ec2.py"
cd "$SP"
APPLIED=0

# Patch 1: lib/ec2.py (pagination, .get(), tqdm, index)
if patch -p1 --forward --dry-run < "$PROJECT_ROOT/patches/dallinger-ec2-list-instances-fix.patch" 2>/dev/null; then
    patch -p1 --forward < "$PROJECT_ROOT/patches/dallinger-ec2-list-instances-fix.patch" && APPLIED=1
elif grep -q 'while "NextToken" in response' "$EC2_LIB" 2>/dev/null; then
    :  # lib fix already applied
else
    patch -p1 --forward < "$PROJECT_ROOT/patches/dallinger-ec2-list-instances-fix.patch" 2>/dev/null && APPLIED=1 || true
fi

# Patch 2: command_line/ec2.py (--all flag)
if patch -p1 --forward --dry-run < "$PROJECT_ROOT/patches/dallinger-ec2-list-all-flag.patch" 2>/dev/null; then
    patch -p1 --forward < "$PROJECT_ROOT/patches/dallinger-ec2-list-all-flag.patch" && APPLIED=1
elif grep -q 'all_instances' "$EC2_CLI" 2>/dev/null; then
    :  # --all flag already applied
else
    patch -p1 --forward < "$PROJECT_ROOT/patches/dallinger-ec2-list-all-flag.patch" 2>/dev/null && APPLIED=1 || true
fi

[[ $APPLIED -eq 1 ]] && echo "Patches applied." || echo "Fixes already applied."
