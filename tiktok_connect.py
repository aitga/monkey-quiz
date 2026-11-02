"""One-time: swaps the TikTok code for a refresh token and saves it as the TIKTOK_REFRESH_TOKEN secret."""
import os
import subprocess
import urllib.parse

import requests

code = urllib.parse.unquote(os.environ["CODE"].strip())
if "code=" in code:  # the whole address was pasted
    code = code.split("code=", 1)[1].split("&", 1)[0]
owner, repo = os.environ["GITHUB_REPOSITORY"].split("/")
redirect = f"https://{owner.lower()}.github.io/{repo}/"
r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
    "client_key": os.environ["TIKTOK_CLIENT_KEY"].strip(), "client_secret": os.environ["TIKTOK_CLIENT_SECRET"].strip(),
    "code": code, "grant_type": "authorization_code", "redirect_uri": redirect})
out = r.json()
if "refresh_token" not in out:
    raise SystemExit(f"TikTok said no: {out}. Get a new code (step f) and try again quickly.")
subprocess.run(["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"],
                "--body", out["refresh_token"]], check=True)
print("TikTok connected! TIKTOK_REFRESH_TOKEN was saved.")
