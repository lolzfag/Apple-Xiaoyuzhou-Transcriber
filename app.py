import os
import re
import time
import pathlib
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

import requests
from flask import Flask, jsonify, request, send_from_directory, Response

API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
TRANSCRIPT_DIR = pathlib.Path("transcripts")
TRANSCRIPT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

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
    <h1>小宇宙转录</h1>
    <p>粘贴小宇宙节目链接，点击转录，会自动抓取音频地址并生成文本。</p>
    <form id="form">
      <input id="url" name="url" type="url" placeholder="https://www.xiaoyuzhoufm.com/episode/..." required>
      <button id="submit" type="submit">转录</button>
    </form>
    <div id="status"></div>
    <div id="meta"></div>
    <pre id="result"></pre>
    <p><a id="download" href="#" style="display:none;">下载 .txt</a></p>
  </main>
  <script>
    const form = document.getElementById("form");
    const statusEl = document.getElementById("status");
    const metaEl = document.getElementById("meta");
    const resultEl = document.getElementById("result");
    const downloadEl = document.getElementById("download");
    const submitBtn = document.getElementById("submit");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const url = document.getElementById("url").value.trim();
      if (!url) return;
      resultEl.textContent = "";
      metaEl.textContent = "";
      downloadEl.style.display = "none";
      submitBtn.disabled = true;
      statusEl.textContent = "Pulling audio URL and transcribing...";

      try {
        const res = await fetch("/api/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Transcription failed");

        statusEl.textContent = "Done";
        metaEl.textContent = `Audio: ${data.audio_url}`;
        resultEl.textContent = data.transcript || "";
        if (data.file) {
          downloadEl.href = data.file;
          downloadEl.style.display = "inline";
        }
      } catch (err) {
        statusEl.textContent = err.message;
      } finally {
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def find_audio_url(html: str) -> Optional[str]:
    match = re.search(r'<audio[^>]+src="([^"]+\\.m4a[^"]*)"', html, flags=re.IGNORECASE)
    return match.group(1) if match else None


def start_transcription(audio_url: str, headers: dict) -> str:
    resp = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=headers,
        json={"audio_url": audio_url},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def poll_transcription(transcript_id: str, headers: dict) -> str:
    polling_endpoint = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    while True:
        poll = requests.get(polling_endpoint, headers=headers, timeout=20).json()
        status = poll.get("status")
        if status == "completed":
            return poll.get("text", "")
        if status == "error":
            raise RuntimeError(poll.get("error", "AssemblyAI returned an error."))
        time.sleep(3)


@app.get("/")
def index() -> Response:
    return Response(HTML, mimetype="text/html")


@app.post("/api/transcribe")
def transcribe():
    if not API_KEY:
        return jsonify({"error": "Set ASSEMBLYAI_API_KEY in your environment first."}), 500
    payload = request.get_json(silent=True) or {}
    episode_url = (payload.get("url") or "").strip()
    if not episode_url:
        return jsonify({"error": "Missing episode URL."}), 400

    try:
        page = requests.get(episode_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        page.raise_for_status()
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch episode page: {exc}"}), 502

    audio_url = find_audio_url(page.text)
    if not audio_url:
        return jsonify({"error": "Audio src not found in page."}), 404

    headers = {"authorization": API_KEY}
    try:
        transcript_id = start_transcription(audio_url, headers)
        text = poll_transcription(transcript_id, headers)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    filename = f"transcript-{int(time.time())}.txt"
    filepath = TRANSCRIPT_DIR / filename
    filepath.write_text(text, encoding="utf-8")

    return jsonify(
        {
            "audio_url": audio_url,
            "transcript": text,
            "file": f"/transcripts/{filename}",
        }
    )


@app.get("/transcripts/<path:filename>")
def download_file(filename: str):
    return send_from_directory(TRANSCRIPT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=8000)
