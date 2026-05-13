#!/bin/zsh

cd "/Users/naman/1)Projects/NYU projects/Federhub-all branches/merged/backend" && source .venv/bin/activate && uvicorn app.main:app --reload
