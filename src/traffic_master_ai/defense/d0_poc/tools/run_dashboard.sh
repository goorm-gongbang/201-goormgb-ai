#!/bin/bash
# Run the PoC-0 Cockpit Dashboard
# Usage: ./run_dashboard.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

echo "🛡️ Starting PoC-0 Cockpit Dashboard..."
echo "📁 Project Root: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit not found. Installing..."
    pip install streamlit pandas
fi

# Run the dashboard
streamlit run src/traffic_master_ai/defense/d0_poc/tools/dashboard.py
