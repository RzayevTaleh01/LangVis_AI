import platform
import subprocess
import sys

OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def main() -> None:
    print(f"⚙  LangVis language tutor — setup (OS: {OS or 'unknown'})")

    # requirements.txt filters OS-specific extras by itself via pip markers.
    print("\n▶ Installing Python dependencies…")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                   check=True)

    print("\n✅ Setup complete!")
    print("   1) Launch it:  python main.py")
    print("   2) Paste your free Gemini API key when the setup screen appears.")
    print("   3) Check ⚙ → TUTOR SETTINGS: your level, your own language, the pace.")
    print("   4) Then just talk. The lesson starts by itself.")


if __name__ == "__main__":
    main()
