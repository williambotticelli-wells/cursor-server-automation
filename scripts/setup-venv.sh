#!/usr/bin/env bash
# Create/refresh venv, install deps, and apply dallinger ec2 list-instances fix.
# Run after: refactoring venv, or any pip install that updates dallinger.
#
# Usage: ./scripts/setup-venv.sh [pip_install_args...]
# Example: ./scripts/setup-venv.sh
# Example: ./scripts/setup-venv.sh -r requirements.txt -c constraints.txt

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Create venv if missing
if [[ ! -d ".venv" ]]; then
    echo "Creating .venv..."
    python3 -m venv .venv
fi

# Activate and install
source .venv/bin/activate
echo "Installing dependencies..."
if [[ -f constraints.txt ]]; then
    pip install -q -r requirements.txt -c constraints.txt "$@"
else
    pip install -q -r requirements.txt "$@"
fi

# Apply dallinger ec2 fix (pagination, tqdm, display)
echo "Applying dallinger ec2 list-instances fix..."
"$SCRIPT_DIR/apply-dallinger-ec2-fix.sh"

echo "Setup complete. Activate with: source .venv/bin/activate"
