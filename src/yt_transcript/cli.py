#!/usr/bin/env python3
"""yt-transcript: Fetch and clean YouTube transcripts."""

import argparse
import os
import re
import sys
from pathlib import Path

import anthropic
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

CLEANUP_MODEL = "claude-haiku-4-5-20251001"
SMART_MODEL = "claude-sonnet-4-5-20250929"
CHUNK_SIZE_WORDS = 3000

# Pricing per million tokens
HAIKU_INPUT_COST = 0.80
HAIKU_OUTPUT_COST = 4.00
SONNET_INPUT_COST = 3.00
SONNET_OUTPUT_COST = 15.00


class TokenTracker:
    def __init__(self):
        self.haiku_input = 0
        self.haiku_output = 0
        self.sonnet_input = 0
        self.sonnet_output = 0

    def add(self, usage, model):
        if model == CLEANUP_MODEL:
            self.haiku_input += usage.input_tokens
            self.haiku_output += usage.output_tokens
        else:
            self.sonnet_input += usage.input_tokens
            self.sonnet_output += usage.output_tokens

    def total_cost(self):
        cost = 0
        cost += (self.haiku_input / 1_000_000) * HAIKU_INPUT_COST
        cost += (self.haiku_output / 1_000_000) * HAIKU_OUTPUT_COST
        cost += (self.sonnet_input / 1_000_000) * SONNET_INPUT_COST
        cost += (self.sonnet_output / 1_000_000) * SONNET_OUTPUT_COST
        return cost

    def report(self):
        total_in = self.haiku_input + self.sonnet_input
        total_out = self.haiku_output + self.sonnet_output
        cost = self.total_cost()
        print(f"\nTokens used: {total_in:,} in / {total_out:,} out")
        print(f"Estimated cost: ${cost:.4f}")


tracker = TokenTracker()


def extract_video_id(url_or_id: str) -> str:
    """Extract a YouTube video ID from a URL or return it if already an ID."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url_or_id):
        return url_or_id

    return None


def get_video_title(video_id: str) -> str:
    """Fetch the video title using yt-dlp without downloading the video."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("title", video_id)


def fetch_transcript(video_id: str) -> str:
    """Fetch and combine transcript segments into a single block of text."""
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    parts = [snippet.text for snippet in transcript]
    return " ".join(parts)


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE_WORDS) -> list[str]:
    """Split text into chunks of approximately chunk_size words."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
    return chunks


def call_claude(prompt: str, model: str = SMART_MODEL) -> str:
    """Send a prompt to Claude and return the response text."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    tracker.add(message.usage, model)
    return message.content[0].text


def clean_transcript(raw_text: str, start_chunk: int = 0) -> str:
    """Clean the transcript in chunks using Haiku."""
    chunks = split_into_chunks(raw_text)
    total = len(chunks)
    cleaned_parts = []

    if total == 1:
        print("Cleaning transcript with Claude...")
        cleaned = call_claude(
            "Below is a raw YouTube transcript. Clean it up by adding proper "
            "punctuation, capitalization, and paragraph breaks. Fix obvious "
            "transcription errors where the intended word is clear. Keep the "
            "content exactly as spoken — do not summarize, rephrase, or omit "
            "anything. Do not add any commentary, headers, or notes. Return "
            f"only the cleaned transcript text.\n\n{chunks[0]}",
            model=CLEANUP_MODEL,
        )
        return cleaned, total, total

    for i, chunk in enumerate(chunks):
        if i < start_chunk:
            cleaned_parts.append(chunk)
            continue
        print(f"Cleaning chunk {i + 1}/{total}...")
        try:
            cleaned = call_claude(
                "Clean up this transcript segment — add punctuation, paragraphs, "
                "and fix obvious transcription errors. Keep the content exactly as "
                "spoken. This is part of a longer transcript so don't add any "
                f"introduction or conclusion.\n\n{chunk}",
                model=CLEANUP_MODEL,
            )
            cleaned_parts.append(cleaned)
        except anthropic.APIError as e:
            print(
                f"\nError on chunk {i + 1}/{total}: {e}",
                file=sys.stderr,
            )
            if cleaned_parts:
                partial = "\n\n".join(cleaned_parts)
                return partial, i, total
            raise

    return "\n\n".join(cleaned_parts), total, total


def explain_transcript(transcript: str) -> str:
    """Send the transcript to Claude for a plain-English explanation."""
    return call_claude(
        "Below is a transcript from a YouTube video. Explain the content "
        "to me like I'm not an expert. Break down any jargon, technical "
        "concepts, or complex ideas in plain, everyday English. Organise "
        "it clearly with headings and short paragraphs. Don't skip "
        "anything important — I want to fully understand what was said, "
        f"just in simpler terms.\n\n{transcript}"
    )


def summarize_transcript(transcript: str) -> str:
    """Send the transcript to Claude for a key-points summary."""
    return call_claude(
        "Below is a transcript from a YouTube video. Give me a clear "
        "summary of the key points as a bulleted list. Each bullet should "
        "be one or two sentences. Keep the language simple and plain. "
        "Cover all the main ideas without unnecessary detail.\n\n"
        f"{transcript}"
    )


def tldr_transcript(transcript: str) -> str:
    """Send the transcript to Claude for a one-paragraph TLDR."""
    return call_claude(
        "Below is a transcript from a YouTube video. Give me a single "
        "short paragraph (3-5 sentences max) that captures the core "
        "message. Write it in plain, simple English. No bullet points, "
        f"no headings — just one tight paragraph.\n\n{transcript}"
    )


def sanitize_filename(title: str) -> str:
    """Turn a video title into a safe filename."""
    name = re.sub(r"[^\w\s-]", "", title)
    name = re.sub(r"\s+", "-", name.strip())
    return name.lower()


def check_api_key():
    """Check that the Anthropic API key is set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY environment variable is not set. "
            "Use --raw to skip Claude processing, or set your API key.",
            file=sys.stderr,
        )
        sys.exit(1)


def save_and_print(text: str, output_path: Path, label: str):
    """Save text to a file and print it to the terminal."""
    output_path.write_text(text, encoding="utf-8")
    print(f"{label} saved to {output_path}\n")
    print(text)
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="yt-transcript",
        description="Fetch a YouTube transcript and optionally clean it up with Claude.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube URL or video ID",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip Claude cleanup and output the unprocessed transcript",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Add a plain-English explanation of the content",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Add a bulleted summary of key points",
    )
    parser.add_argument(
        "--tldr",
        action="store_true",
        help="Add a one-paragraph TLDR",
    )
    parser.add_argument(
        "--from-raw",
        metavar="FILE",
        help="Re-run cleanup on an existing .raw.md file instead of fetching from YouTube",
    )
    args = parser.parse_args()

    if not args.url and not args.from_raw:
        parser.error("Provide a YouTube URL/ID or use --from-raw FILE")

    # --from-raw mode: load raw text from file, derive base_name from filename
    if args.from_raw:
        raw_path = Path(args.from_raw)
        if not raw_path.exists():
            print(f"Error: File not found: {raw_path}", file=sys.stderr)
            sys.exit(1)
        raw_text = raw_path.read_text(encoding="utf-8")
        # Derive base_name: strip .raw.md from filename
        fname = raw_path.name
        if fname.endswith(".raw.md"):
            base_name = fname[: -len(".raw.md")]
        else:
            base_name = raw_path.stem
        title = base_name
        output_dir = raw_path.parent
        print(f"Loaded raw transcript from {raw_path} ({len(raw_text.split()):,} words)\n")
    else:
        # Normal mode: fetch from YouTube
        video_id = extract_video_id(args.url)
        if not video_id:
            print(f"Error: Could not parse a video ID from '{args.url}'", file=sys.stderr)
            sys.exit(1)

        try:
            title = get_video_title(video_id)
        except Exception as e:
            print(f"Error fetching video title: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Video: {title}\n")

        try:
            raw_text = fetch_transcript(video_id)
        except Exception as e:
            error_msg = str(e)
            if "No transcripts" in error_msg or "TranscriptsDisabled" in error_msg:
                print("Error: No captions/transcripts are available for this video.", file=sys.stderr)
            elif "VideoUnavailable" in error_msg:
                print("Error: This video is unavailable.", file=sys.stderr)
            else:
                print(f"Error fetching transcript: {e}", file=sys.stderr)
            sys.exit(1)

        output_dir = Path.home() / "transcripts"
        base_name = sanitize_filename(title)

    output_dir.mkdir(exist_ok=True)

    # Always save raw transcript
    raw_path = output_dir / f"{base_name}.raw.md"
    raw_path.write_text(raw_text, encoding="utf-8")
    print(f"Raw transcript saved to {raw_path}")

    needs_claude = not args.raw or args.explain or args.summary or args.tldr
    if needs_claude:
        check_api_key()

    try:
        if args.raw:
            transcript = raw_text
        else:
            word_count = len(raw_text.split())
            chunk_count = max(1, (word_count + CHUNK_SIZE_WORDS - 1) // CHUNK_SIZE_WORDS)
            print(f"Transcript: {word_count:,} words ({chunk_count} chunk{'s' if chunk_count > 1 else ''})\n")

            transcript, completed, total = clean_transcript(raw_text)

            if completed < total:
                print(
                    f"\nPartial cleanup: {completed}/{total} chunks completed.",
                    file=sys.stderr,
                )
                print(
                    f"To resume, fix the issue and run:\n"
                    f"  yt-transcript --from-raw \"{raw_path}\"",
                    file=sys.stderr,
                )

        transcript_path = output_dir / f"{base_name}.md"
        save_and_print(transcript, transcript_path, "Transcript")

        if args.explain:
            print("Generating plain-English explanation...")
            explanation = explain_transcript(transcript)
            explain_path = output_dir / f"{base_name}-explained.md"
            save_and_print(explanation, explain_path, "Explanation")

        if args.summary:
            print("Generating summary...")
            summary = summarize_transcript(transcript)
            summary_path = output_dir / f"{base_name}-summary.md"
            save_and_print(summary, summary_path, "Summary")

        if args.tldr:
            print("Generating TLDR...")
            tldr = tldr_transcript(transcript)
            tldr_path = output_dir / f"{base_name}-tldr.md"
            save_and_print(tldr, tldr_path, "TLDR")

    except anthropic.APIError as e:
        print(f"Error calling Anthropic API: {e}", file=sys.stderr)
        print(f"Raw transcript is saved at: {raw_path}", file=sys.stderr)
        sys.exit(1)

    tracker.report()


if __name__ == "__main__":
    main()
