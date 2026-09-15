import os
from typing import Optional
from openai import OpenAI
from core.schemas import GolfRoundData
from core.user_profile import UserProfile
from core.course import GolfCourse, CONERO_GOLF_CLUB


def parse_golf_audio_transcript(
    transcript_text: str,
    user_profile: Optional[UserProfile] = None,
    course: Optional[GolfCourse] = None,
    api_key: Optional[str] = None
) -> GolfRoundData:
    """
    Parses unstructured golf audio transcripts into a structured Pydantic GolfRoundData object,
    evaluating the Target Landing Area (Ideal vs Actual landing zone) based on player's HCP and course parameters.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OpenAI API Key non trovata.")

    profile = user_profile or UserProfile()
    active_course = course or CONERO_GOLF_CLUB

    tone_instructions = profile.get_tone_system_instruction()
    bag_distances_context = profile.format_club_distances_prompt_context()

    course_context = f"CAMPO DI GIOCO: {active_course.name} ({active_course.city}) — Par Totale: {active_course.total_par}\n"
    course_context += "Dettaglio Buche del Campo:\n"
    for h in active_course.holes:
        course_context += f"- Buca {h.hole_number}: Par {h.par}, {h.distance_meters or 'N/D'} metri (HCP Index {h.handicap_index or 'N/D'})\n"

    system_prompt = f"""Sei Voice Caddy, un analista PGA Tour e caddie professionista personalizzato.

### 🎭 REGOLAZIONE DEL TONO DIALETTICO E DELLA SEVERITÀ DELL'IA:
{tone_instructions}

### 👤 PROFILO GIOCATORE E DISTANZE IN SACCA:
- Giocatore: {profile.player_name} (Handicap: {profile.handicap} — {profile.category.value})
{bag_distances_context}

### ⛳ CONTESTO DEL CAMPO DA GIOCO SELEZIONATO:
{course_context}

### 🎯 ANALISI DELL'AREA DI TARGET E GESTIONE PERCORSO (TARGET LANDING ANALYSIS):
Per OGNI buca analizzata, compila obbligatoriamente l'oggetto `target_landing_analysis`:
1. **`ideal_target_zone`**: Calcola la zona strategica PERFETTA dove il giocatore con HCP {profile.handicap} avrebbe dovuto atterrare dal tee o nel colpo di approccio per giocare in sicurezza quella buca su questo specifico campo (es. *"Centro-sinistra del fairway a 200m per evitare i bunker a destra"*).
2. **`actual_landing_zone`**: Descrivi dove è atterrata la palla nel colpo reale (es. *"Rough di destra a 210 metri"*).
3. **`tactical_verdict`**: Valutazione strategica:
   - Se la palla è finita nella zona ideale o vicina: Rilascia un elogio esplicito (*"Bravo! Posizionamento Tattico Perfetto"*, *"Ottimo Piazzamento"*, *"Scelta Strategica Vincente"*).
   - Se è finita fuori bersaglio: Assegna il verdetto corretto (*"Deviazione Tattica a Destra"*, *"Errore di Selezione Target"*, *"Scelta Troppo Aggressiva"*).
4. **`caddie_tactical_note`**: Spiegazione di come la posizione atterrata ha condizionato il colpo successivo.

### 📋 ULTERIORI ISTRUZIONI DI ESTRAZIONE:
- Confronta le distanze dei colpi menzionati con le distanze registrate nella sacca del giocatore.
- Mantieni la rigorosità nella conta dei colpi, Fairway Hit (solo Par 4/5) e GIR (Green in Regulation).
- Genera la `professional_diagnosis` in tono coerente con la Categoria del giocatore.
"""

    client = OpenAI(api_key=key)

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
        ],
        response_format=GolfRoundData
    )
    parsed_data: GolfRoundData = completion.choices[0].message.parsed

    if not parsed_data.round_info.course_name or parsed_data.round_info.course_name == "Circolo Golf Non Specificato":
        parsed_data.round_info.course_name = active_course.name

    return parsed_data
