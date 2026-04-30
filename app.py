from __future__ import annotations

import sys
import time
import uuid
import base64
import html
import hashlib
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import traceback
import urllib.parse
from pathlib import Path
from threading import Lock, RLock, Thread

import requests
from pathvalidate import sanitize_filename
from flask import Flask, jsonify, render_template, request, send_file


ROOT = Path(__file__).resolve().parent
MUSICDL_REPO = ROOT / "musicdl"
AMEMV_REPO = ROOT / "amemv-crawler"
DOWNLOAD_ROOT = ROOT / "downloads"
DOUYIN_VIDEO_ROOT = DOWNLOAD_ROOT / "douyin" / "videos"
DOUYIN_AUDIO_ROOT = DOWNLOAD_ROOT / "douyin" / "audios"
DOUYIN_CACHE_ROOT = ROOT / "cache" / "douyin"
DOUYIN_AVATAR_CACHE = DOUYIN_CACHE_ROOT / "avatars"
DOUYIN_COVER_CACHE = DOUYIN_CACHE_ROOT / "covers"
DOUYIN_BROWSER_PROFILE = DOUYIN_CACHE_ROOT / "browser-profile"
MEDIACRAWLER_DOUYIN_SIGN_JS = ROOT / "vendor" / "mediacrawler" / "douyin.js"
MEDIACRAWLER_VERIFY_FP = "verify_ma3hrt8n_q2q2HyYA_uLyO_4N6D_BLvX_E2LgoGmkA1BU"

if str(MUSICDL_REPO) not in sys.path:
    sys.path.insert(0, str(MUSICDL_REPO))

DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
DOUYIN_VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
DOUYIN_AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
DOUYIN_AVATAR_CACHE.mkdir(parents=True, exist_ok=True)
DOUYIN_COVER_CACHE.mkdir(parents=True, exist_ok=True)

from musicdl import musicdl as musicdl_api  # noqa: E402
from musicdl.modules import MusicClientBuilder  # noqa: E402


app = Flask(__name__)

CACHE_LOCK = RLock()
DOUYIN_BROWSER_LOCK = Lock()
SEARCH_CACHE: dict[str, dict] = {}
DOUYIN_USER_CACHE: dict[str, dict] = {}
DOUYIN_VIDEO_CACHE: dict[str, dict] = {}
JOBS: dict[str, dict] = {}
FILE_TOKENS: dict[str, Path] = {}
DOUYIN_LOGIN_THREAD: Thread | None = None
DOUYIN_LOGIN_STATE: dict = {
    "running": False,
    "loggedIn": False,
    "startedAt": None,
    "checkedAt": None,
    "finishedAt": None,
    "message": "未检测登录状态",
    "profileRoot": str(DOUYIN_BROWSER_PROFILE),
}

DEFAULT_CLIENTS = [
    "MiguMusicClient",
    "NeteaseMusicClient",
    "QQMusicClient",
    "KuwoMusicClient",
    "QianqianMusicClient",
]

DOUYIN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": "https://www.douyin.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}

DOUYIN_MOBILE_HEADERS = {
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) "
        "AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 "
        "Mobile/15A372 Safari/604.1"
    ),
}

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


def first_url(value) -> str | None:
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, list):
        for item in value:
            if url := first_url(item):
                return url
    if isinstance(value, dict):
        for key in ("url_list", "urls", "url", "uri"):
            if key in value and (url := first_url(value[key])):
                return url
    return None


def cache_file_count_and_size(directory: Path) -> tuple[int, int]:
    if not directory.exists():
        return 0, 0
    files = [path for path in directory.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def douyin_cache_stats() -> dict:
    avatar_count, avatar_bytes = cache_file_count_and_size(DOUYIN_AVATAR_CACHE)
    cover_count, cover_bytes = cache_file_count_and_size(DOUYIN_COVER_CACHE)
    return {
        "avatarCount": avatar_count,
        "coverCount": cover_count,
        "fileCount": avatar_count + cover_count,
        "bytes": avatar_bytes + cover_bytes,
    }


def cache_category_dir(category: str) -> Path:
    if category == "avatars":
        return DOUYIN_AVATAR_CACHE
    if category == "covers":
        return DOUYIN_COVER_CACHE
    raise ValueError("invalid cache category")


def guess_image_ext(url: str, content_type: str | None = None) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "image/jpeg":
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return guessed
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"


def cache_remote_image(url: str | None, category: str, key: str) -> str | None:
    if not url:
        return None
    cache_dir = cache_category_dir(category)
    url = str(url).replace("{w}", "300").replace("{h}", "300")
    digest = hashlib.sha256(f"{category}:{key}:{url}".encode("utf-8")).hexdigest()
    for existing in cache_dir.glob(f"{digest}.*"):
        if existing.is_file() and existing.stat().st_size > 0:
            return f"/cache/douyin/{category}/{existing.name}"
    try:
        resp = requests.get(url, headers=DOUYIN_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type") or ""
        content = resp.content or b""
        signature = content[:16]
        looks_like_image = (
            content_type.startswith("image/")
            or signature.startswith(b"\xff\xd8\xff")
            or signature.startswith(b"\x89PNG\r\n\x1a\n")
            or signature.startswith(b"RIFF")
            or signature.startswith(b"GIF8")
        )
        if not looks_like_image:
            return url
        ext = guess_image_ext(resp.url, content_type)
        path = cache_dir / f"{digest}{ext}"
        path.write_bytes(content)
        return f"/cache/douyin/{category}/{path.name}"
    except Exception:
        return url


def iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def iter_douyin_payload_dicts(value):
    for node in iter_dicts(value):
        yield node
        if not isinstance(node, dict):
            continue
        for raw_key in ("raw_data", "rawData", "data"):
            raw_value = node.get(raw_key)
            if not isinstance(raw_value, str):
                continue
            raw_text = raw_value.strip()
            if not raw_text or raw_text[0] not in "[{":
                continue
            try:
                parsed = json.loads(raw_text)
            except Exception:
                continue
            yield from iter_dicts(parsed)


def compact_text(value, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() not in {"none", "null"} else fallback


def douyin_device_id() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(19))


def douyin_safe_json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        text = resp.text.strip()
        return json.loads(text) if text else {}


def douyin_get_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 18) -> dict:
    resp = requests.get(url, params=params, headers=headers or DOUYIN_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return douyin_safe_json(resp)


def resolve_douyin_url(text: str) -> str:
    url_match = re.search(r"https?://[^\s，,]+", text)
    url = url_match.group(0) if url_match else text.strip()
    if not re.search(r"(douyin\.com|iesdouyin\.com|amemv\.com|tiktok\.com)", url):
        return url
    for _ in range(4):
        try:
            resp = requests.get(url, headers=DOUYIN_MOBILE_HEADERS, allow_redirects=False, timeout=12)
        except Exception:
            break
        location = resp.headers.get("Location")
        if resp.status_code in {301, 302, 303, 307, 308} and location:
            url = urllib.parse.urljoin(url, location)
            continue
        break
    return url


def extract_douyin_identity(text: str) -> dict:
    resolved = resolve_douyin_url(text)
    merged = f"{text} {resolved}"
    sec_uid = None
    user_id = None
    raw_text = text.strip()
    if re.fullmatch(r"MS4wLjAB[A-Za-z0-9_-]{20,}", raw_text):
        sec_uid = raw_text
    if match := re.search(r"/user/([^/?#\s]+)", merged):
        sec_uid = urllib.parse.unquote(match.group(1))
    if match := re.search(r"(?:sec_uid|sec_user_id)=([^&#\s]+)", merged):
        sec_uid = urllib.parse.unquote(match.group(1))
    if match := re.search(r"/share/user/(\d+)", merged):
        user_id = match.group(1)
    if match := re.search(r"(?:user_id|uid)=([0-9]+)", merged):
        user_id = user_id or match.group(1)
    return {"inputUrl": resolved, "secUid": sec_uid, "userId": user_id}


def serialize_douyin_user(raw_user: dict, source: str) -> dict | None:
    user = raw_user.get("user_info") if isinstance(raw_user.get("user_info"), dict) else raw_user
    user = user.get("user") if isinstance(user.get("user"), dict) else user
    sec_uid = user.get("sec_uid") or user.get("secUid") or user.get("sec_user_id")
    uid = user.get("uid") or user.get("user_id") or user.get("id")
    nickname = compact_text(user.get("nickname") or user.get("name") or raw_user.get("nickname"))
    unique_id = compact_text(user.get("unique_id") or user.get("display_id"))
    short_id = compact_text(user.get("short_id"))
    douyin_id = unique_id or short_id
    if not (sec_uid or uid or nickname):
        return None
    profile_url = f"https://www.douyin.com/user/{sec_uid}" if sec_uid else None
    stats = user.get("custom_verify") or user.get("enterprise_verify_reason") or user.get("signature")
    avatar_url = first_url(user.get("avatar_thumb") or user.get("avatar_medium") or user.get("avatar_larger"))
    cache_key = str(sec_uid or uid or douyin_id or nickname)
    return {
        "id": uuid.uuid4().hex,
        "uid": str(uid or ""),
        "secUid": str(sec_uid or ""),
        "nickname": nickname or unique_id or str(uid or sec_uid or "Douyin User"),
        "uniqueId": unique_id,
        "shortId": short_id,
        "douyinId": douyin_id,
        "signature": compact_text(stats),
        "avatar": cache_remote_image(avatar_url, "avatars", cache_key),
        "avatarRemote": avatar_url,
        "followerCount": user.get("follower_count") or user.get("followerCount"),
        "profileUrl": profile_url,
        "inputUrl": profile_url,
        "source": source,
    }


def dedupe_douyin_users(users: list[dict]) -> list[dict]:
    deduped, seen = [], set()
    for user in users:
        key = user.get("secUid") or user.get("uid") or user.get("profileUrl") or user.get("nickname")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(user)
    return deduped


def actionable_douyin_user(user: dict) -> bool:
    return bool(user.get("secUid") or (user.get("uid") and (user.get("inputUrl") or user.get("profileUrl"))))


def normalize_douyin_id_query(keyword: str) -> str | None:
    text = keyword.strip()
    if re.search(r"https?://", text):
        return None
    text = re.sub(r"^(抖音号|douyin|douyin_id|id)\s*[:：]?\s*", "", text, flags=re.I).strip()
    text = text.removeprefix("@").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]{2,40}", text):
        return text
    return None


def rank_douyin_users(users: list[dict], keyword: str) -> list[dict]:
    needle = (normalize_douyin_id_query(keyword) or keyword).lower().strip()
    def score(user: dict) -> tuple[int, str]:
        fields = [
            str(user.get("douyinId") or ""),
            str(user.get("uniqueId") or ""),
            str(user.get("shortId") or ""),
            str(user.get("nickname") or ""),
            str(user.get("uid") or ""),
        ]
        lowered = [field.lower() for field in fields if field]
        if needle and any(field == needle for field in lowered):
            return (0, user.get("nickname") or "")
        if needle and any(needle in field for field in lowered):
            return (1, user.get("nickname") or "")
        return (2, user.get("nickname") or "")
    return sorted(users, key=score)


def merge_douyin_user(base: dict, enriched: dict, *, prefer_enriched_profile: bool = False) -> dict:
    merged = dict(base)
    for key in (
        "uid",
        "secUid",
        "nickname",
        "uniqueId",
        "shortId",
        "douyinId",
        "signature",
        "avatar",
        "avatarRemote",
        "followerCount",
        "profileUrl",
        "inputUrl",
    ):
        value = enriched.get(key)
        if value is None or value == "" or value == []:
            continue
        if prefer_enriched_profile or key in {"avatar", "avatarRemote", "followerCount", "signature"} or not merged.get(key):
            merged[key] = value
    sources = [str(item) for item in (base.get("source"), enriched.get("source")) if item]
    if sources:
        merged["source"] = " + ".join(dict.fromkeys(sources))
    return merged


def fetch_douyin_user_info_by_dy_data(sec_uid: str) -> tuple[dict | None, list[str]]:
    if not sec_uid:
        return None, ["dy-data-user-info: missing secUid"]
    notes = []
    params = {"sec_uid": sec_uid}
    headers = dict(DOUYIN_HEADERS)
    headers["referer"] = "https://www.iesdouyin.com/"
    for host in ("https://www.iesdouyin.com", "https://www.douyin.com"):
        try:
            data = douyin_get_json(f"{host}/web/api/v2/user/info/", params=params, headers=headers)
        except Exception as exc:
            notes.append(f"dy-data-user-info({urllib.parse.urlparse(host).netloc}): {exc}")
            continue
        status_code = data.get("status_code")
        if status_code not in {0, None}:
            notes.append(f"dy-data-user-info({urllib.parse.urlparse(host).netloc}): {data.get('status_msg') or status_code}")
            continue
        candidate = serialize_douyin_user(data, source="dy-data-user-info")
        if candidate:
            return candidate, notes
        notes.append(f"dy-data-user-info({urllib.parse.urlparse(host).netloc}): no user_info")
    return None, notes


def enrich_douyin_users_by_dy_data(users: list[dict], keyword: str, limit: int) -> tuple[list[dict], list[str]]:
    enriched_users, notes = [], []
    for user in dedupe_douyin_users(users)[:limit]:
        sec_uid = user.get("secUid")
        if not sec_uid:
            identity = extract_douyin_identity(user.get("inputUrl") or user.get("profileUrl") or "")
            sec_uid = identity.get("secUid")
            if sec_uid:
                user["secUid"] = sec_uid
                user["profileUrl"] = f"https://www.douyin.com/user/{sec_uid}"
        if not sec_uid:
            enriched_users.append(user)
            continue
        info_user, info_notes = fetch_douyin_user_info_by_dy_data(sec_uid)
        if info_user:
            prefer_profile = user.get("source") in {"search-engine", "direct-url"} or user.get("nickname") in {keyword, "抖音用户"}
            enriched_users.append(merge_douyin_user(user, info_user, prefer_enriched_profile=prefer_profile))
        else:
            notes.extend(info_notes)
            enriched_users.append(user)
    return rank_douyin_users(dedupe_douyin_users(enriched_users), keyword)[:limit], notes


def extract_douyin_search_state(html_text: str) -> list[dict]:
    users = []
    for pattern in (
        r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
        r'<script id="SIGI_STATE" type="application/json">(.*?)</script>',
    ):
        for raw in re.findall(pattern, html_text, flags=re.S):
            try:
                payload = urllib.parse.unquote(raw)
                data = json.loads(payload)
            except Exception:
                continue
            for node in iter_dicts(data):
                candidate = serialize_douyin_user(node, source="search-page")
                if candidate and (candidate.get("secUid") or candidate.get("uid")):
                    users.append(candidate)
    for match in re.finditer(r'"sec_uid"\s*:\s*"([^"]+)".{0,800}?"nickname"\s*:\s*"([^"]*)"', html_text, flags=re.S):
        try:
            sec_uid = json.loads(f'"{match.group(1)}"')
            nickname = json.loads(f'"{match.group(2)}"')
        except Exception:
            sec_uid, nickname = match.group(1), match.group(2)
        candidate = serialize_douyin_user({"sec_uid": sec_uid, "nickname": nickname}, source="search-page-regex")
        if candidate:
            users.append(candidate)
    return dedupe_douyin_users(users)


def search_douyin_by_search_page(keyword: str, limit: int) -> tuple[list[dict], list[str]]:
    notes = []
    url = f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}"
    try:
        resp = requests.get(url, params={"type": "user"}, headers=DOUYIN_HEADERS, timeout=18)
        resp.raise_for_status()
    except Exception as exc:
        return [], [f"search-page: {exc}"]
    users = extract_douyin_search_state(resp.text)
    if not users:
        notes.append("search-page: no user state")
    return users[:limit], notes


def unwrap_search_result_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query_params:
        return urllib.parse.unquote(query_params.get("uddg", [""])[0])
    if "url" in query_params:
        return urllib.parse.unquote(query_params.get("url", [""])[0])
    if parsed.netloc.endswith("bing.com") and "u" in query_params:
        encoded = query_params.get("u", [""])[0]
        if encoded.startswith("a1"):
            raw = encoded[2:]
            raw += "=" * (-len(raw) % 4)
            try:
                return urllib.parse.unquote(base64.urlsafe_b64decode(raw).decode("utf-8"))
            except Exception:
                return url
    return url


def douyin_users_from_links(text: str, keyword: str, source: str, *, douyin_id: str | None = None) -> list[dict]:
    users = []
    links = set(re.findall(r"https?://[^\s\"'<>]+", text))
    for sec_uid in re.findall(r"/user/([A-Za-z0-9_-]{20,})", text):
        links.add(f"https://www.douyin.com/user/{sec_uid}")
    for raw_url in links:
        url = html.unescape(raw_url).rstrip("),.;")
        if not re.search(r"(douyin\.com/user/|iesdouyin\.com/share/user/|v\.douyin\.com/)", url):
            continue
        identity = extract_douyin_identity(url)
        if not (identity.get("secUid") or identity.get("userId")):
            continue
        if identity.get("secUid", "").lower() in {"self", "login"}:
            continue
        users.append(
            {
                "id": uuid.uuid4().hex,
                "uid": identity.get("userId") or "",
                "secUid": identity.get("secUid") or "",
                "nickname": keyword,
                "uniqueId": douyin_id or "",
                "shortId": "",
                "douyinId": douyin_id or "",
                "signature": "页面候选结果",
                "avatar": None,
                "avatarRemote": None,
                "followerCount": None,
                "profileUrl": identity["inputUrl"],
                "inputUrl": identity["inputUrl"],
                "source": source,
            }
        )
    return dedupe_douyin_users(users)


def extract_douyin_awemes_from_payload(data: dict) -> list[dict]:
    awemes = []
    if isinstance(data.get("aweme_list"), list):
        awemes.extend([item for item in data["aweme_list"] if isinstance(item, dict)])
    if isinstance(data.get("aweme_detail"), dict):
        awemes.append(data["aweme_detail"])
    if isinstance(data.get("item_list"), list):
        awemes.extend([item for item in data["item_list"] if isinstance(item, dict)])
    for node in iter_douyin_payload_dicts(data):
        if isinstance(node, dict) and node.get("aweme_id") and isinstance(node.get("video"), dict):
            awemes.append(node)
    deduped, seen = [], set()
    for aweme in awemes:
        key = str(aweme.get("aweme_id") or aweme.get("group_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(aweme)
    return deduped


def extract_douyin_awemes_from_html(html_text: str) -> list[dict]:
    awemes = []
    for pattern in (
        r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
        r'<script id="SIGI_STATE" type="application/json">(.*?)</script>',
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
    ):
        for raw in re.findall(pattern, html_text, flags=re.S):
            try:
                payload = urllib.parse.unquote(raw)
                data = json.loads(payload)
            except Exception:
                continue
            awemes.extend(extract_douyin_awemes_from_payload(data))
    deduped, seen = [], set()
    for aweme in awemes:
        key = str(aweme.get("aweme_id") or aweme.get("group_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(aweme)
    return deduped


def browser_risk_note(page) -> str | None:
    try:
        text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return None
    risk_words = ("验证", "验证码", "请完成安全验证", "登录后", "扫码登录", "环境异常")
    for word in risk_words:
        if word in text:
            return f"browser: 页面提示“{word}”，需要人工处理登录/验证后再试"
    return None


def find_system_chromium() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def mediacrawler_web_id() -> str:
    def replace_char(value):
        if value is not None:
            return str(value ^ (int(16 * random.random()) >> (value // 4)))
        return "10000000-1000-4000-8000-100000000000"

    web_id = "".join(replace_char(int(ch)) if ch in "018" else ch for ch in replace_char(None))
    return web_id.replace("-", "")[:19]


def douyin_cookie_header(context) -> str:
    try:
        cookies = context.cookies(["https://www.douyin.com", "https://douyin.com"])
    except Exception:
        return ""
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies if cookie.get("name"))


def douyin_local_storage(page) -> dict:
    try:
        return page.evaluate("() => Object.assign({}, window.localStorage)") or {}
    except Exception:
        return {}


def mediacrawler_common_params(local_storage: dict) -> dict:
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "version_code": "190600",
        "version_name": "19.6.0",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "cookie_enabled": "true",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "124.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "8",
        "device_memory": "8",
        "engine_version": "124.0.0.0",
        "platform": "PC",
        "screen_width": "1365",
        "screen_height": "768",
        "effective_type": "4g",
        "round_trip_time": "50",
        "webid": mediacrawler_web_id(),
        "msToken": local_storage.get("xmst") or local_storage.get("msToken") or "",
    }


def generate_mediacrawler_a_bogus(query_string: str, user_agent: str, *, reply: bool = False) -> str:
    if not MEDIACRAWLER_DOUYIN_SIGN_JS.exists():
        raise RuntimeError("MediaCrawler douyin.js not found")
    sign_name = "sign_reply" if reply else "sign_datail"
    code = (
        "const fs = require('fs');"
        f"eval(fs.readFileSync({json.dumps(str(MEDIACRAWLER_DOUYIN_SIGN_JS))}, 'utf8'));"
        f"process.stdout.write({sign_name}({json.dumps(query_string)}, {json.dumps(user_agent)}));"
    )
    result = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=10, check=True)
    return result.stdout.strip()


def mediacrawler_douyin_get(
    page,
    context,
    uri: str,
    params: dict,
    *,
    referer: str,
    sign: bool = True,
) -> dict:
    user_agent = DOUYIN_HEADERS["user-agent"]
    request_params = dict(params)
    request_params.update(mediacrawler_common_params(douyin_local_storage(page)))
    query_string = urllib.parse.urlencode(request_params)
    if sign and "/v1/web/general/search" not in uri:
        request_params["a_bogus"] = generate_mediacrawler_a_bogus(query_string, user_agent)
    headers = dict(DOUYIN_HEADERS)
    headers.update(
        {
            "origin": "https://www.douyin.com",
            "referer": referer,
            "user-agent": user_agent,
        }
    )
    if cookie_header := douyin_cookie_header(context):
        headers["cookie"] = cookie_header
    resp = requests.get(f"https://www.douyin.com{uri}", params=request_params, headers=headers, timeout=20)
    if not resp.text.strip():
        raise RuntimeError("empty response")
    return douyin_safe_json(resp)


def login_status_from_browser(page, context) -> dict:
    local_storage = douyin_local_storage(page)
    cookie_map = {cookie["name"]: cookie["value"] for cookie in context.cookies(["https://www.douyin.com", "https://douyin.com"])}
    logged_in = local_storage.get("HasUserLogin") == "1" or cookie_map.get("LOGIN_STATUS") == "1"
    return {
        "loggedIn": logged_in,
        "hasXmst": bool(local_storage.get("xmst")),
        "hasLoginCookie": bool(cookie_map.get("LOGIN_STATUS")),
        "profileRoot": str(DOUYIN_BROWSER_PROFILE),
    }


def update_douyin_login_state(**updates):
    with CACHE_LOCK:
        DOUYIN_LOGIN_STATE.update(updates)


def douyin_login_snapshot() -> dict:
    with CACHE_LOCK:
        return dict(DOUYIN_LOGIN_STATE)


def run_douyin_login_window(timeout_seconds: int = 600):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        update_douyin_login_state(
            running=False,
            loggedIn=False,
            finishedAt=time.time(),
            message=f"Playwright 不可用: {exc}",
        )
        return

    if not DOUYIN_BROWSER_LOCK.acquire(blocking=False):
        update_douyin_login_state(
            running=False,
            finishedAt=time.time(),
            message="浏览器 profile 正在被搜索/抓取任务使用，请稍后再打开登录窗口",
        )
        return

    DOUYIN_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    browser_executable = find_system_chromium()
    update_douyin_login_state(
        running=True,
        startedAt=time.time(),
        finishedAt=None,
        message="登录窗口已打开，请在浏览器中完成抖音登录/验证",
    )
    try:
        with sync_playwright() as playwright:
            launch_options = {
                "user_data_dir": str(DOUYIN_BROWSER_PROFILE),
                "headless": False,
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "viewport": {"width": 1365, "height": 768},
                "user_agent": DOUYIN_HEADERS["user-agent"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            }
            if browser_executable:
                launch_options["executable_path"] = str(browser_executable)
            context = playwright.chromium.launch_persistent_context(**launch_options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(15000)
                page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)
                for locator in (
                    page.get_by_text("登录", exact=True),
                    page.locator("button:has-text('登录')"),
                    page.locator("[role='button']:has-text('登录')"),
                ):
                    try:
                        locator.first.click(timeout=3000)
                        break
                    except Exception:
                        continue
                deadline = time.time() + timeout_seconds
                while time.time() < deadline:
                    status = login_status_from_browser(page, context)
                    update_douyin_login_state(
                        checkedAt=time.time(),
                        loggedIn=status["loggedIn"],
                        hasXmst=status["hasXmst"],
                        hasLoginCookie=status["hasLoginCookie"],
                        message="已检测到登录态" if status["loggedIn"] else "等待你在浏览器中完成登录",
                    )
                    if status["loggedIn"]:
                        break
                    page.wait_for_timeout(2500)
            finally:
                context.close()
        final_state = douyin_login_snapshot()
        update_douyin_login_state(
            running=False,
            finishedAt=time.time(),
            message="登录态已保存到浏览器 profile" if final_state.get("loggedIn") else "登录窗口已关闭，未检测到登录态",
        )
    except Exception as exc:
        update_douyin_login_state(
            running=False,
            finishedAt=time.time(),
            message=f"登录窗口异常: {str(exc).splitlines()[0]}",
        )
    finally:
        DOUYIN_BROWSER_LOCK.release()


def run_douyin_browser_task(label: str, task):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, [f"{label}: Playwright 未安装，需先安装 playwright 并执行 playwright install chromium"]

    if not DOUYIN_BROWSER_LOCK.acquire(timeout=20):
        return None, [f"{label}: 浏览器 profile 正在被登录窗口或其他抓取任务使用，请稍后重试"]

    DOUYIN_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    headless = os.environ.get("DOUYIN_BROWSER_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}
    browser_executable = find_system_chromium()
    try:
        result = None
        notes = []
        with sync_playwright() as playwright:
            launch_options = {
                "user_data_dir": str(DOUYIN_BROWSER_PROFILE),
                "headless": headless,
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "viewport": {"width": 1365, "height": 768},
                "user_agent": DOUYIN_HEADERS["user-agent"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            }
            if browser_executable:
                launch_options["executable_path"] = str(browser_executable)
            context = playwright.chromium.launch_persistent_context(**launch_options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(15000)
                page.set_extra_http_headers({"Accept-Language": "zh-CN,zh;q=0.9"})
                result = task(page, context)
            finally:
                try:
                    context.close()
                except Exception as close_exc:
                    notes.append(f"{label}-close: {str(close_exc).splitlines()[0]}")
        return result, notes
    except Exception as exc:
        message = str(exc).splitlines()[0]
        if "Executable doesn't exist" in str(exc) or "Please run" in str(exc):
            message = "Chromium 未安装，需执行 playwright install chromium"
        return None, [f"{label}: {message}"]
    finally:
        DOUYIN_BROWSER_LOCK.release()


def search_douyin_by_browser(keyword: str, limit: int) -> tuple[list[dict], list[str]]:
    if limit <= 0:
        return [], []

    def task(page, _context):
        users, notes, payloads = [], [], []

        def on_response(response):
            if not any(
                fragment in response.url
                for fragment in ("/aweme/v1/web/general/search/single/", "/aweme/v1/web/query/user/")
            ):
                return
            try:
                payloads.append((response.url, response.json()))
            except Exception as exc:
                notes.append(f"browser-search-response: {exc}")

        page.on("response", on_response)
        page.goto(
            f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}?type=user",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        page.wait_for_timeout(4000)
        for _ in range(4):
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(900)

        for url, data in payloads:
            status_code = data.get("status_code") if isinstance(data, dict) else None
            if status_code not in {0, None}:
                notes.append(f"browser-search: {data.get('status_msg') or status_code}")
            for node in iter_douyin_payload_dicts(data):
                candidate = serialize_douyin_user(node, source="browser-search")
                if candidate:
                    users.append(candidate)

        content = page.content()
        users.extend(extract_douyin_search_state(content))
        users.extend(douyin_users_from_links(content, keyword, "browser-dom"))
        if note := browser_risk_note(page):
            notes.append(note)
        if not users:
            notes.append("browser-search: no user result")
        actionable = [user for user in dedupe_douyin_users(users) if actionable_douyin_user(user)]
        if users and not actionable:
            notes.append("browser-search: results missing secUid")
        return {"users": actionable[:limit], "notes": notes}

    result, run_notes = run_douyin_browser_task("browser-search", task)
    if not result:
        return [], run_notes
    return result["users"], run_notes + result["notes"]


def search_douyin_by_mediacrawler(keyword: str, limit: int) -> tuple[list[dict], list[str]]:
    if limit <= 0:
        return [], []

    def task(page, context):
        notes, users = [], []
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        params = {
            "search_channel": "aweme_user_web",
            "enable_history": "1",
            "keyword": keyword,
            "search_source": "tab_search",
            "query_correct_type": "1",
            "is_filter_search": "0",
            "from_group_id": "7378810571505847586",
            "offset": "0",
            "count": str(min(max(limit, 1), 15)),
            "need_filter_settings": "1",
            "list_type": "multi",
            "search_id": "",
        }
        referer = f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}?type=user"
        try:
            data = mediacrawler_douyin_get(
                page,
                context,
                "/aweme/v1/web/general/search/single/",
                params,
                referer=referer,
                sign=False,
            )
        except Exception as exc:
            return {"users": [], "notes": [f"mediacrawler-search: {exc}"]}

        status_code = data.get("status_code")
        if status_code not in {0, None}:
            notes.append(f"mediacrawler-search: {data.get('status_msg') or status_code}")
        for node in iter_douyin_payload_dicts(data):
            candidate = serialize_douyin_user(node, source="mediacrawler-search")
            if candidate:
                users.append(candidate)
        if note := browser_risk_note(page):
            notes.append(note)
        users = [user for user in dedupe_douyin_users(users) if actionable_douyin_user(user)]
        if not users:
            notes.append("mediacrawler-search: no actionable user result")
        return {"users": users[:limit], "notes": notes}

    result, run_notes = run_douyin_browser_task("mediacrawler-search", task)
    if not result:
        return [], run_notes
    return result["users"], run_notes + result["notes"]


def search_douyin_by_web_api(keyword: str, limit: int) -> tuple[list[dict], list[str]]:
    users, notes = [], []
    device_id = douyin_device_id()
    session = requests.Session()
    endpoints = [
        (
            "query-user",
            "https://www.douyin.com/aweme/v1/web/query/user/",
            {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "keyword": keyword,
                "offset": "0",
                "count": str(limit),
                "device_id": device_id,
                "webid": device_id,
            },
        ),
        (
            "general-search",
            "https://www.douyin.com/aweme/v1/web/general/search/single/",
            {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "keyword": keyword,
                "offset": "0",
                "count": str(limit),
                "search_channel": "aweme_user_web",
                "device_id": device_id,
                "webid": device_id,
            },
        ),
    ]
    for label, url, params in endpoints:
        try:
            resp = session.get(url, params=params, headers=DOUYIN_HEADERS, timeout=15)
            data = douyin_safe_json(resp)
        except Exception as exc:
            notes.append(f"{label}: {exc}")
            continue
        status_code = data.get("status_code")
        if status_code not in {0, None}:
            notes.append(f"{label}: {data.get('status_msg') or status_code}")
        for node in iter_douyin_payload_dicts(data):
            candidate = serialize_douyin_user(node, source=label)
            if candidate:
                users.append(candidate)
    return dedupe_douyin_users(users)[:limit], notes


def search_douyin_by_search_engine(keyword: str, limit: int, *, douyin_id: str | None = None) -> tuple[list[dict], list[str]]:
    users, notes = [], []
    target = douyin_id or keyword
    query = (
        f"抖音号 {target} (site:douyin.com/user OR site:iesdouyin.com/share/user)"
        if douyin_id
        else f"{target} 抖音 (site:douyin.com/user OR site:iesdouyin.com/share/user)"
    )
    simple_query = f"抖音号 {target} site:douyin.com/user" if douyin_id else f"{target} 抖音 site:douyin.com/user"
    engines = [
        ("duckduckgo", "https://duckduckgo.com/html/", {"q": simple_query}),
        ("bing", "https://www.bing.com/search", {"q": simple_query}),
        ("sogou", "https://www.sogou.com/web", {"query": simple_query}),
        ("duckduckgo-wide", "https://duckduckgo.com/html/", {"q": query}),
        ("bing-wide", "https://www.bing.com/search", {"q": query}),
    ]
    for label, engine_url, params in engines:
        if len(users) >= limit:
            break
        try:
            resp = requests.get(
                engine_url,
                params=params,
                headers={"User-Agent": DOUYIN_HEADERS["user-agent"]},
                timeout=15,
            )
            text = html.unescape(resp.text)
        except Exception as exc:
            notes.append(f"search-engine-{label}: {exc}")
            continue

        links = re.findall(r'href=["\']([^"\']+)["\']', text)
        links.extend(re.findall(r'https?://[^\s"\'<>]+', text))
        for href in links:
            url = unwrap_search_result_url(href)
            url = url.rstrip("),.;")
            if not re.search(r"(douyin\.com/user/|iesdouyin\.com/share/user/|v\.douyin\.com/)", url):
                continue
            identity = extract_douyin_identity(url)
            if not (identity.get("secUid") or identity.get("userId")):
                continue
            if identity.get("secUid", "").lower() in {"self", "login"}:
                continue
            users.append(
                {
                    "id": uuid.uuid4().hex,
                    "uid": identity.get("userId") or "",
                    "secUid": identity.get("secUid") or "",
                    "nickname": keyword,
                    "uniqueId": douyin_id or "",
                    "shortId": "",
                    "douyinId": douyin_id or "",
                    "signature": "搜索引擎候选结果",
                    "avatar": None,
                    "avatarRemote": None,
                    "followerCount": None,
                    "profileUrl": identity["inputUrl"],
                    "inputUrl": identity["inputUrl"],
                    "source": f"search-engine-{label}",
                }
            )
            if len(users) >= limit:
                break
    if not users:
        notes.append("search-engine: no profile result")
    return dedupe_douyin_users(users)[:limit], notes


def search_douyin_by_douyin_id(douyin_id: str, limit: int) -> tuple[list[dict], list[str]]:
    users, notes = [], []
    api_users, api_notes = search_douyin_by_web_api(douyin_id, limit)
    users.extend(api_users)
    notes.extend([f"抖音号-{note}" for note in api_notes])
    if len(users) < limit:
        mc_users, mc_notes = search_douyin_by_mediacrawler(douyin_id, limit - len(users))
        users.extend(mc_users)
        notes.extend([f"抖音号-{note}" for note in mc_notes])
    if len(users) < limit:
        browser_users, browser_notes = search_douyin_by_browser(douyin_id, limit - len(users))
        users.extend(browser_users)
        notes.extend([f"抖音号-{note}" for note in browser_notes])
    if len(users) < limit:
        engine_users, engine_notes = search_douyin_by_search_engine(douyin_id, limit - len(users), douyin_id=douyin_id)
        users.extend(engine_users)
        notes.extend([f"抖音号-{note}" for note in engine_notes])
    users = [user for user in dedupe_douyin_users(users) if actionable_douyin_user(user)]
    needle = douyin_id.lower()
    exact_users = [
        user
        for user in users
        if any(str(user.get(key) or "").lower() == needle for key in ("douyinId", "uniqueId", "shortId", "uid"))
    ]
    if exact_users:
        users = exact_users
    return rank_douyin_users(users, douyin_id)[:limit], notes


def search_douyin_users(keyword: str, limit: int = 10) -> tuple[list[dict], list[str]]:
    notes = []
    identity = extract_douyin_identity(keyword)
    if identity.get("secUid") or identity.get("userId"):
        direct_users = [
            {
                "id": uuid.uuid4().hex,
                "uid": identity.get("userId") or "",
                "secUid": identity.get("secUid") or "",
                "nickname": "抖音用户",
                "uniqueId": "",
                "shortId": "",
                "douyinId": "",
                "signature": "由主页/分享链接解析",
                "avatar": None,
                "avatarRemote": None,
                "followerCount": None,
                "profileUrl": identity.get("inputUrl"),
                "inputUrl": identity.get("inputUrl"),
                "source": "direct-url",
            }
        ]
        enriched, enrich_notes = enrich_douyin_users_by_dy_data(direct_users, keyword, limit)
        return [user for user in enriched if actionable_douyin_user(user)], notes + enrich_notes

    users = []
    if douyin_id := normalize_douyin_id_query(keyword):
        id_users, id_notes = search_douyin_by_douyin_id(douyin_id, limit)
        users.extend(id_users)
        notes.extend(id_notes)
        if users:
            users, enrich_notes = enrich_douyin_users_by_dy_data(users, keyword, limit)
            notes.extend(enrich_notes)
            users = [user for user in dedupe_douyin_users(users) if actionable_douyin_user(user)]
            return rank_douyin_users(users, keyword)[:limit], notes

    if len(users) < limit:
        api_users, api_notes = search_douyin_by_web_api(keyword, limit - len(users))
        users.extend(api_users)
        notes.extend(api_notes)
    if len(users) < limit:
        page_users, page_notes = search_douyin_by_search_page(keyword, limit - len(users))
        users.extend(page_users)
        notes.extend(page_notes)
    if len(users) < limit:
        mc_users, mc_notes = search_douyin_by_mediacrawler(keyword, limit - len(users))
        users.extend(mc_users)
        notes.extend(mc_notes)
    if len(users) < limit:
        browser_users, browser_notes = search_douyin_by_browser(keyword, limit - len(users))
        users.extend(browser_users)
        notes.extend(browser_notes)
    if len(users) < limit:
        fallback_users, fallback_notes = search_douyin_by_search_engine(keyword, limit - len(users))
        users.extend(fallback_users)
        notes.extend(fallback_notes)
    users, enrich_notes = enrich_douyin_users_by_dy_data(users, keyword, limit)
    notes.extend(enrich_notes)
    users = [user for user in dedupe_douyin_users(users) if actionable_douyin_user(user)]
    return rank_douyin_users(users, keyword)[:limit], notes


def build_douyin_play_url(uri: str) -> str | None:
    if not uri:
        return None
    params = {
        "video_id": uri,
        "line": "0",
        "ratio": "720p",
        "media_type": "4",
        "vr_type": "0",
        "improve_bitrate": "0",
        "is_play_url": "1",
        "h265": "1",
        "adapt720": "1",
    }
    return f"https://aweme.snssdk.com/aweme/v1/play/?{urllib.parse.urlencode(params)}"


def normalize_douyin_video_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query.pop("watermark", None)
    rebuilt = parsed._replace(query=urllib.parse.urlencode(query, doseq=True)).geturl()
    return rebuilt.replace("playwm", "play").replace("play_watermark", "play")


def select_douyin_video_url(video: dict, play_addr) -> str | None:
    direct_url = normalize_douyin_video_url(first_url(play_addr))
    if direct_url:
        return direct_url
    uri = None
    if isinstance(play_addr, dict):
        uri = play_addr.get("uri")
    uri = uri or video.get("play_addr_uri")
    return build_douyin_play_url(uri)


def serialize_douyin_video(aweme: dict) -> dict | None:
    video = aweme.get("video") or {}
    music = aweme.get("music") or {}
    play_addr = video.get("play_addr") or {}
    video_url = select_douyin_video_url(video, play_addr)
    audio_url = first_url((music.get("play_url") or {}))
    play_addr_uri = play_addr.get("uri") if isinstance(play_addr, dict) else None
    aweme_id = str(aweme.get("aweme_id") or aweme.get("group_id") or play_addr_uri or uuid.uuid4().hex)
    desc = compact_text(aweme.get("desc") or (aweme.get("share_info") or {}).get("share_desc"), "未命名视频")
    create_time = aweme.get("create_time") or 0
    try:
        create_time_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(create_time)))
    except Exception:
        create_time_text = ""
    statistics = aweme.get("statistics") or {}
    cover_url = first_url(video.get("cover") or video.get("origin_cover") or video.get("dynamic_cover"))
    return {
        "id": aweme_id,
        "desc": desc,
        "createTime": create_time,
        "createTimeText": create_time_text,
        "duration": int((video.get("duration") or music.get("duration") or 0) or 0),
        "coverUrl": cache_remote_image(cover_url, "covers", aweme_id),
        "coverRemote": cover_url,
        "videoUrl": video_url,
        "audioUrl": audio_url,
        "musicTitle": compact_text(music.get("title"), "原声"),
        "musicAuthor": compact_text(music.get("author")),
        "diggCount": statistics.get("digg_count"),
        "commentCount": statistics.get("comment_count"),
        "shareCount": statistics.get("share_count"),
        "downloadable": bool(audio_url or video_url),
    }


def generate_amemv_signature(value: str) -> str:
    script = AMEMV_REPO / "fuck-byted-acrawler.js"
    if not script.exists():
        raise RuntimeError("amemv-crawler signature script not found")
    result = subprocess.run(
        ["node", str(script), str(value)],
        cwd=str(AMEMV_REPO),
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return result.stdout.strip().splitlines()[0]


def get_douyin_dytk(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=DOUYIN_MOBILE_HEADERS, timeout=15)
    except Exception:
        return None
    if match := re.search(r"dytk:\s*'([^']+)'", resp.text):
        return match.group(1)
    return None


def ensure_douyin_sec_uid(user: dict) -> str | None:
    sec_uid = user.get("secUid")
    if sec_uid:
        return sec_uid
    identity = extract_douyin_identity(user.get("inputUrl") or user.get("profileUrl") or "")
    sec_uid = identity.get("secUid")
    if sec_uid:
        user["secUid"] = sec_uid
        user["profileUrl"] = f"https://www.douyin.com/user/{sec_uid}"
        user["inputUrl"] = user.get("inputUrl") or user["profileUrl"]
    return sec_uid


def fetch_douyin_videos_by_dy_data(user: dict) -> tuple[list[dict], list[str]]:
    sec_uid = ensure_douyin_sec_uid(user)
    if not sec_uid:
        return [], ["dy-data-post: missing secUid"]
    videos, notes = [], []
    headers = dict(DOUYIN_HEADERS)
    headers["referer"] = "https://www.iesdouyin.com/"
    session = requests.Session()
    cursor = "0"
    for _ in range(120):
        params = {
            "sec_uid": sec_uid,
            "count": "21",
            "max_cursor": cursor,
            "aid": "1128",
            "_signature": "",
            "dytk": "",
        }
        try:
            resp = session.get(
                "https://www.iesdouyin.com/web/api/v2/aweme/post/",
                params=params,
                headers=headers,
                timeout=18,
            )
            data = douyin_safe_json(resp)
        except Exception as exc:
            notes.append(f"dy-data-post: {exc}")
            break
        status_code = data.get("status_code")
        if status_code not in {0, None}:
            notes.append(f"dy-data-post: {data.get('status_msg') or status_code}")
            break
        aweme_list = data.get("aweme_list") or []
        videos.extend([item for item in aweme_list if isinstance(item, dict)])
        if not aweme_list and not data.get("has_more"):
            notes.append("dy-data-post: no aweme_list")
        if not data.get("has_more"):
            break
        next_cursor = str(data.get("max_cursor") or "")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return videos, notes


def fetch_douyin_videos_by_mediacrawler(user: dict) -> tuple[list[dict], list[str]]:
    sec_uid = ensure_douyin_sec_uid(user)
    if not sec_uid:
        return [], ["mediacrawler-post: missing secUid"]
    profile_url = user.get("profileUrl") or f"https://www.douyin.com/user/{sec_uid}"

    def task(page, context):
        videos, notes, cursor, seen = [], [], "", set()
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        for _ in range(120):
            params = {
                "sec_user_id": sec_uid,
                "count": "18",
                "max_cursor": cursor,
                "locate_query": "false",
                "publish_video_strategy_type": "2",
                "verifyFp": MEDIACRAWLER_VERIFY_FP,
                "fp": MEDIACRAWLER_VERIFY_FP,
            }
            try:
                data = mediacrawler_douyin_get(
                    page,
                    context,
                    "/aweme/v1/web/aweme/post/",
                    params,
                    referer=profile_url,
                    sign=True,
                )
            except Exception as exc:
                notes.append(f"mediacrawler-post: {exc}")
                break
            status_code = data.get("status_code")
            if status_code not in {0, None}:
                notes.append(f"mediacrawler-post: {data.get('status_msg') or status_code}")
                break
            aweme_list = extract_douyin_awemes_from_payload(data)
            for aweme in aweme_list:
                key = str(aweme.get("aweme_id") or aweme.get("group_id") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                videos.append(aweme)
            if not aweme_list and not data.get("has_more"):
                notes.append("mediacrawler-post: no aweme_list")
            if not data.get("has_more"):
                break
            next_cursor = str(data.get("max_cursor") or "")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            page.wait_for_timeout(600)
        if note := browser_risk_note(page):
            notes.append(note)
        return {"videos": videos, "notes": notes}

    result, run_notes = run_douyin_browser_task("mediacrawler-post", task)
    if not result:
        return [], run_notes
    return result["videos"], run_notes + result["notes"]


def fetch_douyin_videos_by_browser(user: dict) -> tuple[list[dict], list[str]]:
    sec_uid = ensure_douyin_sec_uid(user)
    if not sec_uid:
        return [], ["browser-post: missing secUid"]
    profile_url = user.get("profileUrl") or f"https://www.douyin.com/user/{sec_uid}"

    def task(page, _context):
        raw_videos, notes, seen = [], [], set()

        def add_awemes(items):
            for aweme in items:
                key = str(aweme.get("aweme_id") or aweme.get("group_id") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                raw_videos.append(aweme)

        def on_response(response):
            if "/aweme/v1/web/aweme/post/" not in response.url:
                return
            try:
                data = response.json()
            except Exception as exc:
                notes.append(f"browser-post-response: {exc}")
                return
            status_code = data.get("status_code")
            if status_code not in {0, None}:
                notes.append(f"browser-post: {data.get('status_msg') or status_code}")
            add_awemes(extract_douyin_awemes_from_payload(data))

        page.on("response", on_response)
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        add_awemes(extract_douyin_awemes_from_html(page.content()))

        stable_rounds, last_count = 0, -1
        for _ in range(80):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1100)
            add_awemes(extract_douyin_awemes_from_html(page.content()))
            if len(raw_videos) == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_count = len(raw_videos)
            if raw_videos and stable_rounds >= 6:
                break

        if note := browser_risk_note(page):
            notes.append(note)
        if not raw_videos:
            notes.append("browser-post: no aweme_list")
        return {"videos": raw_videos, "notes": notes}

    result, run_notes = run_douyin_browser_task("browser-post", task)
    if not result:
        return [], run_notes
    return result["videos"], run_notes + result["notes"]


def fetch_douyin_videos_by_web(user: dict) -> tuple[list[dict], list[str]]:
    sec_uid = ensure_douyin_sec_uid(user)
    if not sec_uid:
        return [], ["web-post: missing secUid"]
    videos, notes = [], []
    session = requests.Session()
    device_id = douyin_device_id()
    cursor = "0"
    for _ in range(120):
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "sec_user_id": sec_uid,
            "max_cursor": cursor,
            "locate_query": "false",
            "show_live_replay_strategy": "1",
            "need_time_list": "1",
            "time_list_query": "0",
            "whale_cut_token": "",
            "cut_version": "1",
            "count": "18",
            "publish_video_strategy_type": "2",
            "from_user_page": "1",
            "device_id": device_id,
            "webid": device_id,
        }
        try:
            resp = session.get(
                "https://www.douyin.com/aweme/v1/web/aweme/post/",
                params=params,
                headers=DOUYIN_HEADERS,
                timeout=18,
            )
            data = douyin_safe_json(resp)
        except Exception as exc:
            notes.append(f"web-post: {exc}")
            break
        if data.get("status_code") not in {0, None}:
            notes.append(f"web-post: {data.get('status_msg') or data.get('status_code')}")
            break
        aweme_list = data.get("aweme_list") or []
        videos.extend([item for item in aweme_list if isinstance(item, dict)])
        if not aweme_list and not data.get("has_more"):
            notes.append("web-post: no aweme_list")
        if not data.get("has_more"):
            break
        next_cursor = str(data.get("max_cursor") or "")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return videos, notes


def fetch_douyin_videos_by_amemv(user: dict) -> tuple[list[dict], list[str]]:
    identity = extract_douyin_identity(user.get("inputUrl") or user.get("profileUrl") or "")
    user_id = user.get("uid") or identity.get("userId")
    input_url = identity.get("inputUrl") or user.get("inputUrl") or user.get("profileUrl")
    if not user_id or not input_url:
        return [], ["amemv: missing share user id"]
    dytk = get_douyin_dytk(input_url)
    hostname = urllib.parse.urlparse(input_url).hostname or "www.douyin.com"
    if hostname != "t.tiktok.com" and not dytk:
        return [], ["amemv: missing dytk"]
    try:
        signature = generate_amemv_signature(str(user_id))
    except Exception as exc:
        return [], [f"amemv-signature: {exc}"]

    params = {
        "user_id": str(user_id),
        "count": "21",
        "max_cursor": "0",
        "aid": "1128",
        "_signature": signature,
        "dytk": dytk,
    }
    url = f"https://{hostname}/web/api/v2/aweme/post/"
    videos, cursor = [], "0"
    for _ in range(120):
        params["max_cursor"] = cursor
        try:
            resp = requests.get(url, params=params, headers=DOUYIN_MOBILE_HEADERS, timeout=18)
            data = douyin_safe_json(resp)
        except Exception as exc:
            return videos, [f"amemv-post: {exc}"]
        aweme_list = data.get("aweme_list") or []
        videos.extend([item for item in aweme_list if isinstance(item, dict)])
        if not data.get("has_more"):
            break
        next_cursor = str(data.get("max_cursor") or "")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return videos, []


def fetch_douyin_user_videos(user: dict) -> tuple[list[dict], list[str]]:
    notes = []
    sec_uid = ensure_douyin_sec_uid(user)
    if sec_uid:
        info_user, info_notes = fetch_douyin_user_info_by_dy_data(sec_uid)
        if info_user:
            user.update(merge_douyin_user(user, info_user, prefer_enriched_profile=True))
        else:
            notes.extend(info_notes)

    raw_videos, dy_data_notes = fetch_douyin_videos_by_dy_data(user)
    notes.extend(dy_data_notes)
    if not raw_videos:
        raw_videos, mc_notes = fetch_douyin_videos_by_mediacrawler(user)
        notes.extend(mc_notes)
    if not raw_videos:
        raw_videos, web_notes = fetch_douyin_videos_by_web(user)
        notes.extend(web_notes)
    if not raw_videos:
        raw_videos, browser_notes = fetch_douyin_videos_by_browser(user)
        notes.extend(browser_notes)
    if not raw_videos:
        raw_videos, amemv_notes = fetch_douyin_videos_by_amemv(user)
        notes.extend(amemv_notes)
    videos = [serialized for item in raw_videos if (serialized := serialize_douyin_video(item))]
    deduped, seen = [], set()
    for video in videos:
        if video["id"] in seen:
            continue
        seen.add(video["id"])
        deduped.append(video)
    return deduped, notes


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe_stem = sanitize_filename(stem).strip(" .") or uuid.uuid4().hex
    safe_stem = safe_stem[:120]
    ext = ext if ext.startswith(".") else f".{ext}"
    path = directory / f"{safe_stem}{ext}"
    idx = 1
    while path.exists():
        path = directory / f"{safe_stem} ({idx}){ext}"
        idx += 1
    return path


def guess_ext_from_response(url: str, content_type: str | None, fallback: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type in {"audio/mpeg", "audio/mp3"}:
        return ".mp3"
    if content_type in {"audio/mp4", "video/mp4", "audio/x-m4a"}:
        return ".m4a" if fallback != ".mp4" else ".mp4"
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return ".m4a" if guessed == ".mp4" and fallback != ".mp4" else guessed
    suffix = Path(urllib.parse.urlparse(url).path).suffix
    return suffix if suffix else fallback


def download_stream_to_file(url: str, directory: Path, stem: str, fallback_ext: str) -> Path:
    headers = dict(DOUYIN_HEADERS)
    headers["referer"] = "https://www.douyin.com/"
    with requests.get(url, headers=headers, stream=True, timeout=(10, 60), allow_redirects=True) as resp:
        resp.raise_for_status()
        ext = guess_ext_from_response(resp.url, resp.headers.get("Content-Type"), fallback_ext)
        path = unique_path(directory, stem, ext)
        with open(path, "wb") as file:
            for chunk in resp.iter_content(chunk_size=1024 * 512):
                if chunk:
                    file.write(chunk)
    return path


def extract_audio_from_video(video_path: Path, audio_path: Path) -> Path:
    import av

    with av.open(str(video_path)) as input_container:
        audio_stream = next((stream for stream in input_container.streams if stream.type == "audio"), None)
        if audio_stream is None:
            raise RuntimeError("video has no audio stream")
        with av.open(str(audio_path), "w") as output_container:
            output_stream = output_container.add_stream_from_template(audio_stream)
            for packet in input_container.demux(audio_stream):
                if packet.dts is None:
                    continue
                packet.stream = output_stream
                output_container.mux(packet)
    return audio_path


def run_douyin_audio_job(job_id: str, video_batch: dict, selected_ids: list[str]):
    with CACHE_LOCK:
        JOBS[job_id].update({"status": "running", "startedAt": time.time(), "message": "正在下载并分离音频"})
    selected_videos = [video_batch["items"][item_id] for item_id in selected_ids if item_id in video_batch["items"]]
    files = []
    try:
        for video in selected_videos:
            stem = f"{video.get('desc') or video.get('musicTitle') or video.get('id')} - {video.get('id')}"
            audio_path = None
            if video.get("audioUrl"):
                audio_path = download_stream_to_file(video["audioUrl"], DOUYIN_AUDIO_ROOT, stem, ".mp3")
            elif video.get("videoUrl"):
                video_path = download_stream_to_file(video["videoUrl"], DOUYIN_VIDEO_ROOT, stem, ".mp4")
                audio_path = extract_audio_from_video(video_path, unique_path(DOUYIN_AUDIO_ROOT, stem, ".m4a"))
            if audio_path and (file_info := safe_register_file(audio_path)):
                file_info.update(
                    {
                        "source": "Douyin",
                        "songName": video.get("musicTitle") or video.get("desc"),
                        "singers": video.get("musicAuthor") or "",
                        "ext": audio_path.suffix.removeprefix("."),
                    }
                )
                files.append(file_info)
        status = "complete" if files else "empty"
        message = "音频下载完成" if files else "任务结束，但没有生成可用音频"
        with CACHE_LOCK:
            JOBS[job_id].update({"status": status, "finishedAt": time.time(), "message": message, "files": files})
    except Exception as exc:
        with CACHE_LOCK:
            JOBS[job_id].update(
                {
                    "status": "error",
                    "finishedAt": time.time(),
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                    "files": files,
                }
            )


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


@app.get("/api/douyin/cache")
def douyin_cache():
    return jsonify({"ok": True, "cacheRoot": str(DOUYIN_CACHE_ROOT), "stats": douyin_cache_stats()})


@app.get("/api/douyin/session")
def douyin_session():
    return jsonify({"ok": True, "session": douyin_login_snapshot()})


@app.post("/api/douyin/session/login")
def douyin_session_login():
    global DOUYIN_LOGIN_THREAD
    with CACHE_LOCK:
        if DOUYIN_LOGIN_STATE.get("running"):
            return jsonify({"ok": True, "session": dict(DOUYIN_LOGIN_STATE)})
        DOUYIN_LOGIN_STATE.update(
            {
                "running": True,
                "startedAt": time.time(),
                "finishedAt": None,
                "message": "正在打开登录窗口",
                "profileRoot": str(DOUYIN_BROWSER_PROFILE),
            }
        )
        DOUYIN_LOGIN_THREAD = Thread(target=run_douyin_login_window, daemon=True)
        DOUYIN_LOGIN_THREAD.start()
        return jsonify({"ok": True, "session": dict(DOUYIN_LOGIN_STATE)})


@app.post("/api/douyin/cache/clear")
def clear_douyin_cache():
    shutil.rmtree(DOUYIN_AVATAR_CACHE, ignore_errors=True)
    shutil.rmtree(DOUYIN_COVER_CACHE, ignore_errors=True)
    DOUYIN_AVATAR_CACHE.mkdir(parents=True, exist_ok=True)
    DOUYIN_COVER_CACHE.mkdir(parents=True, exist_ok=True)
    return jsonify({"ok": True, "cacheRoot": str(DOUYIN_CACHE_ROOT), "stats": douyin_cache_stats()})


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


@app.post("/api/douyin/users")
def douyin_users():
    payload = request.get_json(silent=True) or {}
    keyword = str(payload.get("keyword", "")).strip()
    limit = clamp_limit(payload.get("limit", 10), default=10)
    if not keyword:
        return json_error("请输入抖音用户名、主页链接或分享链接")

    users, notes = search_douyin_users(keyword, limit=limit)
    search_id = uuid.uuid4().hex
    with CACHE_LOCK:
        DOUYIN_USER_CACHE[search_id] = {
            "keyword": keyword,
            "users": {user["id"]: user for user in users},
            "createdAt": time.time(),
            "notes": notes,
        }
    return jsonify({"ok": True, "searchId": search_id, "users": users, "notes": notes})


@app.post("/api/douyin/videos")
def douyin_videos():
    payload = request.get_json(silent=True) or {}
    search_id = str(payload.get("searchId", "")).strip()
    user_id = str(payload.get("userId", "")).strip()
    if not search_id or not user_id:
        return json_error("缺少用户选择")

    with CACHE_LOCK:
        search_obj = DOUYIN_USER_CACHE.get(search_id)
        if not search_obj:
            return json_error("用户搜索结果已失效，请重新搜索", 404)
        user = search_obj["users"].get(user_id)
        if not user:
            return json_error("选中的抖音用户不存在", 404)

    videos, notes = fetch_douyin_user_videos(user)
    video_set_id = uuid.uuid4().hex
    with CACHE_LOCK:
        DOUYIN_VIDEO_CACHE[video_set_id] = {
            "user": user,
            "items": {video["id"]: video for video in videos},
            "createdAt": time.time(),
            "notes": notes,
        }
    return jsonify({"ok": True, "videoSetId": video_set_id, "user": user, "videos": videos, "notes": notes})


@app.post("/api/douyin/download-audio")
def douyin_download_audio():
    payload = request.get_json(silent=True) or {}
    video_set_id = str(payload.get("videoSetId", "")).strip()
    selected_ids = payload.get("ids") if isinstance(payload.get("ids"), list) else []
    selected_ids = [str(item_id) for item_id in selected_ids]
    if not video_set_id:
        return json_error("缺少 videoSetId")
    if not selected_ids:
        return json_error("请选择要下载音频的视频")

    with CACHE_LOCK:
        video_batch = DOUYIN_VIDEO_CACHE.get(video_set_id)
        if not video_batch:
            return json_error("视频列表已失效，请重新获取", 404)
        valid_ids = [item_id for item_id in selected_ids if item_id in video_batch["items"]]
        if not valid_ids:
            return json_error("没有可下载的选中视频")
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {
            "id": job_id,
            "type": "douyin-audio",
            "status": "queued",
            "message": "已加入音频下载队列",
            "createdAt": time.time(),
            "files": [],
        }

    worker = Thread(target=run_douyin_audio_job, args=(job_id, video_batch, valid_ids), daemon=True)
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


@app.get("/cache/douyin/<category>/<filename>")
def douyin_cache_file(category: str, filename: str):
    try:
        base_dir = cache_category_dir(category).resolve()
    except ValueError:
        return json_error("缓存分类不存在", 404)
    path = (base_dir / filename).resolve()
    if base_dir not in path.parents or not path.exists() or not path.is_file():
        return json_error("缓存文件不存在", 404)
    return send_file(path, as_attachment=False, download_name=path.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False, threaded=True)
