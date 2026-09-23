import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from core.live_session import LiveSessionManager
from core.telegram_bot import VoiceCaddyTelegramBot, BotState
from core.auth import UserRecord
from core.user_profile import UserProfile
from core.course import CONERO_GOLF_CLUB
from core.caddy_personality import CaddyPersonalityEngine, CaddyTone


class TestTelegramFsmFlow(unittest.TestCase):
    def setUp(self):
        # Database temporaneo isolato per rispetto rigoroso della SafeVault Policy
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_voice_caddy.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_path)

        # Mock bot e storage
        self.bot = VoiceCaddyTelegramBot(bot_token="123456:TEST_TOKEN", db=MagicMock(), auth_mgr=MagicMock())
        self.bot.session_mgr = self.session_mgr
        self.bot.config_mgr = MagicMock()
        self.bot._api_request = MagicMock(return_value={"ok": True, "result": {"message_id": 999}})

        # Mock contesto utente
        self.test_user = UserRecord(
            user_id="test_stefano",
            username="stefano_p",
            first_name="Stefano",
            last_name="Pirani",
            group="strafatti",
            password_hash="dummy_hash",
            salt="dummy_salt"
        )
        self.test_profile = UserProfile(
            player_name="Stefano Pirani",
            handicap=14.0
        )
        self.save_patcher = unittest.mock.patch.object(UserProfile, "save_for_user", return_value=True)
        self.save_patcher.start()
        self.weather_patcher = unittest.mock.patch("core.telegram_bot.weather_service.get_current_weather", return_value={
            "weather_desc": "Sereno ☀️",
            "temperature": 21.0,
            "wind_speed": 10.0,
            "wind_cardinal": "NE",
            "wind_arrow": "↙️",
            "wind_gusts": 15.0
        })
        self.weather_patcher.start()
        self.bot._resolve_context = MagicMock(return_value=(self.test_user, self.test_profile, CONERO_GOLF_CLUB, MagicMock()))
        self.chat_id = 99887766

    def tearDown(self):
        self.weather_patcher.stop()
        self.save_patcher.stop()
        self.temp_dir.cleanup()

    def _last_sent_text_and_markup(self):
        self.bot._api_request.assert_called()
        last_call = self.bot._api_request.call_args[0]
        payload = last_call[1]
        return payload.get("text", ""), payload.get("reply_markup", {})

    def test_idle_guards_and_setup_flow(self):
        """Verifica i guardrail iniziali in IDLE e la procedura di impostazione giro."""
        # 1. In IDLE, Score e Stato Buca non devono far avanzare né mostrare dati vuoti
        self.bot.process_text_message(self.chat_id, "Score")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Ti piacerebbe che fosse già finita", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "IDLE")

        self.bot.process_text_message(self.chat_id, "Stato Buca")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Ti piacerebbe che fosse già finita", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "IDLE")

        # 2. Nuovo Giro in IDLE deve essere bloccato
        self.bot.process_text_message(self.chat_id, "Nuovo Giro")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Opzione disponibile solo a giro concluso", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "IDLE")

        # 3. Calcolo distanze identifica il circolo
        self.bot.process_text_message(self.chat_id, "Calcolo distanze & plays Like")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Conero Golf Club", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "CIRCOLO_IDENTIFICATO")

        # 4. Scelta Tono Caddie
        self.bot.process_text_message(self.chat_id, "Tono Caddie")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Scegli il tono del tuo caddie", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "SCELTA_TONO")

        self.bot.process_text_message(self.chat_id, "Spiritoso")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Tono caddie aggiornato: Spiritoso", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "CIRCOLO_IDENTIFICATO")

        # 5. Avvio scelta modalità -> Formula da scegliere
        self.bot.process_text_message(self.chat_id, "Modalità Training")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Scegli la formula di gioco", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "FORMULA_DA_SCEGLIERE")

        # In FORMULA_DA_SCEGLIERE, la tastiera deve proporre Stableford / Scratch
        kb_texts = [btn["text"] for row in kb.get("keyboard", []) for btn in row]
        self.assertIn("Stableford", kb_texts)
        self.assertIn("Scratch", kb_texts)

        # 6. Selezione Formula -> Selezione Tee
        self.bot.process_text_message(self.chat_id, "Stableford")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Scegli il tee di partenza", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "TEE_DA_SCEGLIERE")

        # 7. Selezione Tee Gialli -> Pronto alla buca 1 (COLPO_DA_TEE)
        self.bot.process_text_message(self.chat_id, "Gialli")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Buca 1", txt)
        self.assertIn("Par", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "COLPO_DA_TEE")

    def test_hole_play_penalties_and_closure(self):
        """Testa l'esecuzione di una buca con penalità dal tee, gioco sul fairway, bunker e green."""
        # Portiamo lo stato a COLPO_DA_TEE buca 1
        self.session_mgr.set_fsm_state(
            self.chat_id,
            "COLPO_DA_TEE",
            current_hole=1,
            current_shot_number=1,
            game_mode="TRAINING",
            game_format="stableford"
        )

        # Colpo 1: Tira Driver dal tee -> ATTESA_ESITO_COLPO
        self.bot.process_text_message(self.chat_id, "Driver")
        txt, kb = self._last_sent_text_and_markup()
        self.assertTrue(len(txt) > 0)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_ESITO_COLPO")

        # Proviamo palla persa dal tee -> "Terzo colpo dal tee"
        self.bot.process_text_message(self.chat_id, "Terzo colpo dal tee")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("terzo colpo dal tee", txt.lower())
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "COLPO_DA_TEE")

        # Ritira Driver per il colpo 3
        self.bot.process_text_message(self.chat_id, "Driver")
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_ESITO_COLPO")

        # Raggiunge la palla: "Calcolo distanze & plays Like"
        self.bot.process_text_message(self.chat_id, "Calcolo distanze & plays Like")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Dove si trova la palla?", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "POSIZIONE_PALLA_DA_SCEGLIERE")

        # Palla in Fairway -> scelta bastone
        self.bot.process_text_message(self.chat_id, "Fairway")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Indica il bastone", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "BASTONE_DA_SCEGLIERE")

        # Tira Ferro Medio -> passa ad ATTESA_ESITO_COLPO
        self.bot.process_text_message(self.chat_id, "Ferro Medio")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_ESITO_COLPO")

        # Raggiunge la palla: Calcolo distanze -> POSIZIONE_PALLA_DA_SCEGLIERE
        self.bot.process_text_message(self.chat_id, "Calcolo distanze & plays Like")
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "POSIZIONE_PALLA_DA_SCEGLIERE")

        # Palla finisce in Bunker -> Bastone da scegliere include Sand Wedge
        self.bot.process_text_message(self.chat_id, "Bunker")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "BASTONE_DA_SCEGLIERE")
        kb_texts = [btn["text"] for row in kb.get("keyboard", []) for btn in row]
        self.assertIn("Sand Wedge", kb_texts)

        # Tira Sand Wedge dal bunker -> ATTESA_ESITO_COLPO
        self.bot.process_text_message(self.chat_id, "Sand Wedge")
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_ESITO_COLPO")

        # Raggiunge la palla: Calcolo distanze -> Green -> PUTT_DA_SCEGLIERE
        self.bot.process_text_message(self.chat_id, "Calcolo distanze & plays Like")
        self.bot.process_text_message(self.chat_id, "Green")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Green raggiunto", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "PUTT_DA_SCEGLIERE")

        # Esegue 2 putt per imbucare -> BUCA_CHIUSA
        self.bot.process_text_message(self.chat_id, "2 putt")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Buca 1 chiusa", txt)
        self.assertIn("Colpi lordi:", txt)
        self.assertIn("Risultato lordo:", txt)
        self.assertIn("Risultato netto:", txt)
        self.assertIn("Punti Stableford:", txt)
        self.assertIn("Commento caddie:", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "BUCA_CHIUSA")

        # Verifica che "Score" ora mostri il punteggio della buca 1
        self.bot.process_text_message(self.chat_id, "Score")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Score provvisorio", txt)
        self.assertIn("Buca 1:", txt)

    def test_full_round_18_holes_and_coach_comment(self):
        """Verifica la chiusura di tutte le 18 buche, il report finale con uno dei 50 commenti coach e la correzione score."""
        self.session_mgr.set_fsm_state(
            self.chat_id,
            "COLPO_DA_TEE",
            current_hole=1,
            game_mode="TRAINING",
            game_format="stableford"
        )
        self.test_profile.caddy_tone = CaddyTone.SPIRITOSO

        # Simuliamo il completamento veloce di tutte le 18 buche
        for h in range(1, 19):
            self.session_mgr.set_fsm_state(self.chat_id, "PUTT_DA_SCEGLIERE", current_hole=h)
            self.bot.process_text_message(self.chat_id, "2 putt")
            if h < 18:
                self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "BUCA_CHIUSA")
                # Avanza alla prossima buca
                self.bot.process_text_message(self.chat_id, "Prossima buca")
                self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "COLPO_DA_TEE")

        # Alla 18esima buca, il giro deve chiudersi automaticamente passando in ATTESA_CONFERMA_SCORE
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_CONFERMA_SCORE")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Giro completato", txt)
        self.assertIn("Formula:", txt)
        self.assertIn("Totale lordo:", txt)
        self.assertIn("Totale netto:", txt)
        self.assertIn("Punti Stableford:", txt)
        self.assertIn("Commento caddie", txt)

        # Tastiera deve proporre SOLO Confermi / Correggi
        kb_texts = [btn["text"] for row in kb.get("keyboard", []) for btn in row]
        self.assertIn("Confermi", kb_texts)
        self.assertIn("Correggi", kb_texts)
        self.assertNotIn("Nuovo Giro", kb_texts)

        # Test flusso "Correggi": Buca 7, 6 colpi
        self.bot.process_text_message(self.chat_id, "Correggi")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Scrivi il numero della buca da correggere", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "CORREZIONE_SCORE")

        self.bot.process_text_message(self.chat_id, "Buca 7, 6 colpi")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Score aggiornato con successo", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_CONFERMA_SCORE")

        # Test flusso "Confermi"
        self.bot.process_text_message(self.chat_id, "Confermi")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Score confermato. Giro chiuso correttamente", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "FINE_DEFINITIVA")

        # In FINE_DEFINITIVA, l'unico pulsante disponibile è Nuovo Giro
        _, kb_fin = self._last_sent_text_and_markup()
        kb_texts_fin = [btn["text"] for row in kb_fin.get("keyboard", []) for btn in row]
        self.assertEqual(kb_texts_fin, ["Nuovo Giro"])

        # Clicca Nuovo Giro -> richiesta conferma
        self.bot.process_text_message(self.chat_id, "Nuovo Giro")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Vuoi iniziare un nuovo giro?", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "CONFERMA_NUOVO_GIRO")

        # Clicca "Sì, nuovo giro" -> reset completo a IDLE
        self.bot.process_text_message(self.chat_id, "Sì, nuovo giro")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("Nuovo giro pronto", txt)
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "IDLE")

    def test_gara_mode_strictly_no_club_suggestions_rule_4_3(self):
        """Verifica che in Modalità Gara NON vengano MAI suggeriti i bastoni per evitare squalifica (Regola 4.3 & 10.2)."""
        # Avvia giro in Modalità Gara
        self.bot.process_text_message(self.chat_id, "Modalità Gara")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "FORMULA_DA_SCEGLIERE")
        self.assertIn("Gara", txt)

        self.bot.process_text_message(self.chat_id, "Stableford")
        self.bot.process_text_message(self.chat_id, "Gialli")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "COLPO_DA_TEE")
        # In Gara deve chiedere che bastone hai usato, senza consigliare
        self.assertIn("Indica il bastone", txt)
        self.assertNotIn("consigliato", txt.lower())

        # Prova richiesta esplicita consiglio bastone: deve scattare l'avviso anti-squalifica
        self.bot.process_text_message(self.chat_id, "Cosa tiro dal tee?")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("MODALITÀ GARA", txt)
        self.assertIn("Regola 4.3", txt)
        self.assertIn("SQUALIFICA", txt)
        self.assertNotIn("Driver consigliato", txt)

        # Registra Driver come fatto autonomamente dal giocatore
        self.bot.process_text_message(self.chat_id, "Driver")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "ATTESA_ESITO_COLPO")
        self.assertIn("Bastone registrato: Driver", txt)
        self.assertNotIn("consiglio", txt.lower())

        # In ATTESA_ESITO_COLPO, la tastiera deve mostrare "Calcolo distanze" senza "Plays Like"
        kb_texts = [btn["text"] for row in kb.get("keyboard", []) for btn in row]
        self.assertIn("Calcolo distanze", kb_texts)
        self.assertNotIn("Calcolo distanze & plays Like", kb_texts)

        # Calcola distanza alla bandiera
        self.bot.process_text_message(self.chat_id, "Calcolo distanze")
        txt, kb = self._last_sent_text_and_markup()
        self.assertEqual(self.session_mgr.get_fsm_state(self.chat_id), "POSIZIONE_PALLA_DA_SCEGLIERE")
        self.assertIn("Distanza alla bandiera", txt)
        self.assertIn("Regola 4.3", txt)
        self.assertNotIn("Plays like", txt)
        self.assertNotIn("Consigliato", txt)

        # Prova altra richiesta di consiglio sul fairway
        self.bot.process_text_message(self.chat_id, "Fairway")
        self.bot.process_text_message(self.chat_id, "Che ferro tiro adesso?")
        txt, kb = self._last_sent_text_and_markup()
        self.assertIn("MODALITÀ GARA", txt)
        self.assertIn("SQUALIFICA", txt)


if __name__ == "__main__":
    unittest.main()
