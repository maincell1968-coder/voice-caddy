from __future__ import annotations

import os
import re
from typing import Optional, Dict, Any
from core.schemas import GolfRoundData
from core.user_profile import UserProfile
from core.course import GolfCourse, CONERO_GOLF_CLUB
from core.auth import AIUserConfig
from core.ai_provider import execute_round_analysis


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

    parsed_data = execute_round_analysis(
        transcript_text=transcript_text,
        system_prompt=system_prompt,
        ai_config=config
    )

    if not parsed_data.round_info.course_name or parsed_data.round_info.course_name == "Circolo Golf Non Specificato":
        parsed_data.round_info.course_name = active_course.name

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
        (r"\b(approach\s*wedge|aw)\b", "Approach Wedge"),
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

    return {
        "is_quick_shot": is_quick_shot,
        "shot_index": shot_index,
        "club": club,
        "lie": lie or ("tee" if shot_index == 1 else "fairway"),
        "manual_distance": manual_distance,
        "raw_text": text
    }
