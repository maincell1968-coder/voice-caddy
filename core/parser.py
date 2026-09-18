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

    return {
        "is_quick_shot": is_quick_shot,
        "shot_index": shot_index,
        "club": club,
        "lie": lie or ("tee" if shot_index == 1 else "fairway"),
        "manual_distance": manual_distance,
        "raw_text": text
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

    if gross is not None and putts is not None:
        if gross < 1:
            return {
                "is_closure": True,
                "valid": False,
                "gross_strokes": gross,
                "putts": putts,
                "error": f"I colpi totali ({gross}) devono essere almeno 1."
            }
        if putts < 0:
            return {
                "is_closure": True,
                "valid": False,
                "gross_strokes": gross,
                "putts": putts,
                "error": f"Il numero di putt ({putts}) non può essere negativo."
            }
        # Controllo di validità: il numero di putt non può superare i colpi totali
        if putts > gross:
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
            "putts": putts,
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


