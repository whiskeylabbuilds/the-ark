#!/usr/bin/env python3
"""Create (or update) the "Ark Mechanic" assistant in Ask the Ark.

Qwen3 4B with 16k context (fits fully in a 6 GB GPU), told about your vehicles and equipment,
with the "Bookshelf: Vehicles & Equipment" collection and the Reference Library search tool.
Shared read-only with every account.

Your machines go in local/fleet.txt (one per line, e.g. "- 2015 Ford F-150 (5.0 L V8)") and
optional example questions in local/mechanic-prompts.txt. Both are private (git-ignored).
Edit them and run this again to update. Needs OPENWEBUI_API_KEY in .env.
"""
import json, sys, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENV = {k.strip(): v.strip().strip("\"'") for k, v in (l.split("=", 1) for l in (HERE / ".env").read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))}
URL = ENV.get("OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
KEY = ENV.get("OPENWEBUI_API_KEY", "").strip()

LOCAL = HERE / "local"
_fleet = LOCAL / "fleet.txt"
FLEET = _fleet.read_text().strip() if _fleet.exists() and _fleet.read_text().strip() else \
    "(No machines listed yet. Ask which vehicle or equipment it is, including year, make, model and engine.)"
_prompts = LOCAL / "mechanic-prompts.txt"
PROMPTS = [l.strip() for l in _prompts.read_text().splitlines() if l.strip()] if _prompts.exists() else [
    "How often should I change the engine oil?",
    "Walk me through replacing front brake pads",
    "Tractor: daily checks before work",
    "How do I sharpen and balance mower blades?",
]

SYSTEM = f"""You are Ark Mechanic, the maintenance and repair helper on The Ark, this household's offline server.
There is no internet. Your sources are the attached manuals and the Ark's Reference Library.

Our vehicles and equipment:
{FLEET}

How to answer:
1. Always search our manuals first: call query_knowledge_files (or query_knowledge_bases) with a short query naming the machine and the topic, e.g. "F-150 engine oil capacity". Quote specifications exactly as written: fluid types and capacities, torque values, intervals, part numbers, gaps and pressures. Name the manual and page or section you used.
2. If the manuals don't cover all of it, immediately (without asking) use the search_library tool (try collection "ifixit" for repair guides and "mechanics" for the Motor Vehicle Mechanics Q&A, then everything), and read_article for the best match. Cite the article title.
3. If neither has the answer, say so plainly, give general best practice, and label it as general knowledge rather than from our manuals. Never invent a specification, torque value or part number.
4. Ask which machine, engine or trim it is when the answer depends on it.
5. Put safety first: mention jack stands and wheel chocks, disconnecting the battery, hot coolant and exhaust, hydraulic pressure, PTO and blade hazards when they apply.
6. Keep answers practical: tools needed, parts and fluids, then numbered steps."""

PUBLIC_READ = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]
WANTED_KNOWLEDGE = ["Bookshelf: Vehicles & Equipment"]  # vehicle manuals only; mixing in other shelves confuses citations


def api(method, path, body=None):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read()
            return r.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def main():
    if not KEY:
        sys.exit("Set OPENWEBUI_API_KEY in .env first.")
    _, kl = api("GET", "/api/v1/knowledge/?page=1")
    items = kl.get("items", []) if isinstance(kl, dict) else []
    knowledge = [{"id": k["id"], "name": k["name"], "description": k.get("description", ""), "type": "collection"}
                 for k in items if k["name"] in WANTED_KNOWLEDGE]
    missing = set(WANTED_KNOWLEDGE) - {k["name"] for k in knowledge}
    if missing:
        print("Note: not found yet (run scripts/sync-knowledge.py):", ", ".join(sorted(missing)))
    form = {
        "id": "ark-mechanic",
        "base_model_id": "qwen3:4b-instruct",  # Qwen3-4B-Instruct-2507: no long "thinking" step, better tool use
        "name": "Ark Mechanic - qwen3:4b-instruct",
        "meta": {
            "description": "Maintenance and repair help for your vehicles and equipment, from your manuals and the offline library.",
            "profile_image_url": "/static/favicon.png",
            "capabilities": {"citations": True, "vision": False, "file_upload": True},
            "knowledge": knowledge,
            "toolIds": ["ark_library"],
            "suggestion_prompts": [{"content": p} for p in PROMPTS],
        },
        "params": {"system": SYSTEM, "num_ctx": 16384, "temperature": 0.3, "function_calling": "native"},
        "access_grants": PUBLIC_READ,
        "is_active": True,
    }
    code, existing = api("GET", "/api/v1/models/model?id=ark-mechanic")
    if code == 200 and existing:
        code, res = api("POST", "/api/v1/models/model/update?id=ark-mechanic", form)
        if code != 200:
            code, res = api("POST", "/api/v1/models/model/update", form)
        action = "updated"
    else:
        code, res = api("POST", "/api/v1/models/create", form)
        action = "created"
    if code != 200:
        sys.exit(f"Failed ({code}): {res}")
    api("POST", "/api/v1/models/model/access/update", {"id": "ark-mechanic", "access_grants": PUBLIC_READ})  # create ignores sharing
    print(f"Ark Mechanic {action}: base qwen3:4b-instruct, 16k context, tools: ark_library, knowledge: "
          + (", ".join(k["name"] for k in knowledge) or "none yet"))


if __name__ == "__main__":
    main()
