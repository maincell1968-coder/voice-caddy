from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional
from openai import OpenAI


class AudioProcessingError(Exception):
    pass


class VoiceCaddyAudioEngine:
    """
    Audio Processing Engine for Voice Caddy.
    Supports both:
    1. OpenAI Whisper API (Cloud, ultra-fast, zero local dependencies)
    2. faster-whisper (Local, offline, with optional ffmpeg noise reduction)
    """

    GOLF_CONTEXT_PROMPT = (
        "Note vocali di un giro da golf. Parlato naturale ed espressivo. "
        "Buca 1, buca 2, buca 3, buca 4, buca 5, buca 6, buca 7, buca 8, buca 9, "
        "buca 10, buca 11, buca 12, buca 13, buca 14, buca 15, buca 16, buca 17, buca 18. "
        "Par 3, par 4, par 5, score, colpi, drive, tee shot, partenza dal tee, "
        "fairway, rough, rough di destra, rough di sinistra, bunker di fairway, bunker di green, "
        "green in regulation, GIR, approccio, pitch, chip, flop shot, lob wedge, "
        "sand wedge, gap wedge, pitching wedge, ferro 3, ferro 4, ferro 5, ferro 6, ferro 7, ferro 8, ferro 9, "
        "ibrido, legno 3, legno 5, driver, putter, putt, 3-putt, birdie, eagle, par, bogey, doppio bogey, "
        "slice, hook, fade, draw, pull, push, fat, preso pesante, thin, liscio, top, socket, "
        "out of bounds, fuori limite, ostacolo d'acqua, penalità, due putt, un putt."
    )

    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "default"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as err:
                raise AudioProcessingError(
                    "Il modulo 'faster-whisper' non è installato nel sistema. "
                    "Puoi selezionare 'OpenAI Whisper Cloud' nella barra laterale oppure installare 'faster-whisper'."
                ) from err
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    @staticmethod
    def normalize_to_wav(input_path: str | Path, enable_noise_reduction: bool = True) -> str:
        """
        Converts audio to a standard 16kHz Mono PCM WAV file using ffmpeg if available.
        If ffmpeg is missing and the file is already a valid format, returns original path.
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"File audio non trovato: {input_path}")

        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = temp_wav.name
        temp_wav.close()

        filters = []
        if enable_noise_reduction:
            filters.append("afftdn=nr=12:nf=-25")
        filters.append("loudnorm")
        filter_str = ",".join(filters)

        cmd = [
            "ffmpeg", "-y", "-i", str(input_path), "-vn",
            "-af", filter_str,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            "-loglevel", "error", output_path
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            if os.path.exists(output_path):
                os.remove(output_path)
            # Fallback: if input is already wav/mp3/m4a, return original path directly
            return str(input_path)

    def transcribe_local(self, audio_path: str | Path, language: str = "it") -> Tuple[str, dict]:
        """
        Transcribes audio using local faster-whisper.
        """
        normalized_wav = None
        try:
            normalized_wav = self.normalize_to_wav(audio_path)
            segments, info = self.model.transcribe(
                normalized_wav,
                language=language,
                initial_prompt=self.GOLF_CONTEXT_PROMPT,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            transcript_parts = [segment.text.strip() for segment in segments]
            full_transcript = " ".join(transcript_parts)

            metadata = {
                "detected_language": info.language,
                "language_probability": info.language_probability,
                "duration_seconds": info.duration,
                "engine": "faster-whisper (local)"
            }
            return full_transcript, metadata
        finally:
            if normalized_wav and normalized_wav != str(audio_path) and os.path.exists(normalized_wav):
                try:
                    os.remove(normalized_wav)
                except OSError:
                    pass

    @classmethod
    def transcribe_cloud_groq(cls, audio_path: str | Path, api_key: Optional[str] = None, language: str = "it") -> Tuple[str, dict]:
        """
        Transcribes audio using Groq Whisper Cloud (whisper-large-v3-turbo).
        Ultra-fast, accurate, and completely free with Groq API key.
        """
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            try:
                import streamlit as st
                if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                    key = st.secrets["GROQ_API_KEY"]
            except Exception:
                pass
        if not key:
            try:
                from core.ai_provider import get_default_groq_key
                key = get_default_groq_key()
            except Exception:
                pass
        if not key:
            raise ValueError("Groq API Key non configurata per la trascrizione cloud.")

        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key)
        audio_file_path = Path(audio_path)

        with open(audio_file_path, "rb") as audio_file:
            transcript_resp = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                prompt=cls.GOLF_CONTEXT_PROMPT,
                language=language
            )

        full_transcript = transcript_resp.text.strip()
        metadata = {
            "detected_language": language,
            "engine": "Groq Whisper-large-v3-turbo (cloud ultra-rapido)"
        }
        return full_transcript, metadata

    @classmethod
    def transcribe_cloud_openai(cls, audio_path: str | Path, api_key: Optional[str] = None, language: str = "it") -> Tuple[str, dict]:
        """
        Transcribes audio using OpenAI Whisper API (whisper-1). Fast, reliable, no local model needed.
        """
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OpenAI API Key non configurata per la trascrizione cloud.")

        client = OpenAI(api_key=key)
        audio_file_path = Path(audio_path)

        with open(audio_file_path, "rb") as audio_file:
            transcript_resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                prompt=cls.GOLF_CONTEXT_PROMPT,
                language=language
            )

        full_transcript = transcript_resp.text.strip()
        metadata = {
            "detected_language": language,
            "engine": "OpenAI Whisper-1 (cloud)"
        }
        return full_transcript, metadata

    def transcribe(
        self,
        audio_path: str | Path,
        engine_mode: str = "cloud",
        api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        language: str = "it"
    ) -> Tuple[str, dict]:
        """
        Unified transcription method dispatching to Groq, OpenAI Cloud, or Local engine.
        Automatically falls back to Groq or OpenAI if local faster-whisper is not installed.
        """
        if engine_mode == "groq":
            return self.transcribe_cloud_groq(audio_path, api_key=groq_api_key, language=language)
        elif engine_mode == "cloud":
            return self.transcribe_cloud_openai(audio_path, api_key=api_key, language=language)
        else:
            try:
                return self.transcribe_local(audio_path, language=language)
            except (AudioProcessingError, Exception) as err:
                # Graceful fallback: if local faster-whisper is unavailable, check Groq or OpenAI
                g_key = groq_api_key or os.environ.get("GROQ_API_KEY")
                if g_key:
                    return self.transcribe_cloud_groq(audio_path, api_key=g_key, language=language)
                o_key = api_key or os.environ.get("OPENAI_API_KEY")
                if o_key:
                    return self.transcribe_cloud_openai(audio_path, api_key=o_key, language=language)
                raise AudioProcessingError(f"Trascrizione non riuscita: {err}") from err

    def transcribe_multiple(
        self,
        audio_paths: List[str | Path],
        engine_mode: str = "cloud",
        api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        language: str = "it"
    ) -> Tuple[str, List[dict]]:
        full_transcripts = []
        all_metadata = []

        for idx, path in enumerate(audio_paths, 1):
            text, meta = self.transcribe(
                path, engine_mode=engine_mode, api_key=api_key, groq_api_key=groq_api_key, language=language
            )
            full_transcripts.append(f"[Nota Audio {idx}]: {text}")
            all_metadata.append(meta)

        combined_text = "\n\n".join(full_transcripts)
        return combined_text, all_metadata

