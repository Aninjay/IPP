# Hosting guide - Kala Fest Allocator

The same Python file (`kala_fest_allocator.py`) runs in two modes:

| Mode | Where | How |
|---|---|---|
| Browser mode | Netlify / GitHub Pages / any static host | Python runs inside the visitor's browser (Pyodide). No server. |
| Server mode | Render, Railway, Docker, your PC | `python kala_fest_allocator.py` |

## Option A - Netlify (fixes the "link broken" page)
The old upload had no `index.html` at the site root, so Netlify showed "page not found".
Use the ready-made `netlify_site` folder:
1. Go to app.netlify.com -> Add new site -> **Deploy manually** (drag and drop).
2. Drag the **`netlify_site` folder itself** (the one that contains `index.html`) onto the page. Do NOT drag the whole project folder or the .zip.
3. Open the link Netlify gives you. The first load takes ~20 seconds (it downloads Python, NumPy, Pandas, Matplotlib from the jsDelivr CDN), then the login page appears.
Git deploy: push the whole project; `netlify.toml` already says `publish = "netlify_site"` and no build command is needed.
If you change the Python file, run `python build_site.py` again and re-upload `netlify_site`.
Notes: saved drafts/versions are stored in the visitor's own browser (localStorage), so each browser has its own data. The visitor needs internet access.

## Option B - Render (server mode, shared data)
1. Push the project to GitHub. 2. render.com -> New -> Web Service -> pick the repo.
3. Build: `pip install -r requirements.txt`  Start: `python kala_fest_allocator.py` (render.yaml has both).

## Option C - Railway / Heroku-style
Connect the repo; the Procfile is detected.

## Option D - Docker
    docker build -t kala-fest .
    docker run -d -p 5000:5000 -v kala_data:/data kala-fest

## Option E - Own PC / college LAN
    pip install -r requirements.txt
    python kala_fest_allocator.py      (opens http://localhost:5000)

## Demo logins
convener@tapmi.edu.in / convener123 · coconvener@tapmi.edu.in / coconvener123 · abhinav.karthik@tapmi.edu.in / volunteer123
(Change passwords in build_users() before real use. Do not put real personal data on a public repo.)

## Server-mode notes
Run ONE instance only (sessions are in memory). Set STATE_DIR to a persistent disk to keep saved data.
