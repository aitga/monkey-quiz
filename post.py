"""Posts the videos in out/ to every platform whose secrets are set, and writes a results table."""
import json
import os
import subprocess
import time

import requests

GRAPH = "https://graph.facebook.com/v21.0"
CONFIG = json.load(open("config.json"))
results = []


def env(name):
    return (os.environ.get(name) or "").strip()


def have(*names):
    return all(env(n) for n in names)


def caption(v):
    return (f"Quiz {v['number']} - {v['country']} Week! {v['question']} Comment A, B, C or D and tag a friend "
            f"from {v['country']}! {CONFIG.get('hashtags', '')} Photo: Wikipedia / Wikimedia Commons").strip()


def check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


# ---------------- YouTube ----------------
def youtube(v):
    tok = check(requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}))["access_token"]
    meta = {"snippet": {"title": f"Quiz {v['number']} - {v['country']} Week #shorts"[:100],
                        "description": caption(v), "categoryId": "27"},
            "status": {"privacyStatus": CONFIG.get("youtube_privacy", "public"), "selfDeclaredMadeForKids": False}}
    size = os.path.getsize(v["video"])
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      headers={"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(size)}, json=meta)
    check(r)
    with open(v["video"], "rb") as f:
        out = check(requests.put(r.headers["Location"], data=f, headers={"Authorization": f"Bearer {tok}",
                                                                          "Content-Type": "video/mp4"}))
    return f"https://youtube.com/shorts/{out['id']}"


# ---------------- Facebook Page ----------------
def facebook(v):
    with open(v["video"], "rb") as f:
        out = check(requests.post(f"https://graph-video.facebook.com/v21.0/{env('META_PAGE_ID')}/videos",
                                  data={"access_token": env("META_PAGE_TOKEN"), "description": caption(v),
                                        "title": f"Quiz {v['number']}"},
                                  files={"source": ("video.mp4", f, "video/mp4")}, timeout=600))
    return f"https://facebook.com/{out['id']}"


# ---------------- Instagram Reels ----------------
def instagram(v):
    token, ig = env("META_PAGE_TOKEN"), env("IG_USER_ID")
    box = check(requests.post(f"{GRAPH}/{ig}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption(v), "access_token": token}))
    size = os.path.getsize(v["video"])
    with open(v["video"], "rb") as f:
        check(requests.post(f"https://rupload.facebook.com/ig-api-upload/v21.0/{box['id']}", data=f, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}, timeout=600))
    for _ in range(60):
        st = check(requests.get(f"{GRAPH}/{box['id']}", params={"fields": "status_code,status", "access_token": token}))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram could not process the video: {st.get('status')}")
        time.sleep(10)
    out = check(requests.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": box["id"], "access_token": token}))
    return f"Instagram post id {out['id']}"


# ---------------- TikTok ----------------
_tiktok_token = None


def tiktok_token():
    global _tiktok_token
    if _tiktok_token:
        return _tiktok_token
    out = check(requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": env("TIKTOK_CLIENT_KEY"), "client_secret": env("TIKTOK_CLIENT_SECRET"),
        "grant_type": "refresh_token", "refresh_token": env("TIKTOK_REFRESH_TOKEN")}))
    if "access_token" not in out:
        raise RuntimeError(f"TikTok login failed: {out}")
    new_refresh = out.get("refresh_token")
    if new_refresh and new_refresh != env("TIKTOK_REFRESH_TOKEN") and env("GH_TOKEN"):
        subprocess.run(["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", env("GITHUB_REPOSITORY"),
                        "--body", new_refresh], check=True)
    _tiktok_token = out["access_token"]
    return _tiktok_token


def tiktok(v):
    h = {"Authorization": f"Bearer {tiktok_token()}", "Content-Type": "application/json; charset=UTF-8"}
    info = check(requests.post("https://open.tiktokapis.com/v2/post/publish/creator_info/query/", headers=h))
    options = info.get("data", {}).get("privacy_level_options", ["SELF_ONLY"])
    wanted = CONFIG.get("tiktok_privacy", "PUBLIC_TO_EVERYONE")
    privacy = wanted if wanted in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])
    size = os.path.getsize(v["video"])
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    r = requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/", headers=h, json={
        "post_info": {"title": caption(v)[:2000], "privacy_level": privacy, "disable_comment": False},
        "source_info": source})
    how = f"posted (privacy: {privacy})"
    if "unaudited_client" in r.text:
        # Until TikTok approves the app, send it to your TikTok inbox instead: open TikTok, tap the
        # notification, and post it yourself in one tap (you can also add a trending sound there).
        r = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", headers=h,
                          json={"source_info": source})
        how = "sent to your TikTok inbox - open TikTok and tap the notification to post it"
    data = check(r).get("data", {})
    with open(v["video"], "rb") as f:
        r = requests.put(data["upload_url"], data=f, headers={
            "Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}", "Content-Length": str(size)})
    if r.status_code >= 400:
        raise RuntimeError(f"TikTok upload failed: HTTP {r.status_code} {r.text[:200]}")
    return how


# ---------------- X (Twitter) ----------------
def x_post(v):
    from requests_oauthlib import OAuth1
    auth = OAuth1(env("X_API_KEY"), env("X_API_SECRET"), env("X_ACCESS_TOKEN"), env("X_ACCESS_SECRET"))
    size = os.path.getsize(v["video"])
    base = "https://api.x.com/2/media/upload"
    init = check(requests.post(f"{base}/initialize", auth=auth, json={
        "media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}))
    media_id = init["data"]["id"]
    with open(v["video"], "rb") as f:
        i = 0
        while chunk := f.read(4 * 1024 * 1024):
            r = requests.post(f"{base}/{media_id}/append", auth=auth, data={"segment_index": i},
                              files={"media": ("chunk", chunk, "application/octet-stream")})
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            i += 1
    fin = check(requests.post(f"{base}/{media_id}/finalize", auth=auth))
    info = fin.get("data", {}).get("processing_info")
    while info and info.get("state") in ("pending", "in_progress"):
        time.sleep(info.get("check_after_secs", 5))
        st = check(requests.get(base, auth=auth, params={"command": "STATUS", "media_id": media_id}))
        info = st.get("data", {}).get("processing_info")
    if info and info.get("state") == "failed":
        raise RuntimeError(f"X could not process the video: {info}")
    out = check(requests.post("https://api.x.com/2/tweets", auth=auth, json={
        "text": caption(v)[:280], "media": {"media_ids": [media_id]}}))
    return f"https://x.com/i/status/{out['data']['id']}"


PLATFORMS = [
    ("YouTube", youtube, ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]),
    ("Facebook", facebook, ["META_PAGE_ID", "META_PAGE_TOKEN"]),
    ("Instagram", instagram, ["META_PAGE_TOKEN", "IG_USER_ID"]),
    ("TikTok", tiktok, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"]),
    ("X", x_post, ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]),
]


def main():
    manifest = json.load(open("out/manifest.json"))
    for v in manifest["videos"]:
        for name, fn, needs in PLATFORMS:
            if not have(*needs):
                results.append((name, v["number"], "⏭️ not connected"))
                continue
            try:
                results.append((name, v["number"], "✅ " + fn(v)))
            except Exception as e:
                results.append((name, v["number"], "❌ " + str(e).replace("|", "/").replace("\n", " ")[:400]))
            print(results[-1])
    json.dump(manifest["state"], open("state.json", "w"), indent=2)
    lines = ["## Posting results", "", "| Platform | Quiz | Result |", "|---|---|---|"]
    lines += [f"| {p} | {n} | {r} |" for p, n, r in results]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        open(summary, "a").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    # your own videos from ready/ are removed after posting so they are not posted twice
    for v in manifest["videos"]:
        src = v.get("source")
        if src:
            for path in (src, os.path.splitext(src)[0] + ".txt"):
                if os.path.exists(path):
                    subprocess.run(["git", "rm", "-q", path])


if __name__ == "__main__":
    main()
