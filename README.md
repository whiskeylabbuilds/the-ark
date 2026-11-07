# The Ark

**An offline knowledge library and private AI for your household, on one small computer.**

The Ark keeps working when the internet doesn't. Any phone, tablet or laptop on your Wi-Fi opens
one dashboard and gets:

| Section | What it is | App | Port |
|---|---|---|---|
| **Ask the Ark** | Private AI chat that runs on the box: everyday questions, photos, voice, and *Ark Mechanic* for your vehicles. It can search the whole library. | Open WebUI + Ollama | 3000 (3443 for voice) |
| **Reference Library** | All of Wikipedia, WikiMed, iFixit, survival guides, Stack Exchange Q&A, LibreTexts textbooks | Kiwix | 8080 |
| **Courses & Lessons** | Khan Academy and other full courses with videos and progress tracking | Kolibri | 8300 |
| **Bookshelf** | Books and PDFs: Bible, philosophy, field manuals, your own manuals | Kavita | 5000 |
| **Music** | Your music library, in a browser or a phone app | Navidrome | 4533 |
| **Field Notes** | Shared notes and checklists | FlatNotes | 8083 |
| **Data Toolkit** | Encode, decode, checksum, encrypt | CyberChef | 8084 |
| **Regional Map** | Street-level offline map of the area you choose | Protomaps + MapLibre | 8082 |
| **Mesh Radio** | Meshtastic and MeshCore clients for off-grid LoRa messaging | meshtastic-web, mc-webui | 8085, 8086 |
| **Dashboard** | Start page with a Getting Started guide, live GPU and power readings | Homepage | 80 |

Everything runs in Docker, nothing phones home, and all content is downloaded once while you're online.

## What you need

- **A 64-bit PC** running **Ubuntu 24.04, Linux Mint 22 or Debian 12**, wired or on Wi-Fi to your router.
- **16 GB RAM** recommended (8 GB works with the small AI model set).
- **500 GB disk** for the default content (about 250 GB used; see the disk budget below).
- **A graphics card is optional.** With an NVIDIA card (6 GB+) the AI answers in seconds. On the CPU
  it works but is slower. AMD Radeon cards supported by ROCm work too.

Reference build: HP EliteDesk 800 G6 Mini (i7-10700T, 32 GB, GTX 1660 Ti 6 GB, 512 GB NVMe), Linux Mint 22.3.
There the AI runs at about 37 words/s fully on the GPU, and the whole box draws about 25–45 W.

## Install

```bash
sudo apt install -y git
git clone https://github.com/YOUR-ACCOUNT/the-ark.git ~/ark
cd ~/ark && ./install.sh
```

The installer asks before each big step and is safe to run again at any time. It:

1. Detects your graphics card. **NVIDIA:** installs the driver, then asks you to reboot and run `./install.sh` again.
2. Installs Docker (plus the NVIDIA Container Toolkit when needed) and creates `/srv/ark` for all content.
3. Creates `.env` with a random secret key, your time zone and your LAN address.
4. Optionally renames the computer to `ark` so people can type `http://ark.local`, and installs a small
   service that keeps the dashboard links right when your router hands out a new address.
5. Starts everything, downloads the AI models picked for your hardware, and offers the books, the
   Reference Library (~100 GB) and the map, each showing its size first.

Then finish in a browser (the installer prints these steps):

- **Ask the Ark** (`:3000`): create the first account (it becomes the admin). Under Settings → Account → API Keys,
  create a key, put it in `.env` as `OPENWEBUI_API_KEY=...`, and run `scripts/setup-ai.sh`. That applies the
  search tuning and voice settings, installs the library search tool, names the models and creates Ark Mechanic.
- **Bookshelf** (`:5000`): create the admin account and add each folder under `/books` as a library.
- **Courses** (`:8300`): run the setup, then Device → Channels → Import. Pick only the topics you need, and watch the size it shows.
- **Music** (`:4533`): create the admin account, then copy music into `/srv/ark/music`.

The **Getting Started & FAQ** page on the dashboard explains every section to the rest of the household.

## Disk budget (512 GB drive)

| Item | GB |
|---|---|
| Reference Library (`content/zims.list`) | ~104 |
| AI models (full set) | ~17 |
| Map, 4 US states at full detail | ~2 |
| Kolibri (pick channels) | budget ~40–60 |
| Docker images | ~17 |
| Books | <1 |
| Kept free (`RESERVE_GB` in the downloader) | 60 |

Edit `content/zims.list` to change what's in the Reference Library (Wikipedia with images is +75 GB, for example).
The downloader shows sizes and free space, and refuses to fill the disk.

## Make it yours (privately)

Anything personal goes in **`local/`**, which git ignores, so it never lands in a repository.
`cp -r local.example local` to start. See `local.example/README.md`.

- `local/fleet.txt`: your vehicles and equipment. Ark Mechanic is told about them (`scripts/setup-ark-mechanic.py`).
- `local/homepage/`: your own dashboard tiles and pages, such as a family emergency plan or house rules.
- Vehicle and equipment manuals go in `/srv/ark/books/Vehicles & Equipment/<machine>/`.
  Run `scripts/sync-knowledge.py` and the AI can quote them (spec tables are kept intact).

Music, books you bought and anything else under `/srv/ark` stay on your machine. The project folder only holds code and settings.

## Scripts

| Script | What it does |
|---|---|
| `install.sh` | Everything above. `ARK_YES=1` accepts defaults; `ARK_NO_PULL=1` skips updating the programs. |
| `scripts/setup-ai.sh` | Finishes Ask the Ark (needs `OPENWEBUI_API_KEY`). Runs the four scripts below. |
| `scripts/setup-ask-the-ark.py` | Search tuning (chunk size, hybrid search), offline voice, Reference Library tool |
| `scripts/setup-model-names.py` | Friendly model names ("Quick Answers - qwen3:4b-instruct"), menu order, hides helper models |
| `scripts/setup-ark-mechanic.py` | The Ark Mechanic assistant, from `local/fleet.txt` |
| `scripts/sync-knowledge.py` | Indexes every Bookshelf shelf into an AI knowledge collection (`--dry-run` to preview) |
| `scripts/pull-models.sh` | AI models: `full` (~17 GB) or `small` (~7 GB), picked for your hardware (`MODEL_SET=` to choose) |
| `scripts/download-zims.sh` | Reference Library; resumes dropped downloads and verifies checksums (`--dry-run` to preview) |
| `scripts/download-books.sh` | Public-domain books and official manuals for the Bookshelf |
| `scripts/build-maps.sh` | Offline map for `MAP_BBOX` / `MAP_REGION_NAME` in `.env` (find a box at bboxfinder.com) |
| `scripts/export-ca.sh` | Publishes the Ark's HTTPS certificate at `/ca/ark-root-ca.crt` for voice |
| `scripts/update-host-addr.sh` | Points the dashboard at the current IP (run automatically) |

## Notes

- **Graphics card:** `.env`'s `COMPOSE_FILE` adds `compose.nvidia.yml` or `compose.amd.yml` to the base `docker-compose.yml`.
  With no graphics-card file, the AI runs on the CPU. On NVIDIA systems that also have a built-in GPU, the desktop
  runs on the built-in one so the AI gets all the card's memory. Check with `nvidia-smi`: idle use should be near 0 MiB.
- **AMD:** if the AI ends up on the CPU, set `HSA_OVERRIDE_GFX_VERSION` in `.env` (e.g. `10.3.0` for RX 6600-class cards) and `docker compose up -d`.
- **Voice** (Ask the Ark): Whisper `small.en` listens and Kokoro speaks, both on the CPU. Browsers only allow the microphone
  over HTTPS. Caddy serves Ask the Ark at `https://<ark>:3443` with its own local certificate authority. Each device trusts it
  once via `/ca/ark-root-ca.crt`; the Getting Started page has the steps for each kind of device.
- **AI accuracy:** small models make mistakes. Check medical answers against WikiMed and the manuals.
- **MeshCore** (`:8086`): flash the radio with the *Companion USB* firmware while you're online, then plug it into the Ark.
  With a Meshtastic radio plugged in too, set `MC_SERIAL_PORT` in `.env` (`ls /dev/serial/by-id/`).
- **Meshtastic:** the web client uses Web Serial, so open it in Chrome or Chromium on the Ark itself (`http://localhost:8085`).
- **Ollama** is only reachable from the Ark itself (`127.0.0.1:11434`).
- **Power loss:** every service restarts on its own. Set the BIOS to *After Power Loss → Power On* so the Ark comes back by itself.
- **Updates:** while online, run `docker compose pull && docker compose up -d`, then re-run `scripts/download-zims.sh` (it replaces older versions).

## About

The Ark was created by **WhiskeyLab**. Follow along on TikTok at [@whiskeylab.io](https://www.tiktok.com/@whiskeylab.io),
or get in touch at [whiskeylabmedia@gmail.com](mailto:whiskeylabmedia@gmail.com).
The dashboard's *About The Ark* tile (`/pages/about.html`) shows the same.

## License and credits

The Ark's own scripts and configuration are MIT licensed (see `LICENSE`), © 2026 WhiskeyLab.
It's glue around these projects, whose own licenses apply to them:
[Kiwix](https://kiwix.org), [Ollama](https://ollama.com), [Open WebUI](https://openwebui.com), [Kolibri](https://learningequality.org/kolibri),
[Kavita](https://www.kavitareader.com), [Navidrome](https://www.navidrome.org), [Homepage](https://gethomepage.dev),
[FlatNotes](https://github.com/dullage/flatnotes), [CyberChef](https://github.com/gchq/CyberChef),
[Protomaps](https://protomaps.com) and [MapLibre](https://maplibre.org), [Meshtastic](https://meshtastic.org),
[mc-webui](https://github.com/marekwo/mc-webui), [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI), [Caddy](https://caddyserver.com).
Downloaded content keeps its own licenses (Wikipedia CC BY-SA, Project Gutenberg public domain, and so on).
