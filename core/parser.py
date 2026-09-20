from __future__ import annotations

import os
import re
from typing import Optional, Dict, Any
from core.schemas import GolfRoundData, ShotIntent
from core.user_profile import UserProfile
from core.course import GolfCourse, CONERO_GOLF_CLUB
from core.auth import AIUserConfig
from core.ai_provider import execute_round_analysis


def infer_shot_intent(
    text: str = "",
    club: Optional[str] = None,
    lie: Optional[str] = None,
    distance_to_green: Optional[float] = None,
    shot_index: Optional[int] = None,
    par: Optional[int] = None,
    prev_lie: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Riconosce e classifica deterministicamente l'intento tattico del colpo (Shot Intent):
    - Distingue tra colpo pieno (FULL_SHOT), layup tattico (LAYUP), salvataggio/uscita (RECOVERY_PUNCH / ESCAPE_TROUBLE),
      approccio a correre (BUMP_AND_RUN), flop/pitch alto (PITCH_FLOP), chip dal bordo (CHIP), o tee shot (TEE_SHOT).
    - Impedisce che un colpo di tocco o di piazzamento (es. F6 a 30m) sia catalogato erroneamente come un colpo fallito o corto di 100m.
    """
    cleaned = (text or "").lower()
    club_str = (club or "").lower()
    lie_str = (lie or "").lower()
    prev_lie_str = (prev_lie or "").lower()

    # 1. Analisi esplicita del testo / parole chiave
    recovery_keywords = [
        "recovery", "punch", "colpo basso", "uscita da", "uscita tra", "alberi", "piante", "rami",
        "boscaglia", "rimettersi in gioco", "rimesso in gioco", "rimettersi in pista", "tirare fuori",
        "fuori dai guai", "sotto i rami", "uscita laterale", "escape", "salvataggio", "in fairway solo per uscire"
    ]
    if any(kw in cleaned for kw in recovery_keywords):
        if "laterale" in cleaned or "solo per uscire" in cleaned or "escape" in cleaned:
            return {
                "intent": ShotIntent.ESCAPE_TROUBLE,
                "is_recovery": True,
                "is_layup": False,
                "intent_reason": "Uscita laterale di sicurezza da ostacolo/boscaglia"
            }
        return {
            "intent": ShotIntent.RECOVERY_PUNCH,
            "is_recovery": True,
            "is_layup": False,
            "intent_reason": "Colpo di recovery/salvataggio per rimettersi in gioco"
        }

    layup_keywords = [
        "layup", "lay up", "lay-up", "piazzamento", "piazzare", "piazzato", "colpo conservativo",
        "davanti all'acqua", "prima dell'acqua", "prima del lago", "prima del fosso", "tenuto corto",
        "appoggio", "piazzata"
    ]
    if any(kw in cleaned for kw in layup_keywords):
        return {
            "intent": ShotIntent.LAYUP,
            "is_recovery": False,
            "is_layup": True,
            "intent_reason": "Piazzamento tattico conservativo (Layup)"
        }

    bump_keywords = [
        "bump and run", "bump & run", "bumpandrun", "approccio a correre", "a correre",
        "rotolo", "fatto correre", "farla correre", "ferro basso a correre", "corsa"
    ]
    if any(kw in cleaned for kw in bump_keywords):
        return {
            "intent": ShotIntent.BUMP_AND_RUN,
            "is_recovery": False,
            "is_layup": False,
            "intent_reason": "Approccio basso a correre (Bump and Run)"
        }

    flop_keywords = [
        "flop", "flop shot", "pitch alto", "alzo la palla", "alta e morbida", "morbido sopra",
        "aperto la faccia", "faccia aperta", "pallonetto"
    ]
    if any(kw in cleaned for kw in flop_keywords):
        return {
            "intent": ShotIntent.PITCH_FLOP,
            "is_recovery": False,
            "is_layup": False,
            "intent_reason": "Approccio alto e morbido (Flop / Pitch)"
        }

    chip_keywords = [
        "chip", "chippetto", "bordo green", "dal bordo", "collar", "fringe", "avangreen"
    ]
    if any(kw in cleaned for kw in chip_keywords):
        return {
            "intent": ShotIntent.CHIP,
            "is_recovery": False,
            "is_layup": False,
            "intent_reason": "Chip attorno al green"
        }

    # 2. Euristica balistica e contestuale basata su bastone e distanza
    dist = distance_to_green

    # Controlla se è un colpo di partenza
    if shot_index == 1 or lie_str == "tee":
        return {
            "intent": ShotIntent.TEE_SHOT,
            "is_recovery": False,
            "is_layup": False,
            "intent_reason": "Tee shot dal tee di partenza"
        }

    # Rilevamento Bump & Run implicito:
    # Uso di un ferro medio (F4, F5, F6, F7, F8, F9 o Ibrido) da < 45m dal green
    is_mid_iron_or_hybrid = any(
        c in club_str for c in ["ferro 4", "ferro 5", "ferro 6", "ferro 7", "ferro 8", "ferro 9", "f4", "f5", "f6", "f7", "f8", "f9", "ibrido"]
    )
    if is_mid_iron_or_hybrid and dist is not None and dist <= 45.0 and lie_str in ("fairway", "rough", "green", "collar", "fringe", "unknown", ""):
        return {
            "intent": ShotIntent.BUMP_AND_RUN,
            "is_recovery": False,
            "is_layup": False,
            "intent_reason": f"Uso di ferro medio ({club}) da {dist}m per approccio a correre (Bump & Run)"
        }

    # Rilevamento Recovery implicito:
    is_long_or_mid_club = any(
        c in club_str for c in ["driver", "legno", "ibrido", "ferro 3", "ferro 4", "ferro 5", "ferro 6", "ferro 7"]
    )
    if is_long_or_mid_club and lie_str in ("rough", "hazard", "alberi") and dist is not None and 35.0 <= dist <= 85.0:
        return {
            "intent": ShotIntent.RECOVERY_PUNCH,
            "is_recovery": True,
            "is_layup": False,
            "intent_reason": f"Uscita/recovery controllata con {club} dal rough/ostacolo"
        }

    # Rilevamento Layup implicito su Par 5:
    if par == 5 and shot_index == 2 and is_long_or_mid_club:
        if dist is not None and dist >= 50.0:
            return {
                "intent": ShotIntent.LAYUP,
                "is_recovery": False,
                "is_layup": True,
                "intent_reason": "Secondo colpo di piazzamento strategico su Par 5 (Layup)"
            }

    # Rilevamento approcci con Wedge vicino al green
    is_wedge = any(w in club_str for w in ["wedge", "pitch", "sand", "lob", "approach", "gap", "pw", "sw", "lw", "gw", "aw"])
    if is_wedge and dist is not None:
        if dist <= 18.0:
            return {
                "intent": ShotIntent.CHIP,
                "is_recovery": False,
                "is_layup": False,
                "intent_reason": f"Chip con {club} a breve distanza ({dist}m)"
            }
        elif dist <= 50.0:
            return {
                "intent": ShotIntent.PITCH_FLOP,
                "is_recovery": False,
                "is_layup": False,
                "intent_reason": f"Pitch/approccio morbido con {club} ({dist}m)"
            }

    # Default: Colpo pieno standard
    return {
        "intent": ShotIntent.FULL_SHOT,
        "is_recovery": False,
        "is_layup": False,
        "intent_reason": "Colpo pieno standard"
    }


def parse_golf_audio_transcript(
    transcript_text: str,
    user_profile: Optional[UserProfile] = None,
    course: Optional[GolfCourse] = None,
    ai_config: Optional[AIUserConfig] = None,
    api_key: Optional[str] = None,
    model_name: str = "gpt-4o"
) -> GolfRoundData:
    """
    Parses unstructured golf audio transcripts into a structured Pydantic GolfRoundData object,
    evaluating the Target Landing Area (Ideal vs Actual landing zone) based on player's HCP and course parameters.
    Uses the user's private AI configuration (Ollama, personal OpenAI, or Custom endpoint).
    """
    profile = user_profile or UserProfile()
    active_course = course or CONERO_GOLF_CLUB

    tone_instructions = profile.get_tone_system_instruction()
    bag_distances_context = profile.format_club_distances_prompt_context()

    course_context = f"CAMPO DI GIOCO: {active_course.name} ({active_course.city}) — Par Totale: {active_course.total_par}\n"
    if hasattr(active_course, "terrain_description"):
        course_context += f"OROGRAFIA DEL PERCORSO: {active_course.terrain_description}\n"
    course_context += "Dettaglio Buche del Campo e Profilo Altimetrico:\n"
    for h in active_course.holes:
        dist_str = f"{h.distance_meters} metri" if h.distance_meters else "N/D"
        hcp_str = f"HCP Index {h.handicap_index}" if h.handicap_index else "HCP Index N/D"
        slope_str = getattr(h, "slope_elevation_profile", "In pianura")
        course_context += f"- Buca {h.hole_number}: Par {h.par}, {dist_str} ({hcp_str}) — Pendenza/Dislivello: {slope_str}\n"

    system_prompt = f"""Sei Voice Caddy, un analista PGA Tour e caddie professionista personalizzato.

### 🎭 REGOLAZIONE DEL TONO DIALETTICO E DELLA SEVERITÀ DELL'IA:
{tone_instructions}

### 🏌️‍♂️ PROFILO GIOCATORE E DISTANZE IN SACCA:
- Giocatore: {profile.player_name} (Handicap: {profile.handicap} — {profile.category.value})
{bag_distances_context}

### ⛳ CONTESTO DEL CAMPO DA GIOCO E PROFILO DELLE PENDENZE:
{course_context}

### ⛰️ PREMESSE FONDAMENTALI SU PENDENZE E ALTIMETRIA (PLAYS-LIKE DISTANCE):
Le pendenze indicate per ciascuna buca sono la PREMESSA FONDAMENTALE di ogni analisi tattica e della scelta dei bastoni:
1. **Buche in Salita (es. Conero Buca 1 finale, Buca 7 finale, Buca 9, Buca 10 finale, Buca 11, Buca 16 par 3, Buca 18):**
   - La palla ha minor rotolo e la distanza reale giocata (plays-like) è maggiore rispetto alla metratura nominale.
   - Il colpo in salita richiede solitamente da 1 a 2 ferri in più (es. un secondo colpo di 130m in forte salita gioca come 140-145m).
   - Valuta con intelligenza le scelte di bastone e menziona l'effetto della salita.
2. **Buche in Discesa (es. Conero Buca 2 par 3, Buca 3 iniziale, Buca 8 iniziale, Buca 10 iniziale, Buca 12, Buca 17):**
   - La palla vola più a lungo e rotola molto di più. La distanza plays-like è inferiore a quella del telemetro.
   - Premia le scelte di bastone prudenti volte a evitare di finire fuori green sul fondo.
3. **Campi e Tratti in Pianura (es. Torrenova interamente pianeggiante, o buche piatte del Conero):**
   - Nessuna correzione altimetrica da applicare; le distanze nominali corrispondono alla balistica pura.
4. **Note Tattiche del Caddie (`caddie_tactical_note`):**
   - Fai sempre riferimento alla pendenza della buca quando ha influenzato il colpo (es. "Ottima scelta di bastone considerando la salita finale al green", "Colpo lungo facilitato dal dislivello in discesa", ecc.).

### 🎯 ANALISI DELL'AREA DI TARGET E GESTIONE PERCORSO (TARGET LANDING ANALYSIS):
Per OGNI buca analizzata, compila obbligatoriamente l'oggetto `target_landing_analysis`:
1. **`ideal_target_zone`**: Calcola la zona strategica PERFETTA dove il giocatore con HCP {profile.handicap} avrebbe dovuto atterrare dal tee o nel colpo di approccio per giocare in sicurezza quella buca su questo specifico campo considerando anche le pendenze.
2. **`actual_landing_zone`**: Descrivi dove è effettivamente atterrata la palla nel colpo reale.
3. **`tactical_verdict`**: Valutazione strategica:
   - Se la palla è finita nella zona ideale o vicina: Rilascia un elogio esplicito ("Bravo! Posizionamento Tattico Perfetto", "Ottimo Piazzamento", "Scelta Strategica Vincente").
   - Se è finita fuori bersaglio: Assegna il verdetto corretto ("Deviazione Tattica a Destra", "Errore di Selezione Target", "Scelta Troppo Aggressiva").
4. **`caddie_tactical_note`**: Spiegazione di come la posizione atterrata e l'orografia del terreno hanno condizionato il colpo.

### 🏆 REGOLE DI CALCOLO PUNTEGGIO E RIEPILOGO DI GARA (LORDO E NETTO):
Agisci come motore di calcolo e generazione report per gare di golf secondo le Regole R&A/USGA e World Handicap System (WHS):
1. **Formule di gara**: Distingui sempre tra gara "Stableford" (default 95% WHS) e gara a colpi / "Stroke Play" / "Medal" (100%).
2. **Punteggio Lordo vs Netto**:
   - In TUTTI i riepiloghi e nella diagnosi executive (`executive_narrative`) cita SEMPRE sia il risultato LORDO che il risultato NETTO.
   - Nelle gare Stableford indica sempre sia i punti Stableford netti che i punti Stableford lordi, oltre ai colpi netti e lordi.
   - Nelle gare a colpi indica sempre sia i colpi lordi che i colpi netti.
3. **Calcoli ufficiali (Regole 21.1 e 3 R&A/USGA)**:
   - Colpi Netti Buca = Colpi Lordi Buca - Colpi HCP ricevuti (distribuiti secondo lo Stroke Index della buca).
   - Punti Stableford Netti = max(0, 2 + Par - Colpi Netti).
   - Punti Stableford Lordi = max(0, 2 + Par - Colpi Lordi).
   - Colpi Netti Totale = Colpi Lordi Totale - Playing Handicap.
4. **Coerenza dei dati**: Compila con la massima precisione i dettagli buca per buca e il riepilogo complessivo del giro.

### ⛳ REGOLE FONDAMENTALI DI CONTEGGIO COLPI E CHIUSURA BUCA (CONDIZIONE PUTT):
1. **CHIUSURA DETERMINISTICA DELLA BUCA CON I PUTT:**
   - La menzione del numero di putt (es. "1 putt", "un putt", "2 putt", "due putt", "3 putt", "tre putt") è la CONDIZIONE FONDAMENTALE che CHIUDE la buca corrente!
   - Non appena vengono menzionati i putt sul green, la buca è UFFICIALMENTE COMPLETATA.
   - Qualsiasi colpo, bastone o nota successiva appartiene alla buca successiva (anche se il giocatore non ripete esplicitamente il numero di buca, o se dice "Buca X", "Tee X" o il bastone dal tee).
2. **CONTEGGIO AUTOMATICO DEI COLPI (SCORE DELLA BUCA):**
   - Lo score lordo di una buca è SEMPRE pari alla somma di:
     (Tutti i colpi eseguiti prima del green: tee shot + colpi intermedi + approcci/pitch/chip + recovery + penalità)
     PIÙ
     (Il numero di putt comunicati).
   - Esempio: "Buca 1: Partenza Ibrido 3, poi ferro 8, poi approach, e 2 putt" ➔ 1 (Ibrido 3) + 1 (Ferro 8) + 1 (Approach) + 2 (Putt) = 5 COLPI (Score: 5)!
   - Ogni colpo, bastone o approccio citato senza specificare un numero vale esattamente 1 colpo.
   - Se il giocatore dichiara "Acqua", "Fuori Limite" o "Penalità", aggiungi i colpi di penalità corrispondenti. Se dichiara "X" o buca non completata / alzata, assegna il punteggio massimo della buca secondo la Regola WHS 3.1b (Net Double Bogey / 0 punti Stableford: Par + colpi ricevuti + 2. Es. Par 4 con 1 colpo ricevuto = 7 colpi, con 2 ricevuti = 8 colpi).
3. **PRIORITÀ ASSOLUTA AL RECAP DEL GIOCATORE:**
   - Se nel testo o nelle note audio il giocatore fa un riepilogo / recap dei colpi (es. "Buca 1: 5, Buca 2: 3, Buca 3: 5, Buca 4: 6, Buca 5: X (7), Buca 6: 5..."), questi punteggi ufficiali hanno PRIORITÀ ASSOLUTA per il campo `score` di ciascuna buca!

### 🏌️‍♂️ DISTINZIONE TATTICA DELL'INTENTO DEI COLPI (SHOT INTENT TAXONOMY):
Un colpo di golf non è mai un semplice valore numerico: lo stesso Ferro 6 può essere usato a 160m per il green o a 30m per un approccio a correre!
Non confondere MAI una scelta strategica o un colpo di tocco con un colpo sbagliato o un 'mishit':
1. **`BUMP_AND_RUN` (Approccio a correre attorno al green):**
   - Quando un ferro medio (Ferro 4, 5, 6, 7, 8, 9, Ibrido) viene usato da corta distanza (< 45m dal green) per far saltare l'avangreen e rotolare verso la bandiera.
   - Tagga `intent: "bump_and_run"`. NON considerarlo MAI un colpo corto o errato: è una scelta tecnica di precisione!
2. **`RECOVERY_PUNCH` (Uscita da difficoltà / Pugno basso):**
   - Quando il giocatore è tra gli alberi, sotto rami bassi, in rough pesante o in ostacolo, e gioca un ferro per rimettere la palla in gioco in fairway (es. 40-90 metri).
   - Tagga `intent: "recovery_punch"`, `is_recovery: true`. Consideralo un ottimo colpo di salvataggio.
3. **`LAYUP` (Piazzamento Tattico):**
   - Quando il giocatore gioca un colpo conservativo (es. secondo colpo su un Par 5 o prima di un ostacolo d'acqua) per posizionarsi alla distanza di approccio ideale.
   - Tagga `intent: "layup"`, `is_layup: true`. Premialo nell'analisi di gestione del percorso (`course_management_score`).
4. **`FULL_SHOT` (Colpo Pieno):**
   - Il colpo standard giocato alla distanza di carry nominale del bastone verso fairway o green.

### 📋 ULTERIORI ISTRUZIONI DI ESTRAZIONE:
- Confronta le distanze dei colpi menzionati con le distanze registrate nella sacca del giocatore.
- Mantieni la rigorosità nella conta dei colpi, Fairway Hit (solo Par 4/5) e GIR (Green in Regulation).
- Genera la `professional_diagnosis` in tono coerente con la Categoria del giocatore.
"""

    config = ai_config
    if config is None:
        # Fallback to OpenAI with provided api_key or env var
        config = AIUserConfig(
            provider="openai",
            openai_api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            openai_model=model_name
        )

    lower_t = transcript_text.lower()
    has_back_9 = any(k in lower_t for k in ["buca 10", "buca10", "tee 10", "buca 11", "buca 12", "buca 13", "buca 14", "buca 15", "buca 16", "buca 17", "buca 18"])

    if len(transcript_text) > 1200 and has_back_9:
        # Split into Front 9 and Back 9
        idx_b10 = lower_t.find("buca 10")
        if idx_b10 == -1:
            idx_b10 = lower_t.find("buca10")
        if idx_b10 == -1:
            idx_b10 = lower_t.find("tee 10")
        if idx_b10 == -1:
            idx_b10 = len(transcript_text) // 2

        t_front = transcript_text[:idx_b10].strip()
        t_back = transcript_text[idx_b10:].strip()

        # Preserve recap in both splits if present anywhere in the transcript
        recap_match = re.search(r'(\[?\d{2}:\d{2}\]?\s*(?:faccio un piccolo recap|recap|riepilogo|buca 1[\s,:]+\d+[\s,:]+buca 2).*)', transcript_text, re.IGNORECASE | re.DOTALL)
        if recap_match:
            recap_str = recap_match.group(1).strip()
            if recap_str not in t_front:
                t_front += f"\n\n[RECAP UFFICIALE COLPI DEL GIOCATORE]:\n{recap_str}"
            if recap_str not in t_back:
                t_back += f"\n\n[RECAP UFFICIALE COLPI DEL GIOCATORE]:\n{recap_str}"

        sys_front = f"{system_prompt}\n\n### ISTRUZIONE DI SPLIT: Analizza ed estrai ESCLUSIVAMENTE le PRIME 9 BUCHE (Buche 1-9)."
        sys_back = f"{system_prompt}\n\n### ISTRUZIONE DI SPLIT: Analizza ed estrai ESCLUSIVAMENTE le SECONDE 9 BUCHE (Buche 10-18)."

        data_front = execute_round_analysis(
            transcript_text=t_front,
            system_prompt=sys_front,
            ai_config=config
        )
        data_back = execute_round_analysis(
            transcript_text=t_back,
            system_prompt=sys_back,
            ai_config=config
        )

        merged_holes = list(data_front.holes) + list(data_back.holes)
        parsed_data = GolfRoundData(
            round_info=data_front.round_info,
            holes=merged_holes,
            performance_summary=data_front.performance_summary
        )
    else:
        parsed_data = execute_round_analysis(
            transcript_text=transcript_text,
            system_prompt=system_prompt,
            ai_config=config
        )

    if not parsed_data.round_info.course_name or parsed_data.round_info.course_name == "Circolo Golf Non Specificato":
        parsed_data.round_info.course_name = active_course.name

    # Arricchimento deterministico parametri giocatore e handicap di gara
    parsed_data.round_info.player_name = parsed_data.round_info.player_name or profile.player_name
    parsed_data.round_info.exact_hcp = parsed_data.round_info.exact_hcp if parsed_data.round_info.exact_hcp is not None else profile.handicap
    parsed_data.round_info.category = parsed_data.round_info.category or profile.category.value

    # Calcolo Course HCP, Playing HCP e Stroke Index dalle buche del campo
    try:
        from core.whs_rules import calculate_course_handicap, calculate_playing_handicap, allocate_hole_strokes
        tee = active_course.get_tee("gialli")
        if tee:
            chcp = calculate_course_handicap(profile.handicap, tee.slope_rating, tee.course_rating, tee.par)
            # Gare individuali FIG di circolo: Playing HCP 100% Course HCP
            phcp = calculate_playing_handicap(chcp, 1.0)
            parsed_data.round_info.course_hcp = chcp
            parsed_data.round_info.playing_hcp = phcp
            parsed_data.round_info.tee_name = tee.tee_name

            si_map = {ch.hole_number: ch.handicap_index for ch in active_course.holes if ch.handicap_index}
            received_map = allocate_hole_strokes(phcp, si_map, len(active_course.holes))
            for h in parsed_data.holes:
                if h.stroke_index is None and h.hole_number in si_map:
                    h.stroke_index = si_map[h.hole_number]
                h.received_strokes = received_map.get(h.hole_number, 0)
                h.net_score = h.score - h.received_strokes
                h.stableford_points = max(0, 2 + h.par - h.net_score)
                h.stableford_gross_points = max(0, 2 + h.par - h.score)
    except Exception:
        pass

    # Arricchimento deterministico dell'intento dei colpi (Shot Intent Inference)
    for h in parsed_data.holes:
        prev_lie_str = "tee"
        for s in h.shots:
            if not getattr(s, "intent", None) or s.intent == ShotIntent.FULL_SHOT:
                inf = infer_shot_intent(
                    text=s.notes or "",
                    club=s.club,
                    lie=s.lie.value if hasattr(s.lie, "value") else str(s.lie),
                    distance_to_green=s.distance_meters or s.raw_distance,
                    shot_index=s.shot_index,
                    par=h.par,
                    prev_lie=prev_lie_str
                )
                s.intent = inf["intent"]
                s.is_recovery = inf["is_recovery"]
                s.is_layup = inf["is_layup"]
            prev_lie_str = s.lie.value if hasattr(s.lie, "value") else str(s.lie)

    return parsed_data


def parse_quick_shot_update(text: str) -> Dict[str, Any]:
    """
    Parser rapido euristico/regex per note vocali o messaggi brevi durante il gioco di una buca:
    Estrae:
    - shot_index: int (es. 1, 2, 3...)
    - club: str (es. Driver, Legno 3, Ibrido, Ferro 7, Pitching Wedge, Sand Wedge, Putter)
    - lie: str (fairway, rough, bunker, tee, green)
    - manual_distance: float (es. 135.0 metri da paletto)
    - is_quick_shot: bool (True se il messaggio descrive un singolo colpo di gioco)
    """
    cleaned = text.strip().lower()

    # 1. Riconoscimento numero colpo
    shot_index = None
    num_match = re.search(r"\b(?:colpo|tiro)\s*(\d+)\b", cleaned)
    if num_match:
        shot_index = int(num_match.group(1))
    else:
        ordinal_match = re.search(r"\b(\d+)[°ºª]?\s*(?:colpo|tiro)\b", cleaned)
        if ordinal_match:
            shot_index = int(ordinal_match.group(1))
        elif re.search(r"\b(?:primo|1°)\s*(?:colpo|tiro)\b", cleaned):
            shot_index = 1
        elif re.search(r"\b(?:secondo|2°)\s*(?:colpo|tiro)\b", cleaned):
            shot_index = 2
        elif re.search(r"\b(?:terzo|3°)\s*(?:colpo|tiro)\b", cleaned):
            shot_index = 3
        elif re.search(r"\b(?:quarto|4°)\s*(?:colpo|tiro)\b", cleaned):
            shot_index = 4

    # 2. Riconoscimento bastone
    club = None
    club_rules = [
        (r"\b(driver)\b", "Driver"),
        (r"\b(legno\s*3|3\s*wood)\b", "Legno 3"),
        (r"\b(legno\s*5|5\s*wood)\b", "Legno 5"),
        (r"\b(legno\s*([2-9]))\b", lambda m: f"Legno {m.group(2)}"),
        (r"\b(ibrido\s*([2-6]))\b", lambda m: f"Ibrido {m.group(2)}"),
        (r"\b(ibrido)\b", "Ibrido"),
        (r"\b(ferro\s*([3-9]))\b", lambda m: f"Ferro {m.group(2)}"),
        (r"\bf([3-9])\b", lambda m: f"Ferro {m.group(1)}"),
        (r"\b(pitching\s*wedge|pw|pitch)\b", "Pitching Wedge"),
        (r"\b(gap\s*wedge|gw)\b", "Gap Wedge"),
        (r"\b((?:ferro\s*)?approach(?:\s*wedge)?|aw)\b", "Approach Wedge"),
        (r"\b(sand\s*wedge|sw|sand)\b", "Sand Wedge"),
        (r"\b(lob\s*wedge|lw|lob)\b", "Lob Wedge"),
        (r"\b(wedge)\b", "Wedge"),
        (r"\b(putter|putt)\b", "Putter"),
    ]
    for pattern, name in club_rules:
        m = re.search(pattern, cleaned)
        if m:
            club = name(m) if callable(name) else name
            break

    # 3. Riconoscimento lie
    lie = None
    lie_rules = [
        (r"\b(fairway|fway)\b", "fairway"),
        (r"\b(rough|erba\s*alta)\b", "rough"),
        (r"\b(bunker|sabbia)\b", "bunker"),
        (r"\b(tee(\s*box)?|partenza)\b", "tee"),
        (r"\b(green)\b", "green"),
        (r"\b(ostacolo|acqua|hazard)\b", "hazard"),
        (r"\b(fuori\s*limite|ob)\b", "out_of_bounds"),
    ]
    for pattern, name in lie_rules:
        if re.search(pattern, cleaned):
            lie = name
            break

    # 4. Riconoscimento distanza manuale (es. "135 metri", "paletto 150")
    manual_distance = None
    dist_match = re.search(r"\b(?:paletto|distanza|da)?\s*(\d{2,3})\s*(?:metri|metro|mt|m)?\b", cleaned)
    if dist_match:
        val = float(dist_match.group(1))
        if 20 <= val <= 550:
            manual_distance = val

    # Determina se è un update rapido di colpo singolo
    has_signals = any([club is not None, lie is not None, shot_index is not None, manual_distance is not None])
    # Se il testo è troppo lungo o parla di "buca 1... buca 2... score totale", allora è un giro intero
    is_multi_hole = len(re.findall(r"\bbuca\s*\d+\b", cleaned)) > 1 or "score totale" in cleaned

    is_quick_shot = has_signals and not is_multi_hole

    intent_info = infer_shot_intent(
        text=text,
        club=club,
        lie=lie,
        distance_to_green=manual_distance,
        shot_index=shot_index,
    )

    return {
        "is_quick_shot": is_quick_shot,
        "shot_index": shot_index,
        "club": club,
        "lie": lie or ("tee" if shot_index == 1 else "fairway"),
        "manual_distance": manual_distance,
        "raw_text": text,
        "intent": intent_info["intent"],
        "is_recovery": intent_info["is_recovery"],
        "is_layup": intent_info["is_layup"],
        "intent_reason": intent_info["intent_reason"]
    }


ITALIAN_WORD_NUMBERS = {
    "zero": 0, "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4,
    "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
    "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15
}


def word_or_digit_to_int(token: Optional[str]) -> Optional[int]:
    """Converte una cifra numerica o una parola italiana ('due', 'cinque') in intero."""
    if not token:
        return None
    cleaned = token.strip().lower()
    if cleaned.isdigit():
        return int(cleaned)
    return ITALIAN_WORD_NUMBERS.get(cleaned, None)


def parse_hole_closure_intent(text: str) -> Dict[str, Any]:
    """
    Rileva l'intento di CHIUSURA BUCA basato sulla comunicazione esplicita dei PUTT.
    Esempi supportati:
    - 'buca finita, 5 colpi e 2 putt'
    - 'chiuso con 2 putt per un totale di 4'
    - 'fatto 6, 3 putt'
    - 'score 4 con 1 putt'
    - 'chiuso in 5 di cui due putt'
    - '4 colpi e 2 putt'

    Restituisce un dizionario:
    {
        'is_closure': bool,
        'valid': bool,
        'gross_strokes': int | None,
        'putts': int | None,
        'error': str | None
    }
    """
    text_clean = text.strip().lower()

    # Trigger primario: la buca è considerata chiusa quando l'utente menziona esplicitamente i putt
    if not re.search(r"\b(putt|putts|putter)\b", text_clean):
        return {
            "is_closure": False,
            "valid": False,
            "gross_strokes": None,
            "putts": None,
            "error": None
        }

    pat_num = r"(\d+|zero|uno?|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|quindici)"

    gross = None
    putts = None

    # Pattern 1: '[putts] putt per un totale di [gross]' / '[putts] putt e [gross] colpi' / 'chiuso con [putts] putt, [gross] colpi'
    m_putt_first = re.search(
        rf"{pat_num}\s+putts?.*?(?:totale(?:\s+di)?|score(?:\s+di)?|in tutto|per un(?:a)?|concluso in|,|\be\b)\s*{pat_num}(?:\s+colpi)?",
        text_clean
    )
    if m_putt_first:
        putts = word_or_digit_to_int(m_putt_first.group(1))
        gross = word_or_digit_to_int(m_putt_first.group(2))

    # Pattern 2: '[gross] colpi e [putts] putt' / 'fatto [gross], [putts] putt' / 'score [gross] con [putts] putt'
    if gross is None or putts is None:
        m_gross_first = re.search(
            rf"(?:(?:fatto|score|chiuso(?:\s+in)?|chiusa(?:\s+in)?|buca(?:\s+finita)?|totale)\s+)?{pat_num}\s*(?:colpi)?(?:\s*[,e\.]|\s+con|\s+di cui)?\s+{pat_num}\s+putts?",
            text_clean
        )
        if m_gross_first:
            gross = word_or_digit_to_int(m_gross_first.group(1))
            putts = word_or_digit_to_int(m_gross_first.group(2))

    # Pattern 3: Fallback 'chiuso/fatto [gross] [putts] putt'
    if gross is None or putts is None:
        m_fallback = re.search(
            rf"(?:fatto|score|chiuso|chiusa|totale)\s+{pat_num}\s+{pat_num}\s+putts?",
            text_clean
        )
        if m_fallback:
            gross = word_or_digit_to_int(m_fallback.group(1))
            putts = word_or_digit_to_int(m_fallback.group(2))

    # Pattern 4: Solo putt menzionati (es. '2 putt', 'chiuso con 2 putt', 'fatto 1 putt', 'due putt', 'imbucato in 1 putt')
    if putts is None and re.search(r"\b(putt|putts|putter)\b", text_clean):
        m_putts_only = re.search(
            rf"(?:chiuso(?:\s+con)?|fatto|imbucato(?:\s+con)?|con)?\s*{pat_num}\s+putts?",
            text_clean
        )
        if m_putts_only:
            putts = word_or_digit_to_int(m_putts_only.group(1))

    # Pattern 5: Chiusura buca con solo score dichiarato (es. 'chiuso in 5', 'fatto 4', 'score 4', 'fatta in 5')
    if gross is None and not re.search(r"\b(putt|putts)\b", text_clean):
        m_score_only = re.search(
            rf"\b(?:fatto|score|chiuso(?:\s+in)?|chiusa(?:\s+in)?|conclusa(?:\s+in)?|totale)\s+{pat_num}\b",
            text_clean
        )
        if m_score_only:
            gross = word_or_digit_to_int(m_score_only.group(1))
            putts = 2  # Default standard golfistico

    # Pattern 6: Frase generica di chiusura buca (es. 'buca finita', 'buca chiusa', 'fine buca')
    if gross is None and putts is None and re.search(r"\b(buca\s+finita|buca\s+chiusa|fine\s+buca|chiuso\s+la\s+buca|chiusa\s+la\s+buca)\b", text_clean):
        return {
            "is_closure": True,
            "valid": True,
            "gross_strokes": None,
            "putts": 2,
            "error": None
        }

    # Se abbiamo identificato la chiusura della buca
    if putts is not None or gross is not None:
        if gross is not None and gross < 1:
            return {
                "is_closure": True,
                "valid": False,
                "gross_strokes": gross,
                "putts": putts,
                "error": f"I colpi totali ({gross}) devono essere almeno 1."
            }
        if putts is not None and putts < 0:
            return {
                "is_closure": True,
                "valid": False,
                "gross_strokes": gross,
                "putts": putts,
                "error": f"Il numero di putt ({putts}) non può essere negativo."
            }
        # Controllo di validità se entrambi sono presenti
        if gross is not None and putts is not None and putts > gross:
            return {
                "is_closure": True,
                "valid": False,
                "gross_strokes": gross,
                "putts": putts,
                "error": f"Il numero di putt ({putts}) non può superare i colpi totali ({gross})."
            }

        return {
            "is_closure": True,
            "valid": True,
            "gross_strokes": gross,
            "putts": putts if putts is not None else 2,
            "error": None
        }

    return {
        "is_closure": False,
        "valid": False,
        "gross_strokes": None,
        "putts": None,
        "error": None
    }


def parse_retroactive_correction(text: str) -> Dict[str, Any]:
    """
    Riconosce l'intenzione di correggere a posteriori lo score e/o registrare un colpo dimenticato
    su una buca specifica (es. "correggi buca 5: 5 colpi, 2 putt, ferro 7 da 130m",
    oppure comando "/correggi 5 5 2 Ferro 7 130").

    Restituisce:
    - is_correction: bool
    - valid: bool
    - hole_number: Optional[int]
    - gross_strokes: Optional[int]
    - putts: Optional[int] (default 2 se non specificato)
    - club: Optional[str] (es. "Ferro 7")
    - distance: Optional[float] (es. 130.0)
    - error: Optional[str]
    """
    cleaned = text.strip()
    lower = cleaned.lower()

    # Trigger di correzione
    correction_triggers = ["/correggi", "/modifica", "/fix", "correggi", "correzione", "modifica", "dimenticato", "rettifica", "rettifico"]
    is_triggered = any(tr in lower for tr in correction_triggers)

    if not is_triggered:
        return {
            "is_correction": False,
            "valid": False,
            "hole_number": None,
            "gross_strokes": None,
            "putts": 2,
            "club": None,
            "distance": None,
            "error": None
        }

    # Rimuovi prefisso comando se presente
    working_text = cleaned
    for cmd in ["/correggi", "/modifica", "/fix"]:
        if working_text.lower().startswith(cmd):
            working_text = working_text[len(cmd):].strip()
            break

    working_lower = working_text.lower()

    # 1. Riconoscimento numero buca (1-18)
    hole_number = None
    hole_match = re.search(r"\b(?:buca|hole|b)\s*(\d{1,2})\b", working_lower)
    if hole_match:
        hole_number = int(hole_match.group(1))

    # 2. Riconoscimento score lordo (colpi totali)
    gross_strokes = None
    gross_match = re.search(r"\b(?:score|colpi|chiuso(?:\s+in)?|chiusa(?:\s+in)?|totale|fatto|in)\s*(\d+)\b", working_lower)
    if gross_match:
        gross_strokes = int(gross_match.group(1))

    # 3. Riconoscimento putt
    putts = None
    putt_match = re.search(r"\b(\d+)\s*(?:putt|pt)\b", working_lower)
    if putt_match:
        putts = int(putt_match.group(1))

    # 4. Riconoscimento bastone / mazza
    club_name = None
    club_aliases = [
        (r"\b(?:driver|legno\s*1)\b", "Driver"),
        (r"\b(?:legno\s*3|3\s*wood)\b", "Legno 3"),
        (r"\b(?:legno\s*5|5\s*wood)\b", "Legno 5"),
        (r"\b(?:ibrido\s*3|rescue\s*3|3\s*hybrid)\b", "Ibrido 3"),
        (r"\b(?:ibrido\s*4|rescue\s*4|4\s*hybrid)\b", "Ibrido 4"),
        (r"\b(?:ibrido|rescue|hybrid)\b", "Ibrido"),
        (r"\b(?:ferro\s*3|3\s*iron)\b", "Ferro 3"),
        (r"\b(?:ferro\s*4|4\s*iron)\b", "Ferro 4"),
        (r"\b(?:ferro\s*5|5\s*iron)\b", "Ferro 5"),
        (r"\b(?:ferro\s*6|6\s*iron)\b", "Ferro 6"),
        (r"\b(?:ferro\s*7|7\s*iron)\b", "Ferro 7"),
        (r"\b(?:ferro\s*8|8\s*iron)\b", "Ferro 8"),
        (r"\b(?:ferro\s*9|9\s*iron)\b", "Ferro 9"),
        (r"\b(?:pitching\s*wedge|pw|pitching)\b", "Pitching Wedge"),
        (r"\b(?:sand\s*wedge|sw|sand)\b", "Sand Wedge"),
        (r"\b(?:gap\s*wedge|gw)\b", "Gap Wedge (52°)"),
        (r"\b(?:(?:ferro\s*)?approach(?:\s*wedge)?|aw)\b", "Approach Wedge (AW)"),
        (r"\b(?:lob\s*wedge|lw|60\b|60°)\b", "Lob Wedge (60°)"),
        (r"\b(?:putter)\b", "Putter"),
    ]
    for pattern, name in club_aliases:
        if re.search(pattern, working_lower):
            club_name = name
            break

    # 5. Riconoscimento distanza
    distance = None
    dist_match = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*(?:metri|metro|m|mt)\b", working_lower)
    if dist_match:
        distance = float(dist_match.group(1).replace(",", "."))

    # 6. Fallback posizionale da comando numerico (es. "/correggi 5 5 2" oppure "/correggi 5 5 2 Ferro 7 130")
    tokens = working_text.split()
    numeric_tokens = []
    for tok in tokens:
        clean_tok = tok.strip(":,.;")
        if clean_tok.isdigit():
            numeric_tokens.append(int(clean_tok))

    # Se la buca non è stata trovata con keyword 'buca', usa il primo intero se è 1..18
    if hole_number is None and numeric_tokens:
        candidate_hole = numeric_tokens[0]
        if 1 <= candidate_hole <= 18:
            hole_number = candidate_hole
            numeric_tokens = numeric_tokens[1:]

    # Se lo score lordo non è stato trovato con keyword, usa il successivo intero
    if gross_strokes is None and numeric_tokens:
        candidate_gross = numeric_tokens[0]
        if 1 <= candidate_gross <= 20:
            gross_strokes = candidate_gross
            numeric_tokens = numeric_tokens[1:]

    # Se i putt non sono stati trovati con keyword, usa il successivo intero
    if putts is None and numeric_tokens:
        candidate_putt = numeric_tokens[0]
        if 0 <= candidate_putt <= 10:
            putts = candidate_putt
            numeric_tokens = numeric_tokens[1:]

    # Se la distanza non è stata trovata con keyword, e rimane un numero > 20, consideralo distanza
    if distance is None and numeric_tokens:
        candidate_dist = numeric_tokens[0]
        if 15 <= candidate_dist <= 400:
            distance = float(candidate_dist)

    # Default putt se omesso
    if putts is None:
        putts = 2

    # Validazione finale
    if hole_number is None:
        return {
            "is_correction": True,
            "valid": False,
            "hole_number": None,
            "gross_strokes": gross_strokes,
            "putts": putts,
            "club": club_name,
            "distance": distance,
            "error": "Specifica la buca da correggere (es. 'buca 5')."
        }

    if not (1 <= hole_number <= 18):
        return {
            "is_correction": True,
            "valid": False,
            "hole_number": hole_number,
            "gross_strokes": gross_strokes,
            "putts": putts,
            "club": club_name,
            "distance": distance,
            "error": f"Il numero della buca ({hole_number}) deve essere compreso tra 1 e 18."
        }

    if gross_strokes is not None:
        if gross_strokes < 1:
            return {
                "is_correction": True,
                "valid": False,
                "hole_number": hole_number,
                "gross_strokes": gross_strokes,
                "putts": putts,
                "club": club_name,
                "distance": distance,
                "error": f"I colpi totali ({gross_strokes}) devono essere almeno 1."
            }
        if putts > gross_strokes:
            return {
                "is_correction": True,
                "valid": False,
                "hole_number": hole_number,
                "gross_strokes": gross_strokes,
                "putts": putts,
                "club": club_name,
                "distance": distance,
                "error": f"I putt ({putts}) non possono superare i colpi totali ({gross_strokes})."
            }

    return {
        "is_correction": True,
        "valid": True,
        "hole_number": hole_number,
        "gross_strokes": gross_strokes,
        "putts": putts,
        "club": club_name,
        "distance": distance,
        "error": None
    }


def parse_round_sequence_intent(text: str, total_course_holes: int = 18) -> Dict[str, Any]:
    """
    Riconosce l'intenzione dell'utente di impostare la sequenza di buche giocate:
    - Giro standard 18 buche (1..18)
    - Shotgun da qualsiasi buca (es. da buca 7: [7..18, 1..6])
    - Partenza da buca diversa dalla 1 (es. buca 10: [10..18, 1..9])
    - Giro 9 buche: Front 9 (1..9) o Back 9 (10..18)
    - Giro parziale o buche non consecutive (es. "1-6 e 15-18", "1,2,3,4,5")
    - Riconosce inoltre eventuale preferenza di Tee ("gialli", "rossi", "bianchi", "verdi") o genere ("uomo", "donna").
    """
    cleaned = text.strip()
    lower = cleaned.lower()

    # Riconoscimento eventuale tee
    tee_detected = None
    for t in ["gialli", "rossi", "bianchi", "verdi", "neri", "arancioni"]:
        if t in lower:
            tee_detected = t
            break

    # Riconoscimento eventuale genere
    gender_detected = None
    if any(w in lower for w in ["donna", "donne", "femminile", "lady", "ladies"]):
        gender_detected = "Donne"
        if not tee_detected:
            tee_detected = "rossi"
    elif any(w in lower for w in ["uomo", "uomini", "maschile"]):
        gender_detected = "Uomini"
        if not tee_detected:
            tee_detected = "gialli"

    # 1. Shotgun da buca X o partenza da buca X
    shotgun_match = re.search(
        r"\b(?:shotgun|partenza|partito|partiti|iniziato|iniziat[ao]|start|start\s*from)\s*(?:dalla|da|dalle)?\s*(?:buca|hole|b)?\s*(\d{1,2})\b",
        lower
    )
    if shotgun_match:
        start_h = int(shotgun_match.group(1))
        if 1 <= start_h <= total_course_holes:
            seq = list(range(start_h, total_course_holes + 1)) + list(range(1, start_h))
            return {
                "is_sequence_intent": True,
                "sequence": seq,
                "sequence_type": "shotgun",
                "start_hole": start_h,
                "total_holes": len(seq),
                "tee": tee_detected,
                "gender": gender_detected,
                "description": f"Shotgun da buca {start_h} ({start_h}➔{total_course_holes}, poi 1➔{start_h - 1})"
            }

    # 2. Giro 9 buche: Front 9 (1-9)
    if any(k in lower for k in ["prime 9", "front 9", "front nine", "1-9", "1 a 9", "prime nove", "9 buche prime"]):
        seq = list(range(1, 10))
        return {
            "is_sequence_intent": True,
            "sequence": seq,
            "sequence_type": "front_9",
            "start_hole": 1,
            "total_holes": len(seq),
            "tee": tee_detected,
            "gender": gender_detected,
            "description": "Giro 9 buche: Front 9 (Buche 1➔9)"
        }

    # 3. Giro 9 buche: Back 9 (10-18)
    if any(k in lower for k in ["seconde 9", "back 9", "back nine", "10-18", "10 a 18", "ultime 9", "seconde nove"]):
        seq = list(range(10, min(19, total_course_holes + 1)))
        return {
            "is_sequence_intent": True,
            "sequence": seq,
            "sequence_type": "back_9",
            "start_hole": 10,
            "total_holes": len(seq),
            "tee": tee_detected,
            "gender": gender_detected,
            "description": "Giro 9 buche: Back 9 (Buche 10➔18)"
        }

    # 4. Intervalli multipli o parziali (es. "1-6 e 15-18", "1-6, 15-18", "buche 1, 2, 3, 4, 5")
    range_matches = re.findall(r"(\d{1,2})\s*[-–a]\s*(\d{1,2})", lower)
    if range_matches:
        # Se c'è solo un intervallo ed è 1-18 o 1-9 o 10-18, è già gestito altrove
        seq = []
        for start_s, end_s in range_matches:
            s_val = int(start_s)
            e_val = int(end_s)
            if 1 <= s_val <= total_course_holes and 1 <= e_val <= total_course_holes:
                step = 1 if e_val >= s_val else -1
                for h in range(s_val, e_val + step, step):
                    if h not in seq:
                        seq.append(h)
        if seq and (len(range_matches) > 1 or (seq != list(range(1, total_course_holes + 1)) and seq != list(range(1, 10)) and seq != list(range(10, min(19, total_course_holes + 1))))):
            return {
                "is_sequence_intent": True,
                "sequence": seq,
                "sequence_type": "custom_partial",
                "start_hole": seq[0],
                "total_holes": len(seq),
                "tee": tee_detected,
                "gender": gender_detected,
                "description": f"Giro parziale ({len(seq)} buche: {', '.join(str(h) for h in seq)})"
            }

    # 5. Giro standard 18 buche (o intero campo)
    standard_triggers = [
        r"\b1-18\b", r"\b1\s*a\s*18\b", r"\b18\s*buche\b", r"\bgiro\s*standard\b",
        r"\bgiro\s*completo\b", r"\btutte\s*le\s*buche\b", r"\btutto\s*il\s*giro\b",
        r"\bcompleto\b"
    ]
    if any(re.search(tr, lower) for tr in standard_triggers):
        seq = list(range(1, total_course_holes + 1))
        return {
            "is_sequence_intent": True,
            "sequence": seq,
            "sequence_type": "standard_18",
            "start_hole": 1,
            "total_holes": len(seq),
            "tee": tee_detected,
            "gender": gender_detected,
            "description": f"Giro standard {total_course_holes} buche (1➔{total_course_holes})"
        }

    # Se il messaggio descrive colpi, score o chiusura buca, non è un intento di sequenza giro
    if any(w in lower for w in ["colpi", "colpo", "putt", "fatto", "chiuso", "chiusa", "score", "finita"]):
        return {
            "is_sequence_intent": False,
            "sequence": list(range(1, total_course_holes + 1)),
            "sequence_type": "unknown",
            "start_hole": 1,
            "total_holes": total_course_holes,
            "tee": tee_detected,
            "gender": gender_detected,
            "description": "Non riconosciuto"
        }

    # 6. Lista esplicita di numeri separati da virgole o spazi (es. "buche 1, 2, 3, 7, 8")
    if "buche" in lower or "sequenza" in lower or "giocate" in lower:
        num_candidates = [int(x) for x in re.findall(r"\b(\d{1,2})\b", lower) if 1 <= int(x) <= total_course_holes]
        if len(num_candidates) >= 2:
            return {
                "is_sequence_intent": True,
                "sequence": num_candidates,
                "sequence_type": "custom_partial",
                "start_hole": num_candidates[0],
                "total_holes": len(num_candidates),
                "tee": tee_detected,
                "gender": gender_detected,
                "description": f"Buche personalizzate ({len(num_candidates)} buche: {', '.join(str(h) for h in num_candidates)})"
            }

    return {
        "is_sequence_intent": False,
        "sequence": list(range(1, total_course_holes + 1)),
        "sequence_type": "unknown",
        "start_hole": 1,
        "total_holes": total_course_holes,
        "tee": tee_detected,
        "gender": gender_detected,
        "description": "Non riconosciuto"
    }


def detect_hole_anomalies(hole_data: Dict[str, Any]) -> List[str]:
    """
    Analizza i colpi e lo score di una buca registrata ed evidenzia incongruenze:
    1. Palla in acqua / ostacolo senza penalità (Regola 17).
    2. Fuori limite / palla persa senza penalità (Regola 18).
    3. Par 4/5 chiuso in 2 colpi senza menzione di chip-in / eagle / imbucata dal fairway.
    4. Salto diretto da tee shot a putt senza approccio/green su un Par 4/5.
    5. Palla in green senza putt registrati per chiudere la buca.
    """
    anomalies: List[str] = []
    hole_num = hole_data.get("hole_number", 1)
    par = hole_data.get("par", 4)
    shots = hole_data.get("shots", [])
    penalties = hole_data.get("penalties", 0)
    gross_strokes = hole_data.get("gross_strokes") or hole_data.get("score") or len(shots)
    putts = hole_data.get("putts", 0)
    notes_combined = " ".join([
        str(s.get("notes", "")) + " " + str(s.get("result", "")) + " " + str(s.get("lie", ""))
        for s in shots
    ]).lower()
    raw_desc = str(hole_data.get("description", "")).lower() + " " + notes_combined

    # 1. Palla in acqua senza penalità
    has_water = any(
        s.get("result") == "water" or s.get("lie") == "hazard" or "acqua" in s.get("notes", "").lower() or "lago" in s.get("notes", "").lower()
        for s in shots
    ) or ("acqua" in raw_desc or "lago" in raw_desc or "ostacolo" in raw_desc)
    if has_water and penalties == 0:
        anomalies.append(
            f"💧 <b>Buca {hole_num}:</b> Risulta palla finita in ostacolo d'acqua, ma non è stata registrata alcuna penalità di 1 colpo (Regola 17)."
        )

    # 2. Fuori limite / palla persa senza penalità
    has_ob_lost = any(
        s.get("result") in ["out_of_bounds", "lost"] or s.get("lie") == "out_of_bounds" or "fuori limite" in s.get("notes", "").lower() or "persa" in s.get("notes", "").lower()
        for s in shots
    ) or ("fuori limite" in raw_desc or "palla persa" in raw_desc or "lost ball" in raw_desc)
    if has_ob_lost and penalties == 0:
        anomalies.append(
            f"🚫 <b>Buca {hole_num}:</b> Risulta una palla persa o fuori limite senza colpo di penalità registrato (Regola 18 - colpo e distanza)."
        )

    # 3. Par 4 o 5 chiuso in 2 colpi senza eagle o chip-in
    if par >= 4 and gross_strokes <= 2:
        has_holeout = any(k in raw_desc for k in ["chip-in", "chip in", "eagle", "albatross", "imbucat", "hole in one", "ace", "dal fairway", "imbucata"])
        if not has_holeout:
            anomalies.append(
                f"🦅 <b>Buca {hole_num} (Par {par}):</b> Buca chiusa con soli {gross_strokes} colpi senza indicazione di eagle o imbucata diretta da fuori green."
            )

    # 4. Salto diretto da tee a putt su Par 4 o Par 5
    if par >= 4 and len(shots) >= 2:
        s1 = shots[0]
        s2 = shots[1]
        is_s1_tee = s1.get("lie") in ["tee", None] or s1.get("shot_index") == 1
        is_s2_putt = ("putt" in str(s2.get("club", "")).lower()) or s2.get("lie") == "green"
        if is_s1_tee and is_s2_putt and len(shots) <= 2:
            if not any(k in raw_desc for k in ["green dal tee", "green in 1", "drive sul green", "imbucat"]):
                anomalies.append(
                    f"🏌️ <b>Buca {hole_num} (Par {par}):</b> Risulta un passaggio diretto dal tee al putt senza colpo di avvicinamento al green."
                )

    # 5. Palla in green senza putt registrati
    reached_green = any(s.get("lie") == "green" or s.get("result") == "green" for s in shots) or "in green" in raw_desc
    has_direct_holeout = any(k in raw_desc for k in ["imbucat", "chip-in", "chip in"])
    if reached_green and putts == 0 and not has_direct_holeout:
        anomalies.append(
            f"⛳ <b>Buca {hole_num}:</b> La palla ha raggiunto il green, ma non sono stati registrati putt per la chiusura della buca."
        )

    return anomalies


def parse_audit_correction(text: str) -> Dict[str, Any]:
    """
    Riconosce ed estrae le correzioni espresse in linguaggio naturale dall'utente durante l'audit:
    Esempi:
    - "Buca 4: manca un colpo con ferro 7 verso il green"
    - "Buca 8: aggiungi una penalità per palla in acqua"
    - "Buca 12: il secondo colpo era con ibrido, non con ferro 5"
    - "Buca 10: ho fatto 3 putt, non 2"
    - "Buca 5: mancava un approccio con sand wedge"
    - "Buca 7 tutto ok" o "Tutto corretto"
    """
    cleaned = text.strip()
    lower = cleaned.lower()

    # Riconoscimento intenzione di conferma globale
    confirmation_triggers = [
        "tutto corretto", "tutto ok", "confermo", "conferma", "procedi",
        "analizza", "puoi analizzare", "tutto giusto", "ok così", "va bene così",
        "confermo tutto", "/conferma"
    ]
    if any(re.search(rf"\b{re.escape(tr)}\b", lower) for tr in confirmation_triggers):
        return {
            "is_correction": False,
            "is_confirmation": True,
            "hole_number": None,
            "action": "confirm_all",
            "details": {}
        }

    # Riconoscimento numero buca
    hole_match = re.search(r"\b(?:buca|hole|b)\s*(\d{1,2})\b", lower)
    hole_num = int(hole_match.group(1)) if hole_match else None

    # Se non c'è una buca esplicita, controlla se inizia con un numero (es. "4: manca ferro 7")
    if hole_num is None:
        leading_num = re.match(r"^(\d{1,2})[\s:\.-]", cleaned)
        if leading_num:
            hole_num = int(leading_num.group(1))

    # 1. Riconoscimento penalità
    if any(k in lower for k in ["penalità", "penalita", "acqua", "fuori limite", "palla persa", "drop", "ostacolo"]):
        p_strokes = 1
        strokes_match = re.search(r"(\d+)\s*(?:colpi|colpo)?\s*(?:di\s*)?penalit", lower)
        if strokes_match:
            p_strokes = int(strokes_match.group(1))
        elif "2 penalità" in lower or "due penalità" in lower:
            p_strokes = 2

        pen_type = "Generica"
        if "acqua" in lower or "lago" in lower or "ostacolo" in lower:
            pen_type = "Palla in Acqua (Regola 17)"
        elif "fuori limite" in lower or "fl" in lower:
            pen_type = "Fuori Limite (Regola 18)"
        elif "palla persa" in lower:
            pen_type = "Palla Persa (Regola 18)"
        elif "drop" in lower:
            pen_type = "Droppaggio (Regola 16/19)"

        return {
            "is_correction": True,
            "is_confirmation": False,
            "hole_number": hole_num,
            "action": "add_penalty",
            "details": {
                "penalty_type": pen_type,
                "penalty_strokes": p_strokes
            }
        }

    # 2. Riconoscimento correzione putt
    putt_match = re.search(r"\b(\d+)\s*(?:putt|pt)\b", lower)
    if putt_match:
        putts_val = int(putt_match.group(1))
        return {
            "is_correction": True,
            "is_confirmation": False,
            "hole_number": hole_num,
            "action": "update_putts",
            "details": {
                "putts": putts_val
            }
        }

    # 3. Riconoscimento colpo mancante o correzione bastone
    # Individua bastone
    club_candidates = [
        "driver", "legno 3", "legno 5", "legno", "ibrido 3", "ibrido 4", "ibrido",
        "ferro 3", "ferro 4", "ferro 5", "ferro 6", "ferro 7", "ferro 8", "ferro 9",
        "pitching wedge", "pw", "gap wedge", "gw", "sand wedge", "sw", "lob wedge", "lw",
        "putter", "approccio"
    ]
    detected_club = None
    for cb in club_candidates:
        if re.search(rf"\b{re.escape(cb)}\b", lower):
            detected_club = cb.title()
            break

    # Individua indice colpo (es. "secondo colpo", "colpo 3")
    shot_idx = None
    num_m = re.search(r"\b(?:colpo|tiro)\s*(\d+)\b", lower)
    if num_m:
        shot_idx = int(num_m.group(1))
    elif "secondo" in lower or "2°" in lower:
        shot_idx = 2
    elif "terzo" in lower or "3°" in lower:
        shot_idx = 3
    elif "quarto" in lower or "4°" in lower:
        shot_idx = 4
    elif "primo" in lower or "1°" in lower:
        shot_idx = 1

    # Individua esito o lie
    result_cand = "fairway"
    if "green" in lower:
        result_cand = "green"
    elif "rough" in lower:
        result_cand = "rough"
    elif "bunker" in lower:
        result_cand = "bunker"
    elif "corto" in lower:
        result_cand = "short"
    elif "lungo" in lower:
        result_cand = "long"
    elif "destra" in lower:
        result_cand = "miss_right"
    elif "sinistra" in lower:
        result_cand = "miss_left"

    if "manca" in lower or "aggiungi" in lower or "inserisci" in lower or detected_club:
        return {
            "is_correction": True,
            "is_confirmation": False,
            "hole_number": hole_num,
            "action": "add_or_update_shot",
            "details": {
                "shot_index": shot_idx,
                "club": detected_club or "Bastone non specificato",
                "result": result_cand,
                "description": cleaned
            }
        }

    return {
        "is_correction": True if hole_num is not None else False,
        "is_confirmation": False,
        "hole_number": hole_num,
        "action": "unknown",
        "details": {"raw_text": cleaned}
    }



