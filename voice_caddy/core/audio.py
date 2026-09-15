from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional
from faster_whisper import WhisperModel


class AudioProcessingError(Exception):
    pass


class VoiceCaddyAudioEngine:
    """
    Audio Processing Engine powered by ffmpeg and faster-whisper.
    Handles audio normalization, noise reduction (outdoor wind filtering),
    and contextual speech-to-text transcription with golf-specific vocabulary injection.
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

    def __init__(self, model_size: str = "medium", device: str = "auto", compute_type: str = "default"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    @staticmethod
    def normalize_to_wav(input_path: str | Path, enable_noise_reduction: bool = True) -> str:
        """
        Converts audio from any smartphone format (.m4a, .mp3, .aac, .opus, .wav)
        to a standard 16kHz Mono PCM WAV file for Whisper.
        Applies ffmpeg audio filtering (afftdn for wind/outdoor noise reduction + loudnorm).
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"File audio non trovato: {input_path}")

        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = temp_wav.name
        temp_wav.close()

        # Build ffmpeg command with audio filters for outdoor clarity
        filters = []
        if enable_noise_reduction:
            filters.append("afftdn=nr=12:nf=-25")  # FFT noise reduction for wind/ambient
        filters.append("loudnorm")  # Normalize audio volume

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
        except subprocess.CalledProcessError as e:
            # Fallback without filter if complex filter fails
            fallback_cmd = [
                "ffmpeg", "-y", "-i", str(input_path), "-vn",
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                "-loglevel", "error", output_path
            ]
            try:
                subprocess.run(fallback_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return output_path
            except subprocess.CalledProcessError as fallback_err:
                if os.path.exists(output_path):
                    os.remove(output_path)
                raise AudioProcessingError(f"Errore conversione ffmpeg: {fallback_err.stderr.decode('utf-8')}") from fallback_err
        except FileNotFoundError:
            raise AudioProcessingError("ffmpeg non trovato nel PATH di sistema. Installa ffmpeg e riprova.")

    def transcribe(self, audio_path: str | Path, language: str = "it") -> Tuple[str, dict]:
        """
        Transcribes a single audio file using faster-whisper with VAD filter and context prompt.
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
                "duration_seconds": info.duration
            }
            return full_transcript, metadata
        finally:
            if normalized_wav and os.path.exists(normalized_wav):
                try:
                    os.remove(normalized_wav)
                except OSError:
                    pass

    def transcribe_multiple(self, audio_paths: List[str | Path], language: str = "it") -> Tuple[str, List[dict]]:
        """
        Transcribes multiple audio files (e.g. 1 file per hole recorded separately)
        and joins them chronologically.
        """
        full_transcripts = []
        all_metadata = []

        for idx, path in enumerate(audio_paths, 1):
            text, meta = self.transcribe(path, language=language)
            full_transcripts.append(f"[Nota Audio {idx}]: {text}")
            all_metadata.append(meta)

        combined_text = "\n\n".join(full_transcripts)
        return combined_text, all_metadata
