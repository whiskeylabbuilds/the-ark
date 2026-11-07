# Your private layer

Copy this folder to `local/` (`cp -r local.example local`), then copy in the dashboard files you want to change:
`mkdir -p local/homepage/pages && cp config/homepage/services.yaml local/homepage/ && cp config/homepage/pages/*.html local/homepage/pages/`. Everything in `local/` is git-ignored,
so it never ends up in a public repository: family pages, your vehicle list, personal tiles.

| File | Used by | What it does |
|---|---|---|
| `fleet.txt` | `scripts/setup-ark-mechanic.py` | Your vehicles and equipment, one per line. Ark Mechanic is told about them. |
| `mechanic-prompts.txt` | same | Example questions shown under Ark Mechanic (one per line). |
| `compose.yml` | Docker Compose (via `COMPOSE_FILE` in `.env`) | Mounts your own dashboard tiles and pages over the defaults. |
| `homepage/services.yaml` | the dashboard | Your tiles. Start from a copy of `config/homepage/services.yaml`. |
| `homepage/pages/` | the dashboard, at `/pages/...` | Your pages (a family emergency plan, house rules...). Copy `config/homepage/pages/getting-started.html` here too, since this folder replaces the default one. |

After creating `local/compose.yml`, add it to the end of `COMPOSE_FILE` in `.env`, e.g.
`COMPOSE_FILE=docker-compose.yml:compose.nvidia.yml:local/compose.yml`, then `docker compose up -d`.
(`install.sh` does this for you when `local/compose.yml` exists.)
