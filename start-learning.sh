#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ -x .venv/Scripts/python.exe ]]; then
  python_cmd=.venv/Scripts/python.exe
elif [[ -x .venv/bin/python ]]; then
  python_cmd=.venv/bin/python
else
  python -m venv .venv
  if [[ -x .venv/Scripts/python.exe ]]; then
    python_cmd=.venv/Scripts/python.exe
  else
    python_cmd=.venv/bin/python
  fi
fi

"$python_cmd" -m pip install -r learning_backend/requirements.txt
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi
(cd frontend && npm run build)

if ! "$python_cmd" -c 'from learning_backend.pdf_study import API_KEY; raise SystemExit(0 if API_KEY else 1)'; then
  read -rsp 'Paste your OpenAI API key (hidden): ' OPENAI_API_KEY
  printf '\n'
  export OPENAI_API_KEY
fi
exec "$python_cmd" -m learning_backend.server
