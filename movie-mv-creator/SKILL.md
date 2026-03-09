---
name: movie-mv-creator
description: "Create music videos by intelligently matching movie scenes to song lyrics. Supports frame sampling analysis, emotion-lyrics scene matching, time-remapped video editing with ffmpeg, crossfade transitions, and cinematic color grading. Input: a movie file + a music file. Output: a complete MV in mp4 format."
metadata:
  tags: video-editing, mv, music-video, ffmpeg, movie, scene-matching
  author: claude-agent
  version: 1.3.0
---

# Movie MV Creator

Create music videos by matching movie scenes to song lyrics/emotions using AI-powered frame analysis and ffmpeg-based video editing.

## When to Use This Skill

- User wants to create an MV (music video) from a movie + song
- User wants to match movie scenes to song lyrics/emotions
- User wants to extract and re-edit movie clips synced to music
- User needs to do intelligent frame sampling and scene identification from a long video

## Prerequisites

- **ffmpeg** and **ffprobe** installed (with libx264, aac support)
- **Python 3.10+** with Pillow (`pip3 install Pillow`)
- A movie file (mp4/mkv/avi)
- A music/song file (mp3/wav/aac)

## Workflow Overview

The MV creation follows a 4-phase pipeline:

### Phase 1: Intelligent Frame Sampling & Content Boundary Detection

Sample frames from the movie at regular intervals to build a visual scene index and **immediately identify valid content boundaries**.

**CRITICAL RULE: Identify Intro/Outro**
- Before any scene matching, you MUST identify the exact timestamps where the actual movie content starts (after production logos/opening credits) and ends (before the credit scroll/end titles).
- **Goal**: Prevent the MV from including static credits or scrolling text, which ruins the cinematic experience.
- Use dense sampling (every 1-5s) at the beginning and end of the file if the 30s sampling is ambiguous.

### Phase 2: Lyrics-Scene Mapping

Structure the song into emotional sections and map each to appropriate movie scenes.

**CRITICAL RULE: "Original Speed Fast-Cut" Strategy**
- **Goal**: Avoid unnatural "chipmunk" speed-up effects. The user prefers multiple short cuts over one long, sped-up sequence.
- **Rule**: `movie_duration` MUST match `song_duration` as closely as possible (target 1.0x speed).
- **Strategy**:
    - **Do NOT** force a long movie scene (e.g., 80s) into a short song segment (e.g., 45s). This causes unwanted 1.7x speed-up.
    - **Instead**, split the song segment into smaller beats/bars.
    - **Match** each small beat with a short, distinct movie clip (2-5s) at its original speed.
    - **Acceptable Speed Range**: Keep playback speed between **0.8x (slight slow-mo) and 1.2x (slight fast)**. Outside this range, you must crop the footage or split the segment.

**Steps:**
1. **Divide the song** into sections. If a section is fast-paced, split it further into individual beats.
2. **Identify emotional tone** of each section.
3. **Match movie scenes** strictly adhering to the "No Reuse" and "Original Speed" rules.
4. **CRITICAL RULE: No Reuse**: Do NOT reuse the same movie footage multiple times.
5. **Define segments** ensuring `(movie_end - movie_start) ≈ (song_end - song_start)`.

### Phase 3: Video Segment Extraction with Time Remapping

Extract each movie segment. Use time remapping ONLY for subtle adjustments, not for duration fitting.

**CRITICAL: The setpts formula & Speed Check**

```python
# Speed = Movie Duration / Song Duration
# Example: 80s movie / 45s song = 1.77x speed (TOO FAST)
speed = (movie_end - movie_start) / (song_end - song_start)

if speed > 1.3:
    # Action: REJECT or CROP. Do not time-remap.
    # Logic: Reduce movie_end to match song_duration * 1.0
    movie_end = movie_start + (song_end - song_start)
    pts_factor = 1.0
elif speed < 0.7:
    # Action: Acceptable for slow-motion effect, but warn if too slow.
    pts_factor = song_dur / movie_dur
else:
    # Standard subtle adjustment
    pts_factor = song_dur / movie_dur
```

**Complete ffmpeg command for segment extraction:**
```bash
ffmpeg -y \
  -ss {movie_start} -t {movie_duration} \
  -i movie.mp4 \
  -vf "setpts={pts_factor}*PTS,fps=24,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black" \
  -t {song_duration} \
  -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  segment.mp4
```

### Phase 4: Assembly & Post-Processing

1. **Add crossfade transitions** (0.3s).
2. **Concatenate** all segments.
3. **Add the audio** track.
4. **CRITICAL RULE: Audio-Sync Termination**: Ensure the video ends exactly when the audio ends. Truncate video if necessary.
5. **Apply color grading** for cinematic look.

## Usage

### Quick Start
```bash
python3 skills/movie-mv-creator/scripts/create_mv.py \
  --movie "path/to/movie.mp4" \
  --music "path/to/song.mp3" \
  --output "path/to/output_mv.mp4" \
  --segments "path/to/segments.json"
```

## Common Pitfalls

| Pitfall | Cause | Fix |
|---------|-------|-----|
| **Unnatural Speed-up (Benny Hill effect)** | Forcing long clips into short audio | **Enable "Fast-Cut" mode**: Crop clip to match audio length or split audio into smaller beats. Keep speed ~1.0x. |
| **Credits in MV** | Failing to identify intro/outro | **Mandatory check in Phase 1** |
| **Visual Repetitiveness** | Reusing movie clips | Ensure each segment uses a unique movie timestamp range |
| **Silent Video at End** | Video longer than audio | Truncate video to match exact audio duration in Phase 4 |
| Choppy/dropped frames | Missing `fps=N` filter | Add `fps=24` after `setpts` |

## Tips
- **Original Speed Priority**: Always prefer cropping a 10s clip to 5s over speeding it up 2x.
- **Fast Cuts for Energy**: For fast songs, use many short 2-3s clips (1.0x speed) instead of one fast-forwarded long clip.
- **No-Reuse Strategy**: Mark movie time-ranges as "used" after assigning them.
- **Audio-First Ending**: Use `-shortest` in the final ffmpeg concat command.