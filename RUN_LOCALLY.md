# Run OrderBridge on your own computer

Where to type the commands: a terminal.
- **Windows:** PowerShell (Start menu → "PowerShell"), or the terminal inside VS Code (View → Terminal).
- **macOS:** Terminal (Applications → Utilities).
- **Linux:** any terminal.

## 1. Install the prerequisites (one time)
- **Python 3.12 or 3.13** from https://www.python.org/downloads/. On Windows, tick **"Add python.exe to PATH"** in the installer.
- **Node.js 20 or 22 LTS** from https://nodejs.org/
- Check they work. On Windows use `python`; on macOS and Linux use `python3`. You should see version numbers.
  ```
  python --version
  node --version
  npm --version
  ```

## 2. Unzip the project
Extract `OrderBridge_project.zip`, for example to `C:\Projects\` or `~/Projects/`. You get an `orderbridge` folder. Then, in your terminal:
```
cd C:\Projects\orderbridge        # Windows
cd ~/Projects/orderbridge         # macOS / Linux
```
Run every command below from inside this `orderbridge` folder.

## 3. Set up the backend (one time)
**Windows (PowerShell)**
```
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
```
**macOS / Linux**
```
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
```

## 4. Build the frontend (one time, and again after any UI change)
```
cd frontend
npm ci
npm run build
cd ..
```

## 5. Create the demo database
Do this once, and again whenever you want a clean demo.

- **Windows:** `backend\.venv\Scripts\python.exe scripts\reset_demo.py`
- **macOS / Linux:** `backend/.venv/bin/python scripts/reset_demo.py`

## 6. Start the app
- **Windows:** `powershell -ExecutionPolicy Bypass -File scripts\start.ps1`
- **macOS / Linux:** `./scripts/start.sh`

Leave this terminal open. The app is running while you see `Uvicorn running on http://127.0.0.1:8000`.

## 7. Open it
Go to **http://127.0.0.1:8000** in Chrome or Edge.
- **Username:** `owner@demo-gba`
- **Password:** `orderbridge-demo`

Then click **Load synthetic example** → **Analyze new order**, and follow `docs/demo-script.md`.

To stop the app, press **Ctrl + C** in that terminal.

## Optional: run the tests
**Windows**
```
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..
python scripts\verify_reference.py
```
**macOS / Linux**
```
cd backend && .venv/bin/pytest -q && cd ..
python3 scripts/verify_reference.py
```
Expected: `59 passed`, and every verifier line `OK`.

**Browser tests**
1. Install the browser once: `cd frontend`, then `npx playwright install chromium`.
2. In a **second** terminal, start the app on a freshly reset database (steps 5 and 6).
3. In the first terminal, still in `frontend`, run `npx playwright test`.

On macOS or Linux you can instead run `./scripts/e2e.sh`, which does all of this for you.

## Optional: turn on live AI
1. Copy `.env.example` to `.env` in the `orderbridge` folder.
2. Set `ANTHROPIC_API_KEY=` to your own key. Keep this file private and never share it.
3. Restart the app (Ctrl + C, then step 6).
4. Click **Switch to live AI** in the header.

## Common problems
| Problem | Fix |
|---|---|
| `python` not found (Windows) | Reinstall Python with "Add to PATH" ticked, or use `py` instead of `python` |
| PowerShell says scripts are disabled | Use the `powershell -ExecutionPolicy Bypass -File ...` form shown in step 6 |
| Port 8000 already in use | Windows: `$env:PORT=8010` before step 6. macOS/Linux: `PORT=8010 ./scripts/start.sh`. Then open http://127.0.0.1:8010. The allowed origins in `.env.example` must include that port. |
| Page shows `{"detail":"Not Found"}` | You skipped step 4 (frontend build) |
| Want to start the demo over | Stop the app, run step 5 again, then start it again |
