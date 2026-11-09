#!/usr/bin/env python3
"""Give Ask the Ark's models plain-language names, descriptions and a sensible menu order.

Each name ends with the real model name, e.g. "Quick Answers - qwen3:4b-instruct".
Models in HIDE stay installed but disappear from the menu (the search component, and the
"thinking" 4B that duplicates Quick Answers). Edit the tables below and run again to change them.
Needs OPENWEBUI_API_KEY in .env.
"""
import json, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENV = {k.strip(): v.strip().strip("\"'") for k, v in (l.split("=", 1) for l in (HERE / ".env").read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))}
URL = ENV.get("OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
KEY = ENV.get("OPENWEBUI_API_KEY", "").strip()
EVERYONE = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]

# model id: (friendly label, description)
NAMES = {
    "qwen3:4b-instruct": ("Quick Answers", "Fast, everyday questions, summaries and how-tos. Answers right away. The best choice for most things."),
    "qwen3:8b": ("Deep Thinker", "The smartest model here. Thinks before answering, so it's slower: use it for hard problems, careful explanations and writing."),
    "llama3.1:8b": ("Second Opinion", "A different model family (Meta). Ask it too when an answer matters, and compare. Good at natural writing."),
    "gemma3:4b": ("Photo Helper", "Can see pictures: attach a photo of a plant, part, label or rash and ask about it."),
}
HIDE = {
    "nomic-embed-text:latest": "Search component used to index the Bookshelf and manuals (not a chat model)",
    "qwen3:4b": "Thinking version of Quick Answers (slower, same model)",
}
# Models that can't call tools (Ollama rejects tool requests for them, e.g. Gemma 3: "does not support tools").
# Ask the Ark normally sends every chat a set of built-in tools; for these it uses the plain mode instead.
NO_TOOLS = {"gemma3:4b"}
# Context (tokens) per model, above the Ark-wide OLLAMA_CONTEXT_LENGTH (8192). The 4B fits 16k fully on a 6 GB card.
CONTEXT = {"qwen3:4b-instruct": 16384}
# Menu order (models not listed come after). Ark Mechanic is a preset defined by setup-ark-mechanic.py.
ORDER = ["qwen3:4b-instruct", "ark-mechanic", "qwen3:8b", "llama3.1:8b", "gemma3:4b"]
DEFAULT = "qwen3:4b-instruct"   # what a new chat starts with


def api(method, path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def save(model_id, name, description, hidden):
    meta_new = {"description": description, "hidden": hidden, "profile_image_url": "/static/favicon.png"}
    params_new = {"num_ctx": CONTEXT[model_id]} if model_id in CONTEXT else {}
    if model_id in NO_TOOLS:
        params_new["function_calling"] = "legacy"
        meta_new["capabilities"] = {"vision": True, "file_upload": True, "citations": True, "builtin_tools": False}
    form = {"id": model_id, "base_model_id": None, "name": name, "meta": meta_new,
            "params": params_new, "access_grants": EVERYONE, "is_active": True}
    code, existing = api("GET", f"/api/v1/models/model?id={model_id}")
    if code == 200 and existing:
        meta = dict(existing.get("meta") or {})
        meta.update(meta_new)
        params = dict(existing.get("params") or {})
        params.update(params_new)
        form["meta"], form["params"] = meta, params
        code, res = api("POST", "/api/v1/models/model/update", form)
    else:
        code, res = api("POST", "/api/v1/models/create", form)
    if code != 200:
        sys.exit(f"{model_id}: failed ({code}) {res}")
    api("POST", "/api/v1/models/model/access/update", {"id": model_id, "access_grants": EVERYONE})  # create ignores sharing
    print(f"  {'hidden ' if hidden else 'named  '} {model_id:26} -> {name}")


def main():
    if not KEY:
        sys.exit("Set OPENWEBUI_API_KEY in .env first.")
    code, res = api("GET", "/api/models?refresh=true")   # only name models that are actually installed
    have = {m["id"] for m in (res.get("data", []) if isinstance(res, dict) else [])}
    for mid, (label, desc) in NAMES.items():
        if mid in have:
            save(mid, f"{label} - {mid}", desc, False)
        else:
            print(f"  skipped {mid:26} (not installed)")
    for mid, why in HIDE.items():
        if mid in have:
            save(mid, mid, why, True)
    code, cfg = api("GET", "/api/v1/configs/models")
    if code == 200:
        cfg["MODEL_ORDER_LIST"], cfg["DEFAULT_MODELS"] = [m for m in ORDER if m in have], DEFAULT
        code, cfg = api("POST", "/api/v1/configs/models", cfg)
        print(f"  menu order: {', '.join(ORDER)}; new chats start with {DEFAULT}" if code == 200 else f"  order not set ({code})")


if __name__ == "__main__":
    main()
