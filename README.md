# AllDebrid Project

Turn AllDebrid magnets into Emby-compatible `.strm` files without downloading the video files to disk.

This project is designed for homelab users who want:

- a simple file-based workflow
- a local Emby library made of `.strm` files
- automatic magnet processing through AllDebrid
- movie and TV show folder organization
- link refresh when direct URLs expire
- a setup that can later grow into Sonarr, Radarr, or n8n automation

Default library root:

```text
/mnt/16G/alldebrid-emby
```

## What This Does

The app can:

1. Add magnets manually or from files.
2. Send magnets to AllDebrid using your API key.
3. Poll AllDebrid until the magnet is ready.
4. Detect valid video files inside the release.
5. Generate `.strm` files for Emby.
6. Organize output into Movies and Series folders.
7. Refresh expired direct links.
8. Reconcile local `.strm` files against internal state.
9. Run manually or as an always-on worker.

It does not download the actual media files. It stores stream URLs inside `.strm` files.

## Who This Is For

This repository is intended to be usable by:

- beginners who want a copy-paste install path
- homelab users running Linux and Emby
- advanced users who want to extend it later

## Quick Start

Clone the repository:

```bash
git clone https://github.com/Gabba82/AlldebridProject.git
cd AlldebridProject
chmod +x scripts/*.sh
```

Install everything and auto-create the base config:

```bash
ALLDEBRID_API_KEY="your_api_key" ROOT_DIR="/mnt/16G/alldebrid-emby" bash scripts/install.sh
```

Activate the virtual environment and test your AllDebrid connection:

```bash
source .venv/bin/activate
python -m app.cli test-auth
```

If you prefer not to pass the API key on the command line:

```bash
bash scripts/install.sh
nano .env
source .venv/bin/activate
python -m app.cli test-auth
```

## First Real Use

Add one magnet:

```bash
python -m app.cli add-magnet "magnet:?xt=urn:btih:..."
python -m app.cli process-pending
```

Or process magnets from the inbox:

```bash
python -m app.cli scan-inbox
python -m app.cli process-pending
```

After processing, Emby should see `.strm` files inside:

```text
/mnt/16G/alldebrid-emby/library/Peliculas
/mnt/16G/alldebrid-emby/library/Series
```

## Emby Setup

Create two libraries in Emby:

1. Movies library
   Path: `/mnt/16G/alldebrid-emby/library/Peliculas`

2. TV Shows library
   Path: `/mnt/16G/alldebrid-emby/library/Series`

Recommended library types:

- `Movies` for `Peliculas`
- `TV Shows` for `Series`

If Emby runs in Docker, make sure those exact paths are mounted inside the Emby container.

## Installation Details

The installer script does the following:

- creates `.env` from `.env.example` if needed
- creates `config/config.yaml` from the example if needed
- fills in `ROOT_PATH`, movie path, series path, and optional API key
- creates a Python virtual environment
- installs dependencies
- initializes the project structure

Main install command:

```bash
bash scripts/install.sh
```

Optional variables:

```bash
ALLDEBRID_API_KEY="your_api_key"
ROOT_DIR="/mnt/16G/alldebrid-emby"
ALLDEBRID_AGENT="alldebrid-emby/1.0"
```

Example:

```bash
ALLDEBRID_API_KEY="your_api_key" ROOT_DIR="/mnt/16G/alldebrid-emby" bash scripts/install.sh
```

## Docker

Docker is optional. Native Python is the simplest way to start.

Build:

```bash
docker compose build
```

Initialize:

```bash
docker compose run --rm cli init
```

Test auth:

```bash
docker compose run --rm cli test-auth
```

Start the worker:

```bash
docker compose up -d worker
```

## Commands

Initialize folders and database:

```bash
python -m app.cli init
```

Test AllDebrid auth:

```bash
python -m app.cli test-auth
```

Add one magnet:

```bash
python -m app.cli add-magnet "magnet:?xt=urn:btih:..."
```

Add magnets from a file:

```bash
python -m app.cli add-magnets-file /path/to/magnets.txt
```

Scan the inbox:

```bash
python -m app.cli scan-inbox
```

Process pending magnets:

```bash
python -m app.cli process-pending
```

Process pending magnets without waiting for completion:

```bash
python -m app.cli process-pending --no-wait
```

Refresh expired or stale links:

```bash
python -m app.cli refresh-links
```

Rebuild missing `.strm` files and write a health report:

```bash
python -m app.cli reconcile
```

Show current database status:

```bash
python -m app.cli status
```

Run quick diagnostics:

```bash
python -m app.cli doctor
```

Run the automatic worker:

```bash
python -m app.cli worker
```

Shortcut wrapper:

```bash
bash scripts/run.sh process-pending
```

## Inbox Format

Supported inbox files:

- `.txt`
- `.json`

Inbox location:

```text
/mnt/16G/alldebrid-emby/data/inbox
```

Example `.txt`:

```text
magnet:?xt=urn:btih:...
magnet:?xt=urn:btih:...
```

Example `.json` array:

```json
[
  "magnet:?xt=urn:btih:...",
  "magnet:?xt=urn:btih:..."
]
```

Example `.json` object:

```json
{
  "magnets": [
    {"magnet": "magnet:?xt=urn:btih:..."},
    {"magnet": "magnet:?xt=urn:btih:..."}
  ]
}
```

Processed inbox files are renamed with a `.processed` suffix.

## Folder Layout

Generated structure:

```text
/mnt/16G/alldebrid-emby/
  app/
  config/
  data/
  data/inbox/
  data/cache/
  data/state/
  data/logs/
  library/
  library/Peliculas/
  library/Series/
  scripts/
  tests/
  docker/
  .env
  docker-compose.yml
  README.md
```

Typical output:

Series:

```text
library/Series/Show Name/Season 01/Show Name - s01e01.strm
```

Movies:

```text
library/Peliculas/Movie Title (2024)/Movie Title (2024).strm
```

## How Naming Works

The app uses practical heuristics:

- `S01E02` means TV episode
- `1x02` means TV episode
- `Season 1 Episode 2` or `Temporada 1 Episodio 2` means TV episode
- a detected year usually means movie
- release junk such as resolution, codec, and common tags is stripped when possible

Ambiguous cases are still kept, but they may be marked for manual review.

Review data is written to:

```text
data/state/incidents.csv
```

## State and Storage

Persistent storage uses SQLite:

```text
/mnt/16G/alldebrid-emby/data/state/alldebrid_emby.sqlite3
```

Stored data includes:

- source magnet
- BTIH hash when available
- local processing state
- remote AllDebrid magnet id
- detected files
- chosen stream URL
- `.strm` path
- timestamps
- errors

## Link Refresh

Direct links may expire over time.

This command:

```bash
python -m app.cli refresh-links
```

will:

1. validate existing links
2. mark stale links
3. regenerate them from AllDebrid
4. rewrite the `.strm` files in place

## Logs and Reports

Application log:

```text
data/logs/app.log
```

Incidents:

```text
data/state/incidents.csv
```

Health report:

```text
data/state/health-report.json
```

## Troubleshooting

`test-auth` fails:

- check `ALLDEBRID_API_KEY`
- verify outbound network access
- confirm your AllDebrid account is active

No `.strm` files appear:

- the magnet may still be processing
- the release may not contain supported video files
- check `data/logs/app.log`
- check `data/state/incidents.csv`

Emby does not recognize the media correctly:

- review the generated folder names
- run `python -m app.cli reconcile`
- verify Emby is pointed to the correct folders

Links stop working:

- run `python -m app.cli refresh-links`

## Tests

Run the included tests:

```bash
python -m unittest discover -s tests -v
```

## Design Choices

- SQLite instead of plain JSON for better persistence and future integrations
- Python CLI instead of a web app for easier homelab deployment
- a file-based library so Emby can read it directly
- small modules for easier maintenance and future extensions

## Known Limitations

- media classification is heuristic-based and not backed by TMDb or TVDB
- some AllDebrid payload details may change over time
- no advanced interactive file picker is included yet

## Future Ideas

- Sonarr integration
- Radarr integration
- n8n workflows
- systemd service example
- smarter media naming
- richer metadata support
