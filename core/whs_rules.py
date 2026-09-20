from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


def round_half_up(val: float) -> int:
    """
    Arrotondamento matematico standard WHS (0.5 arrotondato verso l'alto).
    """
    d = Decimal(str(val))
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TeeRating(BaseModel):
    """
    Scheda tecnica e parametri ufficiali del Tee di partenza (WHS).
    """
    tee_name: str = Field(..., description="Nome o colore del tee (es. Bianchi, Gialli, Verdi, Rossi, Arancioni)")
    color_code: str = Field(default="yellow", description="Codice identificativo o colore")
    gender: str = Field(default="Uomini", description="Genere/Categoria (Uomini o Donne)")
    course_rating: float = Field(..., description="Course Rating (CR)")
    slope_rating: int = Field(..., ge=55, le=155, description="Slope Rating (SR)")
    par: int = Field(..., ge=27, le=74, description="Par complessivo del tracciato")
    holes_count: int = Field(default=18, description="Numero di buche (9 o 18)")
    length_meters: Optional[int] = Field(default=None, description="Metratura totale del percorso da questo tee")
    hole_stroke_indexes: Optional[Dict[int, int]] = Field(
        default=None,
        description="Mappa opzionale buca -> Stroke Index se specifica per questo tee/genere"
    )


class RoundHandicapProfile(BaseModel):
    """
    Profilo matematico dell'handicap e assegnazione colpi per l'intero giro in corso.
    Mantiene lo stato {Utente, Campo, Tee, Playing_HCP, Tabella_Colpi_Per_Buca}.
    """
    user_id: str
    player_name: str
    exact_hcp: float
    course_id: str
    course_name: str
    tee_name: str
    gender: str
    format_name: str = "stableford"
    format_percentage: float = 0.95
    course_rating: float
    slope_rating: int
    par: int
    holes_count: int = 18

    # Valori calcolati
    course_hcp: float = Field(..., description="Handicap di Campo (Course Handicap non arrotondato)")
    playing_hcp: int = Field(..., description="Handicap di Gioco (Playing Handicap arrotondato)")
    hole_strokes_table: Dict[int, int] = Field(..., description="Mappa Buca -> Colpi Ricevuti assegnati")
    hole_pars: Dict[int, int] = Field(default_factory=dict, description="Mappa Buca -> Par")
    hole_stroke_indices: Dict[int, int] = Field(default_factory=dict, description="Mappa Buca -> Stroke Index")

    def get_received_strokes(self, hole_number: int) -> int:
        """Restituisce i colpi ricevuti sulla buca specificata."""
        return self.hole_strokes_table.get(hole_number, 0)

    def get_net_par(self, hole_number: int) -> int:
        """Restituisce il Par Netto (Par della buca + Colpi ricevuti assegnati)."""
        par = self.hole_pars.get(hole_number, 4)
        return par + self.get_received_strokes(hole_number)

    def calculate_hole_score(self, hole_number: int, gross_strokes: int) -> Dict[str, Any]:
        """
        Calcola lo score completo per la buca corrente:
        - Par Netto = Par buca + Colpi ricevuti
        - Punti Stableford = MAX(0, Par Netto - Colpi Effettivi Lordi + 2)
        """
        par = self.hole_pars.get(hole_number, 4)
        received = self.get_received_strokes(hole_number)
        si = self.hole_stroke_indices.get(hole_number, 0)
        return calculate_hole_score(
            hole_number=hole_number,
            par=par,
            received_strokes=received,
            gross_strokes=gross_strokes,
            stroke_index=si
        )

    def format_summary_card(self) -> str:
        """Restituisce la scheda tecnica formattata per Telegram / UI."""
        pct_label = f"{int(self.format_percentage * 100)}%"
        chcp_fmt = f"{self.course_hcp:.2f}"
        strokes_breakdown = []
        # Trova buche con colpi supplementari
        two_strokes = [h for h, s in sorted(self.hole_strokes_table.items()) if s >= 2]
        one_stroke = [h for h, s in sorted(self.hole_strokes_table.items()) if s == 1]
        zero_stroke = [h for h, s in sorted(self.hole_strokes_table.items()) if s <= 0]

        summary = (
            f"📋 <b>SCHEDA HANDICAP WHS — {self.course_name.upper()}</b>\n"
            f"👤 <b>Giocatore:</b> {self.player_name}\n"
            f"🎯 <b>Exact HCP (Index):</b> {self.exact_hcp}\n"
            f"📍 <b>Tee:</b> {self.tee_name.title()} ({self.gender}) | Par {self.par}\n"
            f"📊 <b>CR:</b> {self.course_rating} | <b>Slope:</b> {self.slope_rating}\n"
            f"⚙️ <b>Formato:</b> {self.format_name.title()} ({pct_label})\n\n"
            f"🔢 <b>CALCOLO UFFICIALE:</b>\n"
            f"• <b>Course HCP:</b> <code>({self.exact_hcp} * {self.slope_rating} / 113) + ({self.course_rating} - {self.par})</code> = <b>{chcp_fmt}</b>\n"
            f"• <b>Playing HCP:</b> <code>Round({chcp_fmt} * {pct_label})</code> = <b>{self.playing_hcp} colpi</b>\n\n"
            f"⛳ <b>ASSEGNAZIONE COLPI SULLE BUCHE:</b>\n"
        )
        if two_strokes:
            summary += f"• <b>2 Colpi ricevuti:</b> Buche {', '.join(map(str, two_strokes))}\n"
        if one_stroke:
            if len(one_stroke) == self.holes_count:
                summary += f"• <b>1 Colpo ricevuto:</b> Su tutte le {self.holes_count} buche\n"
            else:
                summary += f"• <b>1 Colpo ricevuto:</b> Buche {', '.join(map(str, one_stroke))}\n"
        if zero_stroke:
            summary += f"• <b>0 Colpi:</b> Buche {', '.join(map(str, zero_stroke))}\n"

        return summary


# ==============================================================================
# LOGICA DETERMINISTICA DI CALCOLO WHS
# ==============================================================================

def calculate_course_handicap(exact_hcp: float, slope_rating: int, course_rating: float, par: int) -> float:
    """
    Passo A - Course Handicap (Handicap di Campo):
    Course HCP = (Handicap Index * (Slope Rating / 113)) + (Course Rating - Par)
    """
    raw_val = (exact_hcp * (slope_rating / 113.0)) + (course_rating - par)
    return round(raw_val, 4)


def calculate_playing_handicap(course_hcp: float, format_percentage: float = 0.95) -> int:
    """
    Passo B - Playing Handicap (Handicap di Gioco):
    Playing HCP = Round(Course HCP * Percentuale_Formato)
    """
    val = course_hcp * format_percentage
    return round_half_up(round(val, 4))


def get_strokes_for_hole(playing_hcp: int, hole_stroke_index: int, holes_count: int = 18) -> int:
    """
    Funzione pura deterministica per calcolare i colpi ricevuti su una singola buca (WHS):
    - Colpi base = floor(playing_hcp / holes_count)
    - Colpo addizionale (+1) se hole_stroke_index <= (playing_hcp % holes_count)
    - Restituisce i colpi ricevuti totali su quella specifica buca.
    Supporta percorsi a 18 e 9 buche e handicap plus (negativi).
    """
    if holes_count <= 0:
        holes_count = 18

    if playing_hcp >= 0:
        base_strokes = playing_hcp // holes_count
        remainder = playing_hcp % holes_count
        extra = 1 if (1 <= hole_stroke_index <= remainder) else 0
        return base_strokes + extra
    else:
        # Handicap scratch/plus negativi: restituiscono colpi sulle buche con SI più alto
        abs_hcp = abs(playing_hcp)
        base_deduct = abs_hcp // holes_count
        remainder = abs_hcp % holes_count
        extra_deduct = 1 if (hole_stroke_index > (holes_count - remainder)) else 0
        return -(base_deduct + extra_deduct)


def allocate_hole_strokes(
    playing_hcp: int,
    stroke_indices: Dict[int, int],
    holes_count: int = 18
) -> Dict[int, int]:
    """
    REGOLA DI ASSEGNAZIONE COLPI SULLE BUCHE:
    Dato il Playing HCP calcolato:
    - Colpi base per buca = floor(Playing HCP / 18)
    - Colpo supplementare (+1) se: Stroke Index della buca <= (Playing HCP modulo 18)

    Supporta sia percorsi a 18 buche che a 9 buche.
    Gestisce anche handicap plus (negativi) sottraendo colpi a partire dalle buche più facili.
    """
    if holes_count <= 0:
        holes_count = 18

    table: Dict[int, int] = {}
    for hole_num, si in stroke_indices.items():
        if si is not None:
            table[hole_num] = get_strokes_for_hole(playing_hcp, si, holes_count)
        else:
            table[hole_num] = get_strokes_for_hole(playing_hcp, hole_num, holes_count)

    return table



def calculate_stableford_points_net(par: int, net_strokes: int) -> int:
    """
    Calcolo punti Stableford netti (Regola 21.1 R&A/USGA):
    Formula: max(0, 2 + par - net_strokes)
    """
    return max(0, 2 + par - net_strokes)


def calculate_stableford_points_gross(par: int, gross_strokes: int) -> int:
    """
    Calcolo punti Stableford lordi (Regola 21.1 R&A/USGA):
    Formula: max(0, 2 + par - gross_strokes)
    """
    return max(0, 2 + par - gross_strokes)


def calculate_hole_score(
    hole_number: int,
    par: int,
    received_strokes: int,
    gross_strokes: int,
    stroke_index: int = 0
) -> Dict[str, Any]:
    """
    LOGICA DI CALCOLO SCORE A CONCLUSIONE BUCA (Regole 3 & 21.1):
    - Colpi Netti = Colpi Lordi - Colpi Ricevuti
    - Par Netto = Par della buca + Colpi ricevuti assegnati
    - Punti Stableford Netti = MAX(0, 2 + Par - Colpi Netti)
    - Punti Stableford Lordi = MAX(0, 2 + Par - Colpi Lordi)
    """
    net_strokes = gross_strokes - received_strokes
    net_par = par + received_strokes
    stableford_net = calculate_stableford_points_net(par, net_strokes)
    stableford_gross = calculate_stableford_points_gross(par, gross_strokes)

    # Definizione etichetta score netto (es. Net Birdie, Net Par)
    diff_net = net_strokes - par
    if diff_net <= -3:
        label = "Net Albatross"
    elif diff_net == -2:
        label = "Net Eagle"
    elif diff_net == -1:
        label = "Net Birdie"
    elif diff_net == 0:
        label = "Net Par"
    elif diff_net == 1:
        label = "Net Bogey"
    elif diff_net == 2:
        label = "Net Doppio Bogey"
    else:
        label = f"Net +{diff_net}"

    return {
        "hole_number": hole_number,
        "par": par,
        "stroke_index": stroke_index,
        "received_strokes": received_strokes,
        "gross_strokes": gross_strokes,
        "net_par": net_par,
        "net_strokes": net_strokes,
        "stableford_points": stableford_net,
        "stableford_gross_points": stableford_gross,
        "to_net_par": diff_net,
        "score_label": label
    }


def generate_tournament_summary_data(round_data: Any) -> Dict[str, Any]:
    """
    Genera il riepilogo ufficiale di gara conforme alle Regole R&A / USGA (Sezioni A-G):
    - Distinzione Stableford vs Gara a Colpi (Stroke Play / Medal).
    - Risultato Lordo e Netto sempre presenti e calcolati.
    - Validazioni preliminari (Sezione D) e gestione dati mancanti.
    - Ordinamento classifiche netta e lorda (Sezioni E, F).
    - Nota di conformità regolamentare (Sezione G).
    """
    info = round_data.round_info
    holes = round_data.holes or []
    summary = round_data.performance_summary

    raw_format = (getattr(info, "game_format", None) or "stableford").lower().strip()
    is_stableford = "stableford" in raw_format or "stbl" in raw_format
    fmt_display = "Stableford (WHS 95%)" if is_stableford else "Gara a Colpi / Stroke Play (100%)"

    # 1. Validazioni preliminari (Sezione D)
    anomalies: List[str] = []
    if not raw_format:
        anomalies.append("Formula di gara non specificata (impostato default Stableford).")
    if not holes:
        anomalies.append("Nessuna buca registrata nel giro.")

    missing_pars = [h.hole_number for h in holes if not h.par]
    if missing_pars:
        anomalies.append(f"Par mancante alle buche: {missing_pars}.")

    missing_scores = [h.hole_number for h in holes if h.score is None or h.score <= 0]
    if missing_scores:
        anomalies.append(f"Colpi lordi mancanti alle buche: {missing_scores}.")

    missing_si = [h.hole_number for h in holes if h.stroke_index is None]
    if missing_si:
        anomalies.append(f"Stroke Index non configurato alle buche: {missing_si} (colpi ricevuti stimati).")

    phcp = getattr(info, "playing_hcp", None)
    if phcp is None:
        anomalies.append("Playing Handicap non configurato nel profilo (colpi netti calcolati sui colpi ricevuti buca per buca).")

    # 2. Calcolo Colpi e Punti
    total_gross = sum(h.score for h in holes if h.score)
    
    # Calcolo colpi netti
    if phcp is not None:
        if phcp >= 0:
            total_net = total_gross - phcp
        else:
            total_net = total_gross + abs(phcp)
    else:
        # Somma netti buca per buca se colpi ricevuti sono presenti
        total_net = sum((h.net_score if h.net_score is not None else (h.score - (h.received_strokes or 0))) for h in holes)

    # Calcolo Stableford
    total_stbl_net = sum((h.stableford_points if h.stableford_points is not None else calculate_stableford_points_net(h.par, (h.score - (h.received_strokes or 0)))) for h in holes)
    total_stbl_gross = sum((h.stableford_gross_points if h.stableford_gross_points is not None else calculate_stableford_points_gross(h.par, h.score)) for h in holes)

    # 3. Metodo di Calcolo Utilizzato (Sezione B)
    if is_stableford:
        calc_method = (
            "Regola 21.1 R&A/USGA e World Handicap System: "
            "per ogni buca Colpi Netti = Colpi Lordi - Colpi HCP Ricevuti (per Stroke Index); "
            "Punti Stableford Netti = max(0, 2 + Par - Colpi Netti); "
            "Punti Stableford Lordi = max(0, 2 + Par - Colpi Lordi); "
            "Totale Colpi Netti = Colpi Lordi Totali - Playing Handicap."
        )
    else:
        calc_method = (
            "Regola 3 R&A/USGA e World Handicap System: "
            "Colpi Lordi = Somma dei colpi effettivi giocati; "
            "Colpi Netti = Colpi Lordi Totali - Playing Handicap (in caso di HCP plus: Colpi Lordi + |Playing HCP|)."
        )

    # 4. Riga Risultati Giocatore (Sezione C)
    player_name = getattr(info, "player_name", None) or "Giocatore"
    exact_hcp = getattr(info, "exact_hcp", None)
    course_hcp = getattr(info, "course_hcp", None)
    hcp_idx_str = f"{exact_hcp:.1f}" if exact_hcp is not None else "N/D"
    chcp_str = f"{course_hcp:.1f}" if course_hcp is not None else "N/D"
    phcp_str = str(phcp) if phcp is not None else "N/D"

    # 5. Classifiche (Sezioni E, F)
    # Per giro individuale la posizione è 1° (o qualificata se torneo multiplayer)
    if is_stableford:
        leaderboard_net = {
            "criterio": "Punti Stableford Netti (ordine decrescente)",
            "posizione": "1° Netto",
            "valore": f"{total_stbl_net} pt"
        }
        leaderboard_gross = {
            "criterio": "Punti Stableford Lordi (ordine decrescente)",
            "posizione": "1° Lordo",
            "valore": f"{total_stbl_gross} pt"
        }
    else:
        leaderboard_net = {
            "criterio": "Colpi Netti (ordine crescente)",
            "posizione": "1° Netto",
            "valore": f"{total_net} colpi"
        }
        leaderboard_gross = {
            "criterio": "Colpi Lordi (ordine crescente)",
            "posizione": "1° Lordo",
            "valore": f"{total_gross} colpi"
        }

    # 6. Nota di Conformità Regolamentare (Sezione G)
    if is_stableford:
        compliance_note = (
            f"✅ Report conforme alle Regole del Golf R&A/USGA (Regola 21.1 e Regola 3): "
            f"include regolarmente Colpi Lordi ({total_gross}), Colpi Netti ({total_net}), "
            f"Punti Stableford Lordi ({total_stbl_gross} pt) e Punti Stableford Netti ({total_stbl_net} pt)."
        )
    else:
        compliance_note = (
            f"✅ Report conforme alle Regole del Golf R&A/USGA (Regola 3): "
            f"include regolarmente Colpi Lordi ({total_gross}) e Colpi Netti ({total_net})."
        )

    return {
        "is_stableford": is_stableford,
        "format_name": fmt_display,
        "calc_method": calc_method,
        "player_name": player_name,
        "hcp_index": hcp_idx_str,
        "course_hcp": chcp_str,
        "playing_hcp": phcp_str,
        "total_gross": total_gross,
        "total_net": total_net,
        "total_stableford_net": total_stbl_net,
        "total_stableford_gross": total_stbl_gross,
        "anomalies": anomalies,
        "leaderboard_net": leaderboard_net,
        "leaderboard_gross": leaderboard_gross,
        "compliance_note": compliance_note
    }



def compare_match_play_hole(
    player1_gross: int,
    player1_received: int,
    player2_gross: int,
    player2_received: int
) -> int:
    """
    Confronto Match Play per la buca tra due giocatori:
    Restituisce:
       1 se vince il Giocatore 1
      -1 se vince il Giocatore 2
       0 se la buca è pareggiata (halved)
    """
    p1_net = player1_gross - player1_received
    p2_net = player2_gross - player2_received
    if p1_net < p2_net:
        return 1
    elif p2_net < p1_net:
        return -1
    return 0


# ==============================================================================
# FACTORY BUILDER PROFILO GIRO
# ==============================================================================

def build_round_handicap_profile(
    user_id: str,
    player_name: str,
    exact_hcp: float,
    course_id: str,
    course_name: str,
    tee_rating: TeeRating,
    stroke_indices: Dict[int, int],
    hole_pars: Dict[int, int],
    format_name: str = "stableford",
    format_percentage: Optional[float] = None
) -> RoundHandicapProfile:
    """
    Costruisce l'intero profilo matematico WHS per il giro in base ai parametri ufficiali.
    """
    # Formato di gara di default: Stableford 95%, Match Play 100%
    if format_percentage is None:
        if "match" in format_name.lower():
            format_percentage = 1.0
            format_name = "match play"
        elif "stroke" in format_name.lower():
            format_percentage = 1.0
            format_name = "stroke play"
        else:
            format_percentage = 0.95
            format_name = "stableford"

    # Passo A - Course HCP
    course_hcp = calculate_course_handicap(
        exact_hcp=exact_hcp,
        slope_rating=tee_rating.slope_rating,
        course_rating=tee_rating.course_rating,
        par=tee_rating.par
    )

    # Passo B - Playing HCP
    playing_hcp = calculate_playing_handicap(
        course_hcp=course_hcp,
        format_percentage=format_percentage
    )

    # Assegnazione colpi buca per buca
    active_si = tee_rating.hole_stroke_indexes if tee_rating.hole_stroke_indexes else stroke_indices
    hole_strokes_table = allocate_hole_strokes(
        playing_hcp=playing_hcp,
        stroke_indices=active_si,
        holes_count=tee_rating.holes_count
    )

    return RoundHandicapProfile(
        user_id=user_id,
        player_name=player_name,
        exact_hcp=exact_hcp,
        course_id=course_id,
        course_name=course_name,
        tee_name=tee_rating.tee_name,
        gender=tee_rating.gender,
        format_name=format_name,
        format_percentage=format_percentage,
        course_rating=tee_rating.course_rating,
        slope_rating=tee_rating.slope_rating,
        par=tee_rating.par,
        holes_count=tee_rating.holes_count,
        course_hcp=course_hcp,
        playing_hcp=playing_hcp,
        hole_strokes_table=hole_strokes_table,
        hole_pars=hole_pars,
        hole_stroke_indices=active_si
    )
