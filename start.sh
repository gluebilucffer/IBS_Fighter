#!/usr/bin/env bash
cd "$(dirname "$0")"
export IBS_FIGHTER_HOST="${IBS_FIGHTER_HOST:-0.0.0.0}"
export IBS_FIGHTER_PORT="${IBS_FIGHTER_PORT:-8765}"
python3 app.py
