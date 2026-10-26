"""Assemble the observed clips from record_demo.cjs into a captioned local rehearsal.

Requires development-only imageio-ffmpeg (or --ffmpeg). No narration or music is added.
"""
import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg')
    args = parser.parse_args()
    encoder = args.ffmpeg
    if not encoder:
        import imageio_ffmpeg
        encoder = imageio_ffmpeg.get_ffmpeg_exe()
    data = json.loads((args.input_dir / 'clips.json').read_text(encoding='utf-8'))
    clips = data['clips']
    duration = sum(c['end'] - c['start'] for c in clips)
    if len(clips) != 10 or not 0 < duration < 120 or any(c['start'] < 0 or c['end'] <= c['start'] for c in clips):
        raise ValueError('Expected ten complete clips totaling less than two minutes.')
    parts = args.input_dir / 'parts'
    parts.mkdir(exist_ok=True)
    # Browser recording timestamps can drift relative to the harness wall clock.
    # Read tiny color markers from the actual video; crop them from the final edit.
    samples = subprocess.run([encoder, '-hide_banner', '-loglevel', 'error', '-i',
                              str(args.input_dir / 'rehearsal-raw.webm'), '-vf',
                              'fps=5,crop=4:4:2:ih-6,scale=1:1:flags=area,format=rgb24',
                              '-f', 'rawvideo', '-'], check=True, capture_output=True).stdout
    pixels = [tuple(samples[i:i+3]) for i in range(0, len(samples), 3)]
    cursor = 0
    observed = []
    for number, clip in enumerate(clips):
        color = tuple(int(clip['marker'][i:i+2], 16) for i in (1, 3, 5))
        hits = [i for i, pixel in enumerate(pixels) if i >= cursor and sum(abs(a-b) for a, b in zip(pixel, color)) < 70]
        if len(hits) < 10:
            raise ValueError(f"Missing video marker for {clip['name']}; do not use an unaligned edit.")
        start = (hits[0] + 2) / 5
        length = min(clip['end'] - clip['start'], (hits[-1] - 1) / 5 - start)
        if length < 1:
            raise ValueError(f"Clip {clip['name']} has no usable footage.")
        cursor = int((start + length) * 5)
        observed.append({'name': clip['name'], 'source_start': start, 'duration': length})
        destination = parts / f'{number:02}.mp4'
        subprocess.run([encoder, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start),
                        '-i', str(args.input_dir / 'rehearsal-raw.webm'), '-t', str(length),
                        '-vf', 'crop=iw:ih-8:0:0,scale=1280:-2,setsar=1', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                        '-r', '25', '-pix_fmt', 'yuv420p', str(destination)], check=True)
    listing = parts / 'concat.txt'
    listing.write_text('\n'.join(f"file '{n:02}.mp4'" for n in range(len(clips))), encoding='utf-8')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([encoder, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '1',
                    '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(args.output)], check=True)
    (args.input_dir / 'observed-edit.json').write_text(json.dumps(observed, indent=2), encoding='utf-8')
    print(f"Local captioned rehearsal: {sum(c['duration'] for c in observed):.1f}s -> {args.output}")


if __name__ == '__main__':
    main()
