#!/usr/bin/env bash
# Setup script for Claude Proxy Bridge (Linux/macOS)

set -e

echo "============================================"
echo "  Claude Proxy Bridge — Setup"
echo "============================================"
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 is not installed. Install Python 3.10+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Python $PYTHON_VERSION found"

# Check pip
if ! python3 -m pip --version &>/dev/null; then
    echo "[ERROR] pip is not available. Install pip first."
    exit 1
fi
echo "[OK] pip found"

# Check claude CLI
if command -v claude &>/dev/null; then
    echo "[OK] Claude CLI found: $(which claude)"
else
    echo "[WARN] Claude CLI not found on PATH."
    echo "       Install it or set CLAUDE_CLI_PATH in .env"
fi

# Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "[OK] Virtual environment created"
else
    echo "[OK] Virtual environment already exists"
fi

# Activate and install
echo
echo "Installing dependencies..."
source .venv/bin/activate
pip install -e . --quiet
echo "[OK] Dependencies installed"

# Copy .env if needed
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[OK] .env file created from .env.example"
    echo "     Edit .env to customize settings if needed."
else
    echo "[OK] .env already exists"
fi

echo
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo
echo "To start the proxy bridge:"
echo "  source .venv/bin/activate"
echo "  python start.py"
echo
echo "To run the health check:"
echo "  python scripts/health_check.py"
echo
