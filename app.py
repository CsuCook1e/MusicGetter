from __future__ import annotations

import sys
import time
import uuid
import traceback
from pathlib import Path
from threading import RLock, Thread

from flask import Flask, jsonify, render_template, request, send_file


ROOT = Path(__file__).resolve().parent
MUSICDL_REPO = ROOT / "musicdl"
DOWNLOAD_ROOT = ROOT / "downloads"

if str(MUSICDL_REPO) not in sys.path:
    sys.path.insert(0, str(MUSICDL_REPO))

DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

from musicdl import musicdl as musicdl_api  # noqa: E402
from musicdl.modules import MusicClientBuilder  # noqa: E402


app = Flask(__name__)

CACHE_LOCK = RLock()
SEARCH_CACHE: dict[str, dict] = {}
JOBS: dict[str, dict] = {}
FILE_TOKENS: dict[str, Path] = {}

DEFAULT_CLIENTS = [
    "MiguMusicClient",
    "NeteaseMusicClient",
    "QQMusicClient",
    "KuwoMusicClient",
    "QianqianMusicClient",
]

CLIENT_GROUPS = {
    "QQMusicClient": "华语平台",
    "KugouMusicClient": "华语平台",
    "StreetVoiceMusicClient": "华语平台",
    "SodaMusicClient": "华语平台",
    "FiveSingMusicClient": "华语平台",
    "NeteaseMusicClient": "华语平台",
    "QianqianMusicClient": "华语平台",
    "MiguMusicClient": "华语平台",
    "KuwoMusicClient": "华语平台",
    "BilibiliMusicClient": "华语平台",
    "YouTubeMusicClient": "全球/独立",
    "JooxMusicClient": "全球/独立",
    "AppleMusicClient": "全球/独立",
    "JamendoMusicClient": "全球/独立",
    "SoundCloudMusicClient": "全球/独立",
    "DeezerMusicClient": "全球/独立",
    "QobuzMusicClient": "全球/独立",
    "SpotifyMusicClient": "全球/独立",
    "TIDALMusicClient": "全球/独立",
    "FMAMusicClient": "全球/独立",
    "JioSaavnMusicClient": "全球/独立",
    "XimalayaMusicClient": "有声/播客",
    "LizhiMusicClient": "有声/播客",
    "QingtingMusicClient": "有声/播客",
    "LRTSMusicClient": "有声/播客",
    "ITunesMusicClient": "有声/播客",
    "MP3JuiceMusicClient": "聚合源",
    "TuneHubMusicClient": "聚合源",
    "GDStudioMusicClient": "聚合源",
    "MyFreeMP3MusicClient": "聚合源",
    "JBSouMusicClient": "聚合源",
    "MituMusicClient": "第三方站点",
    "BuguyyMusicClient": "第三方站点",
    "GequbaoMusicClient": "第三方站点",
    "YinyuedaoMusicClient": "第三方站点",
    "FLMP3MusicClient": "第三方站点",
    "FangpiMusicClient": "第三方站点",
    "FiveSongMusicClient": "第三方站点",
    "KKWSMusicClient": "第三方站点",
    "GequhaiMusicClient": "第三方站点",
    "LivePOOMusicClient": "第三方站点",
    "HTQYYMusicClient": "第三方站点",
    "JCPOOMusicClient": "第三方站点",
    "TwoT58MusicClient": "第三方站点",
    "ZhuolinMusicClient": "第三方站点",
}


def registered_clients() -> list[str]:
    return list(MusicClientBuilder.REGISTERED_MODULES.keys())


def display_name(client_name: str) -> str:
    return client_name.removesuffix("MusicClient")


def json_error(message: str, status_code: int = 400, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status_code


def normalize_clients(raw_clients) -> list[str]:
    valid_clients = set(registered_clients())
    clients = raw_clients if isinstance(raw_clients, list) else []
    clients = [str(client).strip() for client in clients if str(client).strip() in valid_clients]
    return clients or DEFAULT_CLIENTS


def clamp_limit(raw_value, default: int = 5) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 30))


def build_music_client(clients: list[str], limit_per_client: int) -> musicdl_api.MusicClient:
    init_cfg = {
        client: {
            "work_dir": str(DOWNLOAD_ROOT),
            "search_size_per_source": limit_per_client,
            "disable_print": True,
        }
        for client in clients
    }
    thread_cfg = {client: min(5, max(1, limit_per_client)) for client in clients}
    return musicdl_api.MusicClient(
        music_sources=clients,
        init_music_clients_cfg=init_cfg,
        clients_threadings=thread_cfg,
    )


def normalize_cover_url(cover_url):
    if not cover_url:
        return None
    text = str(cover_url)
    return text.replace("{w}", "300").replace("{h}", "300")


def has_valid_download_url(song_info) -> bool:
    try:
        return bool(song_info.with_valid_download_url)
    except Exception:
        return False


def serialize_song(song_info, item_id: str, parent_title: str | None = None) -> dict:
    source = getattr(song_info, "source", "") or ""
    root_source = getattr(song_info, "root_source", None)
    song_name = getattr(song_info, "song_name", None) or "Untitled"
    singers = getattr(song_info, "singers", None) or ""
    return {
        "id": item_id,
        "source": source,
        "sourceLabel": display_name(source) if source else "",
        "rootSource": root_source,
        "songName": str(song_name),
        "singers": str(singers),
        "album": str(getattr(song_info, "album", None) or ""),
        "ext": str(getattr(song_info, "ext", None) or "").lower(),
        "fileSize": str(getattr(song_info, "file_size", None) or ""),
        "duration": str(getattr(song_info, "duration", None) or ""),
        "bitrate": getattr(song_info, "bitrate", None),
        "codec": getattr(song_info, "codec", None),
        "coverUrl": normalize_cover_url(getattr(song_info, "cover_url", None)),
        "hasLyric": bool(getattr(song_info, "lyric", None)),
        "parentTitle": parent_title,
        "downloadable": has_valid_download_url(song_info),
    }


def flatten_results(search_results: dict) -> tuple[dict[str, object], list[dict]]:
    stored_items: dict[str, object] = {}
    public_items: list[dict] = []

    for source, song_infos in search_results.items():
        for song_info in song_infos or []:
            episodes = getattr(song_info, "episodes", None)
            if episodes:
                parent_title = getattr(song_info, "song_name", None) or source
                for episode in episodes:
                    item_id = uuid.uuid4().hex
                    if not getattr(episode, "source", None):
                        episode.source = source
                    stored_items[item_id] = episode
                    public_items.append(serialize_song(episode, item_id, parent_title=parent_title))
                continue

            item_id = uuid.uuid4().hex
            stored_items[item_id] = song_info
            public_items.append(serialize_song(song_info, item_id))

    return stored_items, public_items


def source_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        source = item.get("source") or "Unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def safe_register_file(path_value) -> dict | None:
    if not path_value:
        return None
    path = Path(path_value).resolve()
    download_root = DOWNLOAD_ROOT.resolve()
    if not path.exists() or not path.is_file():
        return None
    if download_root not in path.parents and path != download_root:
        return None

    token = uuid.uuid4().hex
    with CACHE_LOCK:
        FILE_TOKENS[token] = path
    return {
        "token": token,
        "name": path.name,
        "size": path.stat().st_size,
        "url": f"/files/{token}",
    }


def job_snapshot(job_id: str) -> dict | None:
    with CACHE_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def run_download_job(job_id: str, search: dict, selected_ids: list[str]):
    with CACHE_LOCK:
        JOBS[job_id].update({"status": "running", "startedAt": time.time(), "message": "正在下载"})

    selected_song_infos = [search["items"][item_id] for item_id in selected_ids if item_id in search["items"]]
    sources = sorted({getattr(song_info, "source", None) for song_info in selected_song_infos if getattr(song_info, "source", None)})

    try:
        music_client = build_music_client(sources, search.get("limitPerClient", 5))
        downloaded_song_infos = music_client.download(selected_song_infos)
        files = []
        for song_info in downloaded_song_infos:
            file_info = safe_register_file(getattr(song_info, "save_path", None))
            if file_info:
                file_info.update(
                    {
                        "source": getattr(song_info, "source", None),
                        "songName": getattr(song_info, "song_name", None),
                        "singers": getattr(song_info, "singers", None),
                        "ext": getattr(song_info, "ext", None),
                    }
                )
                files.append(file_info)

        status = "complete" if files else "empty"
        message = "下载完成" if files else "下载结束，但没有返回可用文件"
        with CACHE_LOCK:
            JOBS[job_id].update(
                {
                    "status": status,
                    "finishedAt": time.time(),
                    "message": message,
                    "files": files,
                }
            )
    except Exception as exc:
        with CACHE_LOCK:
            JOBS[job_id].update(
                {
                    "status": "error",
                    "finishedAt": time.time(),
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                }
            )


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "downloadRoot": str(DOWNLOAD_ROOT)})


@app.get("/api/clients")
def clients():
    payload = []
    for name in registered_clients():
        payload.append(
            {
                "name": name,
                "label": display_name(name),
                "group": CLIENT_GROUPS.get(name, "其他"),
                "default": name in DEFAULT_CLIENTS,
            }
        )
    return jsonify({"ok": True, "clients": payload, "defaults": DEFAULT_CLIENTS})


@app.post("/api/search")
def search():
    payload = request.get_json(silent=True) or {}
    keyword = str(payload.get("keyword", "")).strip()
    if not keyword:
        return json_error("请输入搜索关键词")

    selected_clients = normalize_clients(payload.get("clients"))
    limit_per_client = clamp_limit(payload.get("limitPerClient", 5))

    try:
        music_client = build_music_client(selected_clients, limit_per_client)
        search_results = music_client.search(keyword=keyword)
        stored_items, public_items = flatten_results(search_results)
    except Exception as exc:
        return json_error("搜索失败", 500, detail=str(exc), traceback=traceback.format_exc(limit=8))

    search_id = uuid.uuid4().hex
    with CACHE_LOCK:
        SEARCH_CACHE[search_id] = {
            "items": stored_items,
            "keyword": keyword,
            "clients": selected_clients,
            "limitPerClient": limit_per_client,
            "createdAt": time.time(),
        }

    return jsonify(
        {
            "ok": True,
            "searchId": search_id,
            "keyword": keyword,
            "clients": selected_clients,
            "results": public_items,
            "counts": source_counts(public_items),
        }
    )


@app.post("/api/download")
def download():
    payload = request.get_json(silent=True) or {}
    search_id = str(payload.get("searchId", "")).strip()
    selected_ids = payload.get("ids") if isinstance(payload.get("ids"), list) else []
    selected_ids = [str(item_id) for item_id in selected_ids]

    if not search_id:
        return json_error("缺少 searchId")
    if not selected_ids:
        return json_error("请选择要下载的音乐")

    with CACHE_LOCK:
        search_obj = SEARCH_CACHE.get(search_id)
        if not search_obj:
            return json_error("搜索结果已失效，请重新搜索", 404)
        valid_ids = [item_id for item_id in selected_ids if item_id in search_obj["items"]]
        if not valid_ids:
            return json_error("没有可下载的选中项")

        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "message": "已加入下载队列",
            "createdAt": time.time(),
            "files": [],
        }

    worker = Thread(target=run_download_job, args=(job_id, search_obj, valid_ids), daemon=True)
    worker.start()
    return jsonify({"ok": True, "job": job_snapshot(job_id)})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = job_snapshot(job_id)
    if not job:
        return json_error("下载任务不存在", 404)
    return jsonify({"ok": True, "job": job})


@app.get("/api/downloads")
def downloads():
    with CACHE_LOCK:
        files = [
            {
                "token": token,
                "name": path.name,
                "size": path.stat().st_size if path.exists() else 0,
                "url": f"/files/{token}",
            }
            for token, path in FILE_TOKENS.items()
            if path.exists()
        ]
    return jsonify({"ok": True, "files": files})


@app.get("/files/<token>")
def file_by_token(token: str):
    with CACHE_LOCK:
        path = FILE_TOKENS.get(token)
    if not path or not path.exists():
        return json_error("文件不存在或服务已重启", 404)
    return send_file(path, as_attachment=True, download_name=path.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False, threaded=True)
