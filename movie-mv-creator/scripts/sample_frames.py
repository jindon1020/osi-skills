#!/usr/bin/env python3
"""
Frame Sampler - Extract frames from a video at regular intervals for scene analysis.

Usage:
    python3 sample_frames.py --movie movie.mp4 --output-dir ./frames [--interval 30] [--width 640]
"""

import argparse
import subprocess
import json
import os
import sys


def get_video_info(movie_path):
    """Get video duration and basic info."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        movie_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error probing video: {result.stderr}")
        sys.exit(1)

    info = json.loads(result.stdout)
    fmt = info["format"]
    duration = float(fmt["duration"])

    video_stream = None
    for s in info["streams"]:
        if s["codec_type"] == "video" and s.get("codec_name") != "mjpeg":
            video_stream = s
            break

    return {
        "duration": duration,
        "duration_min": duration / 60,
        "width": int(video_stream["width"]) if video_stream else 0,
        "height": int(video_stream["height"]) if video_stream else 0,
        "fps": video_stream.get("r_frame_rate", "24/1") if video_stream else "24/1",
    }


def sample_frames(movie_path, output_dir, interval=30, width=640):
    """Extract frames at regular intervals."""
    os.makedirs(output_dir, exist_ok=True)

    info = get_video_info(movie_path)
    expected_frames = int(info["duration"] / interval) + 1

    print(f"Video: {info['duration']:.0f}s ({info['duration_min']:.1f} min)")
    print(f"Resolution: {info['width']}x{info['height']}")
    print(f"Sampling every {interval}s → ~{expected_frames} frames")
    print(f"Output: {output_dir}/")
    print()

    cmd = [
        "ffmpeg", "-y",
        "-i", movie_path,
        "-vf", f"fps=1/{interval},scale={width}:-1",
        "-q:v", "3",
        os.path.join(output_dir, "frame_%04d.jpg")
    ]

    print("Extracting frames...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr[-500:]}")
        sys.exit(1)

    # Count extracted frames
    frames = [f for f in os.listdir(output_dir) if f.startswith("frame_") and f.endswith(".jpg")]
    print(f"Extracted {len(frames)} frames")
    print()

    # Generate index
    index_file = os.path.join(output_dir, "frame_index.txt")
    with open(index_file, "w") as f:
        f.write(f"# Frame Index for: {os.path.basename(movie_path)}\n")
        f.write(f"# Interval: {interval}s | Total: {len(frames)} frames\n")
        f.write(f"# Frame N → timestamp = N * {interval} seconds\n\n")
        for i in range(1, len(frames) + 1):
            ts = i * interval
            minutes = ts // 60
            seconds = ts % 60
            f.write(f"frame_{i:04d}.jpg → {minutes:02d}:{seconds:02d} ({ts}s)\n")

    print(f"Index written to: {index_file}")
    return len(frames)


def main():
    parser = argparse.ArgumentParser(description="Sample frames from a video for scene analysis")
    parser.add_argument("--movie", required=True, help="Path to the movie file")
    parser.add_argument("--output-dir", required=True, help="Directory to save extracted frames")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between frame samples (default: 30)")
    parser.add_argument("--width", type=int, default=640, help="Output frame width in pixels (default: 640)")
    args = parser.parse_args()

    if not os.path.exists(args.movie):
        print(f"Error: Movie file not found: {args.movie}")
        sys.exit(1)

    sample_frames(args.movie, args.output_dir, args.interval, args.width)


if __name__ == "__main__":
    main()
