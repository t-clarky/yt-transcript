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


def extract_video_id(url_or_id: str) -> str:
    """Extract a YouTube video ID from a URL or return it if already an ID."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # Check if it's already a bare video ID
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


def call_claude(prompt: str) -> str:
    """Send a prompt to Claude and return the response text."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def clean_transcript(raw_text: str) -> str:
    """Send the raw transcript to Claude for cleanup."""
    return call_claude(
        "Below is a raw YouTube transcript. Clean it up by adding proper "
        "punctuation, capitalization, and paragraph breaks. Fix obvious "
        "transcription errors where the intended word is clear. Keep the "
        "content exactly as spoken — do not summarize, rephrase, or omit "
        "anything. Do not add any commentary, headers, or notes. Return "
        f"only the cleaned transcript text.\n\n{raw_text}"
    )


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
    args = parser.parse_args()

    needs_claude = not args.raw or args.explain or args.summary or args.tldr
    if needs_claude:
        check_api_key()

    # Extract video ID
    video_id = extract_video_id(args.url)
    if not video_id:
        print(f"Error: Could not parse a video ID from '{args.url}'", file=sys.stderr)
        sys.exit(1)

    # Fetch video title
    try:
        title = get_video_title(video_id)
    except Exception as e:
        print(f"Error fetching video title: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Video: {title}\n")

    # Fetch transcript
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

    # Set up output directory
    output_dir = Path.home() / "transcripts"
    output_dir.mkdir(exist_ok=True)
    base_name = sanitize_filename(title)

    try:
        # Clean or raw transcript
        if args.raw:
            transcript = raw_text
        else:
            print("Cleaning transcript with Claude...")
            transcript = clean_transcript(raw_text)

        transcript_path = output_dir / f"{base_name}.md"
        save_and_print(transcript, transcript_path, "Transcript")

        # Explain
        if args.explain:
            print("Generating plain-English explanation...")
            explanation = explain_transcript(transcript)
            explain_path = output_dir / f"{base_name}-explained.md"
            save_and_print(explanation, explain_path, "Explanation")

        # Summary
        if args.summary:
            print("Generating summary...")
            summary = summarize_transcript(transcript)
            summary_path = output_dir / f"{base_name}-summary.md"
            save_and_print(summary, summary_path, "Summary")

        # TLDR
        if args.tldr:
            print("Generating TLDR...")
            tldr = tldr_transcript(transcript)
            tldr_path = output_dir / f"{base_name}-tldr.md"
            save_and_print(tldr, tldr_path, "TLDR")

    except anthropic.APIError as e:
        print(f"Error calling Anthropic API: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
