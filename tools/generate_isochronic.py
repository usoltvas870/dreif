"""Generate an isochronic tone track (works without headphones)."""
import argparse
import numpy as np
import soundfile as sf


def generate_isochronic(
    carrier_hz: float,
    pulse_hz: float,
    duration_sec: int,
    sample_rate: int = 44100,
    amplitude: float = 0.4,
    duty_cycle: float = 0.5,
) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    carrier = np.sin(2 * np.pi * carrier_hz * t)
    # Square-wave envelope at pulse_hz
    pulse_period = sample_rate / pulse_hz
    envelope = ((t * pulse_hz) % 1.0 < duty_cycle).astype(float)
    # Smooth envelope edges to avoid clicks
    smooth = 20
    from scipy.ndimage import uniform_filter1d
    envelope = uniform_filter1d(envelope.astype(float), size=smooth)
    signal = amplitude * carrier * envelope
    # Fade in/out
    fade = int(5 * sample_rate)
    window = np.ones(len(t))
    window[:fade] = np.linspace(0, 1, fade)
    window[-fade:] = np.linspace(1, 0, fade)
    mono = signal * window
    return np.column_stack([mono, mono])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate isochronic tone .wav")
    parser.add_argument("--carrier", type=float, default=200.0)
    parser.add_argument("--pulse", type=float, required=True, help="Pulse frequency Hz")
    parser.add_argument("--duration", type=int, default=1800)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    audio = generate_isochronic(args.carrier, args.pulse, args.duration)
    sf.write(args.out, audio, 44100)
    print(f"Written {args.out} ({args.duration}s, {args.pulse}Hz pulse)")


if __name__ == "__main__":
    main()
