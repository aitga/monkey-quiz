"""Posts the new Football Arena cartoon match recaps (English commentary) to TikTok.
   It looks at the 'recaps' videos made by github.com/aitga/football-arena and posts the ones
   it has not posted yet. To stop it, put  "football_tiktok": false  in config.json."""
import datetime
import io
import json
import os
import zipfile

import requests

import post

REPO = "aitga/football-arena"
DONE_FILE = "football_tiktok_done.json"
LANGS = ["en"]          # which commentary to post on TikTok
MAX_AGE_H = 12          # ignore recaps older than this (no old backlog)
MAX_PER_RUN = 4


def gh(url):
    err = None
    for tok in (post.env("GH_TOKEN"), post.env("GITHUB_TOKEN"), ""):
        h = {"Accept": "application/vnd.github+json"}
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        r = requests.get(url, headers=h, timeout=120)
        if r.status_code < 400:
            return r
        err = f"GitHub said HTTP {r.status_code}: {r.text[:200]}"
    raise RuntimeError(err)


def main():
    if post.CONFIG.get("football_tiktok", True) is False:
        print("Football TikTok posting is switched off in config.json")
        return
    try:
        done = set(json.load(open(DONE_FILE)))
    except Exception:
        done = set()
    now = datetime.datetime.now(datetime.timezone.utc)
    arts = gh(f"https://api.github.com/repos/{REPO}/actions/artifacts?name=recaps&per_page=30").json()["artifacts"]
    todo = []
    for a in sorted(arts, key=lambda a: a["created_at"]):
        made = datetime.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
        if a["expired"] or str(a["id"]) in done or now - made > datetime.timedelta(hours=MAX_AGE_H):
            continue
        todo.append(a)
    results = []
    posted = 0
    for a in todo:
        if posted >= MAX_PER_RUN:
            break  # the rest is posted on the next run
        z = zipfile.ZipFile(io.BytesIO(gh(a["archive_download_url"]).content))
        folder = f"fa_{a['id']}"
        z.extractall(folder)
        recaps = json.load(open(os.path.join(folder, "recaps.json")))
        for r in recaps:
            if r.get("lang") not in LANGS:
                continue
            v = {"video": os.path.join(folder, os.path.basename(r["video"])), "caption": r["caption"]}
            try:
                results.append("✅ " + post.tiktok(v) + " – " + r["caption"].splitlines()[0])
            except Exception as e:
                results.append("❌ " + str(e)[:300])
            posted += 1
            print(results[-1])
        done.add(str(a["id"]))
    json.dump(sorted(done)[-300:], open(DONE_FILE, "w"))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        open(summary, "a").write("## Football Arena → TikTok\n\n" +
                                 ("\n\n".join(results) if results else "No new match recaps to post.") + "\n")


post.caption = lambda v: v["caption"]  # use the Football Arena caption, not the quiz one

if __name__ == "__main__":
    main()
