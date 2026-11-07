#!/usr/bin/env python3
"""Index the Bookshelf for the AI: one Open WebUI Knowledge collection per shelf.

  /srv/ark/books/<Shelf>/<Title>/<file>.pdf|.epub|.txt|.md   ->   Knowledge "Bookshelf: <Shelf>"

New or changed files are uploaded and indexed; files already indexed are skipped (tracked by
checksum in $ARK_DATA/knowledge-sync.json). Collections are readable by everyone who has an
Ask the Ark account. Scanned PDFs with no text layer are reported, because the AI can't read
them until they've had text recognition (OCR).

Needs OPENWEBUI_API_KEY in .env (Ask the Ark → Settings → Account → API Keys).

  scripts/sync-knowledge.py              # sync every shelf
  scripts/sync-knowledge.py --dry-run    # show what would change
  scripts/sync-knowledge.py "Vehicles & Equipment"   # sync one shelf
"""
import hashlib, json, mimetypes, os, subprocess, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENV = {}
for line in (HERE / ".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip("\"'")

DATA = Path(ENV.get("ARK_DATA", "/srv/ark"))
BOOKS = DATA / "books"
STATE_FILE = DATA / "knowledge-sync.json"
URL = ENV.get("OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
KEY = ENV.get("OPENWEBUI_API_KEY", "")
EXTS = {".pdf", ".epub", ".txt", ".md"}
PREFIX = "Bookshelf: "
PUBLIC_READ = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
# Shelves whose PDFs are indexed as layout-preserving text (pdftotext -layout, one "## Page N" heading per page).
# Spec tables (capacities, torques, intervals) stay intact this way; Open WebUI's own PDF reader scrambles them.
LAYOUT_SHELVES = {s.strip() for s in ENV.get("LAYOUT_TEXT_SHELVES", "Vehicles & Equipment").split(",") if s.strip()}

args = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv


def api(method, path, body=None, raw=None, ctype=None, timeout=60):
    headers = {"Authorization": f"Bearer {KEY}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        data, headers["Content-Type"] = raw, ctype
    req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}") from None


def multipart(path: Path, data: bytes = None, name: str = None):
    boundary = uuid.uuid4().hex
    name = name or path.name
    if data is not None:
        ctype = "text/markdown"
    else:
        data = path.read_bytes()
        ctype = "application/epub+zip" if path.suffix.lower() == ".epub" else (mimetypes.guess_type(name)[0] or "application/octet-stream")
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pdf_has_text(path: Path):
    try:
        out = subprocess.run(["pdftotext", "-l", "8", str(path), "-"], capture_output=True, text=True, timeout=120).stdout
        return len(out.strip()) > 200
    except Exception:
        return True  # can't tell; let Open WebUI try


def layout_markdown(path: Path):
    """PDF -> markdown text with a '## Page N' heading per page, keeping table rows on one line."""
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=600).stdout
    pages = out.split("\f")
    parts = [f"# {path.stem}\n\nSource: {path.name} (text extracted page by page; page numbers are PDF pages)\n"]
    for n, page in enumerate(pages, 1):
        lines = [l.rstrip() for l in page.splitlines()]
        body = "\n".join(lines).strip()
        if body:
            parts.append(f"\n## Page {n}\n\n{body}\n")
    return "".join(parts).encode()


def collections():
    found, page = {}, 1
    while True:
        res = api("GET", f"/api/v1/knowledge/?page={page}")
        items = res.get("items", res if isinstance(res, list) else [])
        for k in items:
            found[k["name"]] = k["id"]
        if not isinstance(res, dict) or len(found) >= res.get("total", 0) or not items:
            return found
        page += 1


def wait_processed(file_id, limit=1800):
    """Upload is processed in the background; wait until its text is indexed."""
    start = time.time()
    while time.time() - start < limit:
        f = api("GET", f"/api/v1/files/{file_id}")
        status = ((f or {}).get("data") or {}).get("status")
        if status in ("completed", None):
            return "completed"
        if status == "failed":
            return "failed: " + str(((f or {}).get("data") or {}).get("error", ""))[:200]
        time.sleep(3)
    return "timed out"


def main():
    if not KEY and not DRY:
        sys.exit("Set OPENWEBUI_API_KEY in .env first (Ask the Ark → Settings → Account → API Keys).")
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    shelves = sorted(d for d in BOOKS.iterdir() if d.is_dir() and (not args or d.name in args))
    existing = collections() if KEY else {}
    added = skipped = 0
    needs_ocr, failed = [], []

    for shelf in shelves:
        files = sorted(p for p in shelf.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and not p.name.endswith(".part"))
        name = PREFIX + shelf.name
        print(f"\n== {name}  ({len(files)} files)")
        kid = existing.get(name)
        if not kid and not DRY:
            kid = api("POST", "/api/v1/knowledge/create", {
                "name": name,
                "description": f"Everything on the '{shelf.name}' shelf of the Ark's Bookshelf ({BOOKS / shelf.name}).",
                "access_grants": PUBLIC_READ,
            })["id"]
            existing[name] = kid
            api("POST", f"/api/v1/knowledge/{kid}/access/update", {"access_grants": PUBLIC_READ})  # create ignores sharing
            print("   created collection (shared with every account)")
        for p in files:
            rel = str(p.relative_to(BOOKS))
            digest = sha256(p)
            mode = "layout" if (p.suffix.lower() == ".pdf" and shelf.name in LAYOUT_SHELVES) else "file"
            prev = state.get(rel, {})
            if prev.get("sha256") == digest and prev.get("knowledge_id") == kid and prev.get("mode", "file") == mode:
                skipped += 1
                continue
            if p.suffix.lower() == ".pdf" and not pdf_has_text(p):
                needs_ocr.append(rel)
                print(f"   !! no text layer (needs OCR): {rel}")
                continue
            print(f"   + {rel}  ({p.stat().st_size / 1e6:.1f} MB{', as page-by-page text' if mode == 'layout' else ''})", flush=True)
            if DRY:
                continue
            try:
                if mode == "layout":
                    body, ctype = multipart(p, layout_markdown(p), p.stem + " (text).md")
                else:
                    body, ctype = multipart(p)
                f = api("POST", "/api/v1/files/?process=true", raw=body, ctype=ctype, timeout=600)
                result = wait_processed(f["id"])
                if result != "completed":
                    raise RuntimeError(result)
                api("POST", f"/api/v1/knowledge/{kid}/file/add", {"file_id": f["id"]}, timeout=1800)
                old = state.get(rel, {}).get("file_id")
                if old and old != f["id"]:  # file changed: drop the stale copy
                    try:
                        api("POST", f"/api/v1/knowledge/{kid}/file/remove", {"file_id": old})
                    except RuntimeError:
                        pass
                state[rel] = {"sha256": digest, "file_id": f["id"], "knowledge_id": kid, "mode": mode}
                STATE_FILE.write_text(json.dumps(state, indent=1))
                added += 1
            except Exception as e:
                failed.append(f"{rel}: {e}")
                print(f"   !! failed: {e}")

    print(f"\nIndexed {added} new or changed files, {skipped} already up to date.")
    if needs_ocr:
        print(f"{len(needs_ocr)} scanned PDF(s) need text recognition first; see 'Scanned manuals' in the README.")
    if failed:
        print(f"{len(failed)} failed:\n  " + "\n  ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
