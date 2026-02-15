# yt-transcript

A command-line tool that fetches YouTube video transcripts and cleans them up using Claude. It can also generate plain-English explanations, summaries, and TLDRs.

## Install

```
pip install git+https://github.com/t-clarky/yt-transcript.git
```

## Setup

You'll need an Anthropic API key for the Claude-powered features (cleanup, explain, summary, tldr).

1. Get a key at https://console.anthropic.com/settings/keys
2. Add it to your shell:

```
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

Not needed if you only use `--raw`.

## Usage

```
yt-transcript "https://youtube.com/watch?v=..."
```

You can also pass a short URL or just the video ID:

```
yt-transcript "https://youtu.be/dQw4w9WgXcQ"
yt-transcript dQw4w9WgXcQ
```

## Flags

| Flag | What it does |
|------|-------------|
| `--raw` | Skip Claude cleanup, just get the raw captions (free) |
| `--explain` | Generate a plain-English breakdown of the content |
| `--summary` | Generate a bulleted list of key points |
| `--tldr` | Generate a one-paragraph summary |

Flags can be combined:

```
yt-transcript --explain --summary --tldr "https://youtube.com/watch?v=..."
```

## Output

All files are saved to `~/transcripts/`:

- `video-title.md` — cleaned transcript
- `video-title-explained.md` — layman explanation
- `video-title-summary.md` — bullet-point summary
- `video-title-tldr.md` — one-paragraph TLDR

The transcript is also printed to the terminal.

## Cost

Uses Claude Sonnet 4.5. Typical costs per video:

- 5 min video — ~$0.01
- 20 min video — ~$0.03–0.05
- 1 hour video — ~$0.08–0.15

Each additional flag (explain, summary, tldr) adds a similar amount.
