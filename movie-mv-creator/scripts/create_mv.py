#!/usr/bin/env python3
"""
MV Creator - Assemble a music video from movie segments mapped to song timing.

Usage:
    python3 create_mv.py \
        --movie movie.mp4 \
        --music song.mp3 \
        --output output_mv.mp4 \
        --segments segments.json \
        [--fps 24] [--width 1920] [--height 1080] [--crf 18]

Segments JSON format:
[
  {
    "song_start": 0.0,
    "song_end": 15.0,
    "movie_start": 90,
    "movie_end": 120,
    "desc": "Opening section",
    "fade_in": true,
    "fade_out": false
  },
  ...
]
"""

import argparse
import subprocess
import json
import os
import sys
import shutil
import tempfile


def probe_duration(filepath):
    """Get media file duration in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json", "-show_format",
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0
    return float(json.loads(result.stdout)["format"]["duration"])


def probe_video_detail(filepath):
    """Get detailed video stream info."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json", "-show_streams",
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    info = json.loads(result.stdout)
    for s in info["streams"]:
        if s["codec_type"] == "video":
            return {
                "nb_frames": int(s.get("nb_frames", 0)),
                "duration": float(s.get("duration", 0)),
                "fps": s.get("r_frame_rate", "?"),
                "width": s.get("width", 0),
                "height": s.get("height", 0),
            }
    return {}


def extract_segment(seg, idx, movie_path, work_dir, fps, width, height, crf):
    """
    Extract a video segment from the movie, time-remapped to match song duration.

    CRITICAL: setpts factor = song_duration / movie_duration
      - < 1: speeds up the video (more footage compressed into less time)
      - > 1: slows down the video (less footage stretched over more time)
      - = 1: no speed change

    The fps filter AFTER setpts is essential for smooth playback.
    """
    seg_file = os.path.join(work_dir, f"seg_{idx:03d}.mp4")

    movie_start = seg["movie_start"]
    movie_dur = seg["movie_end"] - seg["movie_start"]
    song_dur = seg["song_end"] - seg["song_start"]

    if movie_dur <= 0 or song_dur <= 0:
        print(f"  [{idx:02d}] SKIP: invalid duration (movie={movie_dur}, song={song_dur})")
        return None

    # CORRECT direction for setpts
    pts_factor = song_dur / movie_dur

    vfilters = []

    # Time remapping (skip if factor is ~1.0)
    if abs(pts_factor - 1.0) > 0.01:
        vfilters.append(f"setpts={pts_factor:.6f}*PTS")

    # Constant frame rate (essential after setpts!)
    vfilters.append(f"fps={fps}")

    # Scale to target resolution with letterboxing
    vfilters.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
    vfilters.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black")

    # Fade effects
    if seg.get("fade_in"):
        vfilters.append("fade=t=in:st=0:d=2")
    if seg.get("fade_out"):
        fade_start = max(0, song_dur - 3)
        vfilters.append(f"fade=t=out:st={fade_start:.2f}:d=3")

    vf = ",".join(vfilters)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(movie_start),
        "-t", str(movie_dur),
        "-i", movie_path,
        "-vf", vf,
        "-t", str(song_dur),
        "-an",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        seg_file
    ]

    speed_pct = (movie_dur / song_dur) * 100
    desc = seg.get("desc", f"segment {idx}")
    print(f"  [{idx:02d}] {desc}")
    print(f"       Movie {movie_start:.0f}-{seg['movie_end']:.0f}s ({movie_dur:.0f}s) "
          f"-> Song {seg['song_start']:.0f}-{seg['song_end']:.0f}s ({song_dur:.0f}s) | "
          f"speed: {speed_pct:.0f}%")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"       ERROR: {result.stderr[-300:]}")
        return None

    detail = probe_video_detail(seg_file)
    if detail:
        actual_fps = detail["nb_frames"] / detail["duration"] if detail["duration"] > 0 else 0
        print(f"       -> {detail['duration']:.2f}s, {detail['nb_frames']} frames, {actual_fps:.1f} fps")

    return seg_file


def concatenate_with_crossfades(segment_files, output_path, work_dir, fps, crf, xfade=0.3):
    """Concatenate video segments with short crossfade transitions."""
    valid = [f for f in segment_files if f is not None]
    n = len(valid)

    if n == 0:
        return False
    if n == 1:
        shutil.copy2(valid[0], output_path)
        return True

    # Get durations
    durations = [probe_duration(f) for f in valid]

    # Add fade-in/out at segment boundaries
    processed = []
    for i, (f, dur) in enumerate(zip(valid, durations)):
        out = os.path.join(work_dir, f"xf_{i:03d}.mp4")
        vf_parts = []
        if i > 0:
            vf_parts.append(f"fade=t=in:st=0:d={xfade}")
        if i < n - 1:
            fade_start = max(0, dur - xfade)
            vf_parts.append(f"fade=t=out:st={fade_start:.3f}:d={xfade}")

        if vf_parts:
            vf = ",".join(vf_parts)
            cmd = [
                "ffmpeg", "-y", "-i", f,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-an", out
            ]
            subprocess.run(cmd, capture_output=True, text=True)
        else:
            shutil.copy2(f, out)
        processed.append(out)

    # Concat via demuxer
    concat_file = os.path.join(work_dir, "concat.txt")
    with open(concat_file, "w") as fh:
        for p in processed:
            fh.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-r", str(fps), "-pix_fmt", "yuv420p",
        output_path
    ]

    print("\nConcatenating with crossfades...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[-500:]}")
        return False
    return True


def add_audio(video_path, audio_path, output_path):
    """Combine video with audio track."""
    vdur = probe_duration(video_path)
    adur = probe_duration(audio_path)
    final = min(vdur, adur)

    print(f"\nVideo: {vdur:.2f}s | Audio: {adur:.2f}s | Final: {final:.1f}s")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", str(final),
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[-300:]}")
        return False
    return True


def color_grade(input_path, output_path, crf):
    """Apply subtle cinematic color grading."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "eq=contrast=1.08:brightness=-0.02:saturation=0.9",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-c:a", "copy",
        output_path
    ]
    print("\nApplying color grade...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Create an MV from movie segments + song")
    parser.add_argument("--movie", required=True, help="Path to movie file")
    parser.add_argument("--music", required=True, help="Path to music/song file")
    parser.add_argument("--output", required=True, help="Output MV file path")
    parser.add_argument("--segments", required=True, help="Path to segments.json")
    parser.add_argument("--fps", type=int, default=24, help="Target frame rate (default: 24)")
    parser.add_argument("--width", type=int, default=1920, help="Output width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Output height (default: 1080)")
    parser.add_argument("--crf", type=int, default=18, help="Encoding quality 0-51, lower=better (default: 18)")
    parser.add_argument("--no-grade", action="store_true", help="Skip color grading")
    args = parser.parse_args()

    for path, name in [(args.movie, "Movie"), (args.music, "Music"), (args.segments, "Segments")]:
        if not os.path.exists(path):
            print(f"Error: {name} file not found: {path}")
            sys.exit(1)

    with open(args.segments) as f:
        segments = json.load(f)

    print("=" * 60)
    print("  MV CREATOR")
    print("=" * 60)
    print(f"  Movie:    {args.movie}")
    print(f"  Music:    {args.music}")
    print(f"  Segments: {len(segments)}")
    print(f"  Output:   {args.output}")
    print()

    work_dir = tempfile.mkdtemp(prefix="mv_creator_")

    try:
        # Step 1: Extract segments
        print("[STEP 1] Extracting video segments...")
        print("-" * 50)
        seg_files = []
        for i, seg in enumerate(segments):
            sf = extract_segment(seg, i, args.movie, work_dir,
                                 args.fps, args.width, args.height, args.crf)
            seg_files.append(sf)

        valid = sum(1 for s in seg_files if s)
        print(f"\nExtracted {valid}/{len(segments)} segments")

        if valid < len(segments) * 0.5:
            print("Too many failed segments. Aborting.")
            sys.exit(1)

        # Step 2: Concatenate
        print("\n[STEP 2] Concatenating...")
        print("-" * 50)
        raw = os.path.join(work_dir, "raw.mp4")
        if not concatenate_with_crossfades(seg_files, raw, work_dir, args.fps, args.crf):
            sys.exit(1)

        # Step 3: Add audio
        print("\n[STEP 3] Adding audio...")
        print("-" * 50)
        with_audio = os.path.join(work_dir, "with_audio.mp4")
        if not add_audio(raw, args.music, with_audio):
            sys.exit(1)

        # Step 4: Color grade (optional)
        if not args.no_grade:
            print("\n[STEP 4] Color grading...")
            print("-" * 50)
            if not color_grade(with_audio, args.output, args.crf):
                shutil.copy2(with_audio, args.output)
        else:
            shutil.copy2(with_audio, args.output)

        # Verify
        detail = probe_video_detail(args.output)
        dur = probe_duration(args.output)
        size_mb = os.path.getsize(args.output) / (1024 * 1024)

        print(f"\n{'=' * 60}")
        print(f"  MV COMPLETE!")
        print(f"  File:       {args.output}")
        print(f"  Duration:   {dur:.1f}s ({dur/60:.1f} min)")
        print(f"  Resolution: {detail.get('width','?')}x{detail.get('height','?')} @ {detail.get('fps','?')} fps")
        print(f"  Frames:     {detail.get('nb_frames','?')}")
        print(f"  Size:       {size_mb:.1f} MB")
        print(f"{'=' * 60}")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
