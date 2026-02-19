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
| `--from-raw FILE` | Re-run cleanup from a saved `.raw.md` file (skips YouTube fetch) |

Flags can be combined:

```
yt-transcript --explain --summary --tldr "https://youtube.com/watch?v=..."
```

## Re-running from a saved raw file

Every run saves the raw transcript to a `.raw.md` file. If cleanup fails or you want to re-process it later, use:

```
yt-transcript --from-raw ~/transcripts/video-title.raw.md
yt-transcript --from-raw ~/transcripts/video-title.raw.md --explain --summary
```

## Output

All files are saved to `~/transcripts/`:

- `video-title.raw.md` — unprocessed captions (always saved)
- `video-title.md` — cleaned transcript
- `video-title-explained.md` — layman explanation
- `video-title-summary.md` — bullet-point summary
- `video-title-tldr.md` — one-paragraph TLDR

The transcript is also printed to the terminal.

## How it handles long videos

Long transcripts are automatically split into ~3000-word chunks, each cleaned separately using Claude Haiku (cheaper and fast). You'll see progress like:

```
Cleaning chunk 1/8...
Cleaning chunk 2/8...
```

If cleanup fails partway through, whatever was cleaned so far is saved and you're shown a command to resume.

## Cost

Cleanup uses Claude Haiku 4.5. The explain/summary/tldr flags use Claude Sonnet 4.5.

After each run, token usage and estimated cost are printed:

```
Tokens used: 12,450 in / 11,200 out
Estimated cost: $0.0145
```

Typical cleanup costs:

- 5 min video — less than $0.01
- 20 min video — ~$0.01–0.02
- 1 hour video — ~$0.03–0.05
- 2 hour video — ~$0.05–0.10

Each additional flag (explain, summary, tldr) adds a few cents.
