import os
import re
import json
import time
import pathlib
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

import requests
from flask import Flask, jsonify, request, send_from_directory, Response, session

API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
TRANSCRIPT_DIR = pathlib.Path(os.getenv("TRANSCRIPT_DIR", "/tmp/transcripts"))
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = pathlib.Path(os.getenv("USERS_FILE", "users.json"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xiaoyuzhou Transcript</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 32px; background: #0b1221; color: #e8edf7; }
    main { max-width: 800px; margin: 0 auto; }
    h1 { margin: 0 0 12px; font-size: 28px; }
    p { margin: 0 0 16px; color: #9badc8; }
    form { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
    input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #22304d; background: #121b2f; color: #e8edf7; }
    button { padding: 12px 18px; border: none; border-radius: 8px; background: #4f9cff; color: #0b1221; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    #status { margin-bottom: 12px; color: #9badc8; }
    pre { background: #0f1a2c; padding: 16px; border-radius: 10px; min-height: 140px; white-space: pre-wrap; word-break: break-word; }
    a { color: #8be0ff; }
  </style>
</head>
<body>
  <main>
    <h1>播客转录</h1>
    <p>粘贴小宇宙或 Apple 播客节目链接，自动抓取音频并生成文本（当前默认中文转录）。</p>
    <div id="auth">
      <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:8px;">
        <input id="email" type="email" placeholder="Email">
        <input id="password" type="password" placeholder="Password">
        <button id="register" type="button">注册</button>
        <button id="login" type="button">登录</button>
        <button id="logout" type="button" style="display:none;">退出</button>
      </div>
      <div id="auth-status" style="color:#9badc8; margin-bottom:12px;">未登录</div>
    </div>
    <form id="form">
      <input id="url" name="url" type="url" placeholder="https://www.xiaoyuzhoufm.com/episode/... 或 https://podcasts.apple.com/..." required>
      <button id="submit" type="submit">转录</button>
    </form>
    <div style="display:flex; gap:12px; align-items:center; margin-bottom:12px;">
      <button id="copy" type="button" disabled>复制全部</button>
      <a id="download" href="#" style="display:none;">下载 .txt</a>
    </div>
    <div id="status"></div>
    <div id="meta"></div>
    <pre id="result"></pre>
  </main>
  <script>
    const form = document.getElementById("form");
    const statusEl = document.getElementById("status");
    const metaEl = document.getElementById("meta");
    const resultEl = document.getElementById("result");
    const downloadEl = document.getElementById("download");
    const submitBtn = document.getElementById("submit");
    const copyBtn = document.getElementById("copy");
    const registerBtn = document.getElementById("register");
    const loginBtn = document.getElementById("login");
    const logoutBtn = document.getElementById("logout");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const authStatus = document.getElementById("auth-status");
    let authed = false;

    const updateAuthUI = (user) => {
      authed = !!user;
      authStatus.textContent = authed ? `已登录: ${user}` : "未登录";
      logoutBtn.style.display = authed ? "inline-block" : "none";
      loginBtn.style.display = authed ? "none" : "inline-block";
      registerBtn.style.display = authed ? "none" : "inline-block";
      submitBtn.disabled = !authed;
    };

    const checkAuth = async () => {
      try {
        const res = await fetch("/api/me");
        const data = await res.json();
        updateAuthUI(data.user || null);
      } catch {
        updateAuthUI(null);
      }
    };

    registerBtn.addEventListener("click", async () => {
      const email = emailInput.value.trim();
      const password = passwordInput.value.trim();
      if (!email || !password) {
        authStatus.textContent = "请输入邮箱和密码";
        return;
      }
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) return (authStatus.textContent = data.error || "注册失败");
      updateAuthUI(email);
      authStatus.textContent = "注册成功";
    });

    loginBtn.addEventListener("click", async () => {
      const email = emailInput.value.trim();
      const password = passwordInput.value.trim();
      if (!email || !password) {
        authStatus.textContent = "请输入邮箱和密码";
        return;
      }
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) return (authStatus.textContent = data.error || "登录失败");
      updateAuthUI(email);
      authStatus.textContent = "登录成功";
    });

    logoutBtn.addEventListener("click", async () => {
      await fetch("/api/logout", { method: "POST" });
      updateAuthUI(null);
      authStatus.textContent = "已退出";
    });

    checkAuth();

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!authed) {
        statusEl.textContent = "请先登录";
        return;
      }
      const url = document.getElementById("url").value.trim();
      if (!url) return;
      resultEl.textContent = "";
      metaEl.textContent = "";
      downloadEl.style.display = "none";
      submitBtn.disabled = true;
      copyBtn.disabled = true;
      statusEl.textContent = "Pulling audio URL and transcribing (may take 30-90s)";
      let dots = 0;
      const tick = setInterval(() => {
        dots = (dots + 1) % 4;
        statusEl.textContent = "Transcribing" + ".".repeat(dots);
      }, 800);

      try {
        const res = await fetch("/api/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Transcription failed");

        clearInterval(tick);
        statusEl.textContent = "Done";
        metaEl.textContent = `Audio: ${data.audio_url}`;
        resultEl.textContent = data.transcript || "";
        if (data.file) {
          downloadEl.href = data.file;
          downloadEl.style.display = "inline";
        }
        if (data.transcript) {
          copyBtn.disabled = false;
        }
      } catch (err) {
        clearInterval(tick);
        statusEl.textContent = err.message;
      } finally {
        submitBtn.disabled = false;
      }
    });

    copyBtn.addEventListener("click", async () => {
      if (!resultEl.textContent) return;
      await navigator.clipboard.writeText(resultEl.textContent);
      statusEl.textContent = "已复制";
    });
  </script>
</body>
</html>
"""


def load_users() -> Dict[str, Any]:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_users(data: Dict[str, Any]) -> None:
    if USERS_FILE.parent:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(data), encoding="utf-8")


def find_audio_url(html: str) -> Optional[str]:
    # Prefer explicit audio tag
    match = re.search(r'<audio[^>]+src="([^"]+\.(?:m4a|mp3)[^"]*)"', html, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: first direct m4a/mp3 URL anywhere in the page
    alt = re.search(r'(https?://[^"\s]+\.(?:m4a|mp3)[^"\s<>]*)', html, flags=re.IGNORECASE)
    return alt.group(1) if alt else None


def parse_apple_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    episode_id = (qs.get("i") or [None])[0]
    podcast_id_match = re.search(r"/id(\d+)", parsed.path)
    podcast_id = podcast_id_match.group(1) if podcast_id_match else None
    return podcast_id, episode_id


def fetch_feed_url(podcast_id: str) -> str:
    resp = requests.get(
        f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast",
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results or not results[0].get("feedUrl"):
        raise RuntimeError("Feed URL not found from iTunes lookup.")
    return results[0]["feedUrl"]


def find_episode_audio(feed_url: str, episode_id: Optional[str]) -> str:
    resp = requests.get(feed_url, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Invalid RSS feed.")

    def enclosure_url(item: ET.Element) -> Optional[str]:
        enc = item.find("enclosure")
        return enc.attrib.get("url") if enc is not None else None

    for item in channel.findall("item"):
        guid = (item.findtext("guid") or "").strip()
        if episode_id and episode_id in guid:
            url = enclosure_url(item)
            if url:
                return url

    for item in channel.findall("item"):
        url = enclosure_url(item)
        if url:
            return url

    raise RuntimeError("Audio URL not found in RSS.")


def ms_to_ts(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_transcript(text: str, utterances: Optional[list]) -> str:
    if not utterances:
        return text
    parts = []
    for utt in utterances:
        start = ms_to_ts(int(utt.get("start", 0)))
        speaker = utt.get("speaker", "S")
        parts.append(f"[{start}] Speaker {speaker}: {utt.get('text','').strip()}")
    return "\n".join(parts)


def start_transcription(audio_url: str, headers: dict) -> str:
    payload = {
        "audio_url": audio_url,
        "language_code": "zh",  # default to Chinese
        "speaker_labels": True,  # request diarization/timestamps
    }
    resp = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def poll_transcription(transcript_id: str, headers: dict) -> Dict[str, Any]:
    polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    while True:
        poll = requests.get(polling_endpoint, headers=headers, timeout=20).json()
        status = poll.get("status")
        if status == "completed":
            return {
                "text": poll.get("text", ""),
                "utterances": poll.get("utterances") or [],
            }
        if status == "error":
            raise RuntimeError(poll.get("error", "AssemblyAI returned an error."))
        time.sleep(3)


@app.get("/")
def index() -> Response:
    return Response(HTML, mimetype="text/html")


@app.get("/api/me")
def me():
    return jsonify({"user": session.get("user")})


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "邮箱和密码必填"}), 400
    users = load_users()
    if email in users:
        return jsonify({"error": "该邮箱已注册"}), 400
    users[email] = {"password": password}
    save_users(users)
    session["user"] = email
    return jsonify({"user": email})


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    users = load_users()
    user = users.get(email)
    if not user or user.get("password") != password:
        return jsonify({"error": "邮箱或密码错误"}), 401
    session["user"] = email
    return jsonify({"user": email})


@app.post("/api/logout")
def logout():
    session.pop("user", None)
    return jsonify({"ok": True})


@app.post("/api/transcribe")
def transcribe():
    if not session.get("user"):
        return jsonify({"error": "请先登录"}), 401
    if not API_KEY:
        return jsonify({"error": "Set ASSEMBLYAI_API_KEY in your environment first."}), 500
    payload = request.get_json(silent=True) or {}
    episode_url = (payload.get("url") or "").strip()
    if not episode_url:
        return jsonify({"error": "Missing episode URL."}), 400

    headers = {"authorization": API_KEY}
    try:
        if "xiaoyuzhoufm.com" in episode_url:
            page = requests.get(episode_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            page.raise_for_status()
            audio_url = find_audio_url(page.text)
            if not audio_url:
                return jsonify({"error": "Audio src not found in page."}), 404
        elif "podcasts.apple.com" in episode_url:
            podcast_id, epi_id = parse_apple_url(episode_url)
            if not podcast_id:
                return jsonify({"error": "Invalid Apple Podcasts URL."}), 400
            feed_url = fetch_feed_url(podcast_id)
            audio_url = find_episode_audio(feed_url, epi_id)
        else:
            return jsonify({"error": "Only Xiaoyuzhou or Apple podcast links are supported."}), 400

        transcript_id = start_transcription(audio_url, headers)
        transcript_data = poll_transcription(transcript_id, headers)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    filename = f"transcript-{int(time.time())}.txt"
    filepath = TRANSCRIPT_DIR / filename
    formatted = format_transcript(transcript_data["text"], transcript_data.get("utterances"))
    filepath.write_text(formatted, encoding="utf-8")

    return jsonify(
        {
            "audio_url": audio_url,
            "transcript": formatted,
            "file": f"/transcripts/{filename}",
        }
    )


@app.get("/transcripts/<path:filename>")
def download_file(filename: str):
    return send_from_directory(TRANSCRIPT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
