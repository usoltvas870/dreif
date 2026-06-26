"""Generate a binaural beat track: ambient base + binaural DSP layer."""
import argparse
import numpy as np
import soundfile as sf


def generate_binaural(
    carrier_hz: float,
    beat_hz: float,
    duration_sec: int,
    sample_rate: int = 44100,
    amplitude: float = 0.3,
) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    left = amplitude * np.sin(2 * np.pi * carrier_hz * t)
    right = amplitude * np.sin(2 * np.pi * (carrier_hz + beat_hz) * t)
    # Fade in/out 5 seconds
    fade = int(5 * sample_rate)
    window = np.ones(len(t))
    window[:fade] = np.linspace(0, 1, fade)
    window[-fade:] = np.linspace(1, 0, fade)
    return np.column_stack([left * window, right * window])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate binaural beat .wav")
    parser.add_argument("--carrier", type=float, default=200.0, help="Carrier frequency Hz")
    parser.add_argument("--beat", type=float, required=True, help="Beat frequency Hz")
    parser.add_argument("--duration", type=int, default=1800, help="Duration in seconds")
    parser.add_argument("--out", required=True, help="Output .wav path")
    args = parser.parse_args()

    audio = generate_binaural(args.carrier, args.beat, args.duration)
    sf.write(args.out, audio, 44100)
    print(f"Written {args.out} ({args.duration}s, {args.beat}Hz beat)")


if __name__ == "__main__":
    main()
