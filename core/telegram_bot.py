from __future__ import annotations

import os
import sys
import time
import tempfile
import urllib.request
import json
import logging
from pathlib import Path
from typing import Optional

from core.audio import VoiceCaddyAudioEngine
from core.parser import parse_golf_audio_transcript
from core.metrics import GolfMetricsCalculator
from core.db import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class VoiceCaddyTelegramBot:
    """
    Lightweight Telegram Bot Engine for Voice Caddy.
    Allows golfers to record voice notes on Telegram, send them directly to the bot,
    and receive an instant analyzed scorecard and performance breakdown back on their phone.
    """

    def __init__(self, bot_token: str, openai_api_key: Optional[str] = None):
        self.bot_token = bot_token
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.audio_engine = VoiceCaddyAudioEngine(model_size="medium")
        self.db = DatabaseManager()
        self.is_running = False

    def _api_request(self, method: str, data: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/{method}"
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json')
        payload = json.dumps(data).encode('utf-8') if data else None
        
        try:
            with urllib.request.urlopen(req, data=payload, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logging.error(f"Errore chiamata Telegram API ({method}): {e}")
            return {"ok": False, "error": str(e)}

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML"):
        self._api_request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        })

    def get_file_path(self, file_id: str) -> Optional[str]:
        res = self._api_request("getFile", {"file_id": file_id})
        if res.get("ok"):
            return res["result"]["file_path"]
        return None

    def download_file(self, file_path: str, dest_path: str):
        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        urllib.request.urlretrieve(url, dest_path)

    def process_voice_message(self, chat_id: int, file_id: str):
        self.send_message(chat_id, "🎙️ <i>Nota vocale ricevuta! Conversione audio ed estrazione in corso con Whisper...</i>")
        
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
        temp_audio_path = temp_audio.name
        temp_audio.close()

        try:
            telegram_file_path = self.get_file_path(file_id)
            if not telegram_file_path:
                self.send_message(chat_id, "❌ Impossibile scaricare il file audio da Telegram.")
                return

            self.download_file(telegram_file_path, temp_audio_path)

            # Transcribe with Whisper
            self.send_message(chat_id, "🧠 <i>Trascrizione completata. Ricostruzione colpi in corso (GPT-4o)...</i>")
            transcript, meta = self.audio_engine.transcribe(temp_audio_path)

            # Parse with GPT-4o
            raw_data = parse_golf_audio_transcript(transcript, api_key=self.openai_api_key)

            # Reconcile metrics deterministically
            validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_data)

            # Save to SQLite
            round_id = self.db.save_round(validated_data)

            # Format Response Message for Telegram
            summary = validated_data.performance_summary
            info = validated_data.round_info
            rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(validated_data.holes)
            rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")

            reply_msg = (
                f"<b>⛳ VOICE CADDY — SCORECARD UFFICIALE</b>\n"
                f"<b>Campo:</b> {info.course_name or 'Circolo Golf'}\n"
                f"<b>Buche giocate:</b> {info.holes_played}\n\n"
                f"📊 <b>RISULTATI CHIAVE:</b>\n"
                f"• <b>Score Finale:</b> {summary.total_score} ({rel_par_str})\n"
                f"• <b>Fairway Presi (FIR):</b> {summary.fairway_accuracy_pct}%\n"
                f"• <b>Green in Reg. (GIR):</b> {summary.gir_pct}%\n"
                f"• <b>Scrambling:</b> {summary.scrambling_pct}%\n"
                f"• <b>Totale Putt:</b> {summary.total_putts} (Media {round(summary.total_putts / info.holes_played, 2)}/buca)\n\n"
                f"🎯 <b>TENDENZA ERRORE PRINCIPALE:</b>\n"
                f"<i>{summary.primary_miss_tendency}</i>\n\n"
                f"🏋️ <b>ESERCIZIO CONSIGLIATO:</b>\n"
            )

            if summary.training_drills_recommended:
                drill = summary.training_drills_recommended[0]
                reply_msg += f"<b>[{drill.target_area}] {drill.drill_name}:</b> {drill.drill_instructions}\n\n"

            reply_msg += f"✅ <i>Partita registrata nel database locale (ID #{round_id}). Apri la Dashboard Streamlit su PC per la versione completa!</i>"

            self.send_message(chat_id, reply_msg)

        except Exception as e:
            logging.error(f"Errore durante l'elaborazione del messaggio vocale: {e}")
            self.send_message(chat_id, f"❌ Errore durante l'elaborazione del file audio: {str(e)}")
        finally:
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass

    def run_polling(self):
        """
        Runs continuous HTTP long polling to receive updates from Telegram.
        """
        self.is_running = True
        offset = 0
        logging.info("Bot Telegram Voice Caddy avviato in modalità Polling...")

        while self.is_running:
            res = self._api_request("getUpdates", {"offset": offset, "timeout": 10})
            if res.get("ok"):
                for update in res.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    text = message.get("text", "")

                    if text.startswith("/start") or text.startswith("/help"):
                        self.send_message(
                            chat_id,
                            "⛳ <b>Benvenuto in Voice Caddy Bot!</b>\n\n"
                            "Inviamele pure qui le tue note vocali registrate sul campo da golf (anche buca per buca o in un unico audio).\n"
                            "Convertirò la tua voce in una scorecard ufficiale color-coded e analizzerò i tuoi colpi persi!"
                        )
                    elif "voice" in message:
                        file_id = message["voice"]["file_id"]
                        self.process_voice_message(chat_id, file_id)
                    elif "audio" in message:
                        file_id = message["audio"]["file_id"]
                        self.process_voice_message(chat_id, file_id)

            time.sleep(1)

    def stop(self):
        self.is_running = False


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Fornire TELEGRAM_BOT_TOKEN come argomento o variabile d'ambiente.")
        sys.exit(1)

    bot = VoiceCaddyTelegramBot(bot_token=token)
    bot.run_polling()
