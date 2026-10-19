#!/usr/bin/env bash
# Serve the face simulator on http://127.0.0.1:8317
cd "$(dirname "$0")" && exec python3 -m http.server 8317 --bind 127.0.0.1
