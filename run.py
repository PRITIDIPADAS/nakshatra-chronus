"""Start CHRONOS: python run.py, then open http://127.0.0.1:8000"""
import os
import sys

import uvicorn

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

if __name__ == "__main__":
    uvicorn.run("app:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")), app_dir=os.path.join(ROOT, "backend"))
