# Xiaoyuzhou Transcript Helper

Paste a Xiaoyuzhou episode URL, the app grabs the embedded audio URL, sends it to AssemblyAI for transcription, and saves the text as a `.txt` you can download.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your AssemblyAI API key:
   ```bash
   export ASSEMBLYAI_API_KEY=your_key_here
   ```

## Run

```bash
python app.py
```

Open http://localhost:8000 in your browser, paste an episode link (e.g., `https://www.xiaoyuzhoufm.com/episode/...`), and click **转录**. When finished, the page shows the transcript and a link to download the `.txt` file.
