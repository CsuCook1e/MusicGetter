# MusicClimber

MusicClimber is a local web console for two crawler workflows:

- `musicdl` music search/download.
- `amemv-crawler` based Douyin user video discovery and audio extraction.

## Setup

If you clone this repository elsewhere, initialize the upstream crawler submodules first:

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

Douyin avatar and video-cover cache is stored under:

```text
D:\MusicClimber\cache\douyin
```

## Notes

- The upstream crawlers are referenced as the `musicdl` and `amemv-crawler` Git submodules.
- Use it only for learning, research, and media you are authorized to access or download.
- Some music clients require cookies, membership, or platform-specific network access.
- Douyin user search/video APIs can be rate-limited, require login, or trigger platform risk control. The web UI will surface those messages when they occur.
- The MediaCrawler-inspired Douyin fallback uses `vendor/mediacrawler/douyin.js` for `a_bogus` signing and keeps the upstream non-commercial learning license in `vendor/mediacrawler/LICENSE`.
- The Douyin legacy fallback uses the `amemv-crawler` signature script and needs Node.js available on `PATH`.
- The Douyin browser fallback uses Playwright with system Chrome/Edge when available, or Playwright Chromium if you install it with `.\.venv\Scripts\python.exe -m playwright install chromium`. Its browser profile is stored under `cache/douyin/browser-profile`.
- Use the Douyin sidebar login button to open a separate browser window and complete login manually. The app never asks for or types your credentials; it only reuses the saved browser profile.
- The Douyin workflow supports username, Douyin ID, profile URL, and share URL input. Cached avatars/covers can be cleared from the web UI.
