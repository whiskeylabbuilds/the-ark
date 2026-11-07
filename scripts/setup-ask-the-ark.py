#!/usr/bin/env python3
"""Apply the Ark's Ask the Ark (Open WebUI) settings. Safe to run again at any time.

  1. Document search tuned for manuals: bigger chunks, keyword + meaning (hybrid) search, 6 excerpts.
  2. Offline voice: Whisper small.en listens, the kokoro service speaks (voice af_heart).
  3. Installs the "Ark Reference Library" tool (config/open-webui/tools/ark_library.py), shared
     with every account, so models can search and read the Kiwix library.

Open WebUI keeps these in its own database after the first start, which is why they're set
through its API rather than only in docker-compose.yml. Needs OPENWEBUI_API_KEY in .env
(Ask the Ark → Settings → Account → API Keys; requires an admin account).

The rest of the AI setup: scripts/setup-ai.sh runs this plus the model names, Ark Mechanic
and the Bookshelf indexing.
"""
import json, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENV = {k.strip(): v.strip().strip("\"'") for k, v in (l.split("=", 1) for l in (HERE / ".env").read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))}
URL = ENV.get("OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
KEY = ENV.get("OPENWEBUI_API_KEY", "").strip()
EVERYONE = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]

RETRIEVAL = {"CHUNK_SIZE": 2000, "CHUNK_OVERLAP": 400, "TOP_K": 6, "TOP_K_RERANKER": 6, "ENABLE_RAG_HYBRID_SEARCH": True}
STT = {"ENGINE": "", "WHISPER_MODEL": ENV.get("WHISPER_MODEL", "small.en")}   # "" = Whisper inside Open WebUI
TTS = {"ENGINE": "openai", "OPENAI_API_BASE_URL": "http://kokoro:8880/v1", "OPENAI_API_KEY": "not-needed",
       "MODEL": "kokoro", "VOICE": ENV.get("TTS_VOICE", "af_heart"), "SPLIT_ON": "punctuation"}
TOOL = {"id": "ark_library", "name": "Ark Reference Library",
        "meta": {"description": "Search and read the offline Reference Library (Wikipedia, WikiMed, iFixit, Stack Exchange, LibreTexts, survival guides)."}}


def api(method, path, body=None, timeout=120):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            t = r.read()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def check(what, code, res):
    if code != 200:
        sys.exit(f"{what}: failed ({code}) {res}")
    print(f"  ok  {what}")


def main():
    if not KEY:
        sys.exit("Set OPENWEBUI_API_KEY in .env first (Ask the Ark → Settings → Account → API Keys).")

    check("document search (chunks 2000/400, hybrid, top 6)", *api("POST", "/api/v1/retrieval/config/update", RETRIEVAL))

    code, cfg = api("GET", "/api/v1/audio/config")
    check("read voice settings", code, cfg)
    cfg["stt"].update(STT)
    cfg["tts"].update(TTS)
    body = {"tts": cfg["tts"], "stt": cfg["stt"]}
    if cfg.get("realtime"):
        body["realtime"] = cfg["realtime"]
    check(f"voice (Whisper {STT['WHISPER_MODEL']} + Kokoro {TTS['VOICE']})", *api("POST", "/api/v1/audio/config/update", body))

    form = dict(TOOL, content=(HERE / "config/open-webui/tools/ark_library.py").read_text(), access_grants=EVERYONE)
    code, _ = api("GET", f"/api/v1/tools/id/{TOOL['id']}")
    path = f"/api/v1/tools/id/{TOOL['id']}/update" if code == 200 else "/api/v1/tools/create"
    check("Reference Library tool installed", *api("POST", path, form))
    check("Reference Library tool shared with every account",
          *api("POST", f"/api/v1/tools/id/{TOOL['id']}/access/update", {"access_grants": EVERYONE}))


if __name__ == "__main__":
    main()
