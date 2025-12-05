# Podcast Transcriptor

Both Xiaoyuzhou & Apple doesn't allow you to directly get a transcript, so I made one.

The interface is in chinese but should be intuitive enough for you to use. 

Paste a Xiaoyuzhou or Apple Podcasts episode URL, the app grabs the audio URL, sends it to AssemblyAI for transcription, and saves the text as a `.txt` you can download.

### The model currently is using AssemblyAI, switch to your own if you want others

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

Open http://localhost:8000 in your browser, paste an episode link (e.g., `https://www.xiaoyuzhoufm.com/episode/...` or `https://podcasts.apple.com/...?...i=...`), and click **转录**. When finished, the page shows the transcript and a link to download the `.txt` file.

## For further imporvement

1. The chinese transcription accuracy is sub-par, need to look at a new provider for such