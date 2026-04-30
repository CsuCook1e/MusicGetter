# MusicClimber

MusicClimber is a local web console for the `musicdl` Python crawler/downloader.

## Setup

If you clone this repository elsewhere, initialize the upstream crawler submodule first:

```powershell
git submodule update --init --recursive
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:7860
```

Downloaded files are stored under:

```text
D:\MusicClimber\downloads
```

## Notes

- The upstream crawler is referenced as the `musicdl` Git submodule.
- Use it only for learning, research, and music you are authorized to access or download.
- Some clients require cookies, membership, or platform-specific network access. Those sources may return no results or fail to download without their own valid credentials.
