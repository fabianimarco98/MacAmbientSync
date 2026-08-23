#!/bin/bash
# Launcher con doppio click per macOS

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "      Avvio Mac Screen Ambient Sync per Home Assistant    "
echo "=========================================================="

if [ ! -d "venv" ]; then
    echo "[1/3] Creazione Virtual Environment Python..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

echo "[2/3] Avvio Sincronizzazione Schermo -> Lampada..."
./venv/bin/python screen_sync.py

read -p "Premi INVIO per chiudere questa finestra..."
