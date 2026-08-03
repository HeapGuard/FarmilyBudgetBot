import os
import tempfile
import asyncio
import subprocess
from typing import Optional, Tuple
from app.config import settings

# Lazy loading of faster-whisper model
_whisper_model_instance = None


def get_whisper_model():
    global _whisper_model_instance
    if _whisper_model_instance is None:
        from faster_whisper import WhisperModel
        download_root = "./data/whisper_models"
        os.makedirs(download_root, exist_ok=True)
        _whisper_model_instance = WhisperModel(
            settings.WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            download_root=download_root
        )
    return _whisper_model_instance


async def convert_ogg_to_wav(ogg_path: str, wav_path: str) -> bool:
    """
    Converts OGG Opus audio to mono WAV 16000Hz PCM using ffmpeg.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", ogg_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        wav_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    await proc.wait()
    return proc.returncode == 0


async def transcribe_voice(audio_bytes: bytes, duration_seconds: Optional[int] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Processes voice audio bytes, converts to WAV, runs faster-whisper, and cleans up audio files.
    Returns (transcription_text, error_message).
    """
    if settings.STT_ENGINE == "none":
        return None, "Не смог распознать голос. Напиши, пожалуйста, текстом."

    if duration_seconds and duration_seconds > settings.MAX_VOICE_DURATION_SECONDS:
        return None, f"Голосовое слишком длинное. Пока поддерживаю короткие фразы до {settings.MAX_VOICE_DURATION_SECONDS // 60} минут."

    temp_dir = tempfile.mkdtemp()
    ogg_file = os.path.join(temp_dir, "input.ogg")
    wav_file = os.path.join(temp_dir, "output.wav")

    try:
        # Write OGG bytes to disk
        with open(ogg_file, "wb") as f:
            f.write(audio_bytes)

        # Convert to WAV
        success = await convert_ogg_to_wav(ogg_file, wav_file)
        if not success or not os.path.exists(wav_file):
            return None, "Не смог распознать голос. Напиши, пожалуйста, текстом."

        # Transcribe in a threadpool to prevent blocking async loop
        def run_stt():
            model = get_whisper_model()
            segments, info = model.transcribe(
                wav_file,
                language=settings.STT_LANGUAGE,
                beam_size=5
            )
            text = " ".join([seg.text for seg in segments]).strip()
            return text

        transcription = await asyncio.to_thread(run_stt)
        if not transcription:
            return None, "Не смог распознать голос. Напиши, пожалуйста, текстом."

        return transcription, None

    except Exception:
        return None, "Не смог распознать голос. Напиши, пожалуйста, текстом."

    finally:
        # Strict cleanup of temporary files
        try:
            if os.path.exists(ogg_file):
                os.remove(ogg_file)
            if os.path.exists(wav_file):
                os.remove(wav_file)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception:
            pass
