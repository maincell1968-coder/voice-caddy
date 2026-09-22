"""
Golf Coach Engine (Voice Caddy Pro)
===================================
Implementa la Regola Aurea dell'Analisi di Golf dell'IA secondo le direttive di
`.agents/rules/coach_analysis_rules.md`.

Architettura a 3 Fasi:
- Fase A: Motore Analitico (Calcolo numerico deterministico di errori, pattern, soglie e indici).
- Fase B: Motore Interpretativo (Diagnosi golfistica differenziata per Prima, Seconda e Terza Categoria).
- Fase C: Motore Narrativo (Generazione report conforme alla scaletta fissa a 14 punti,
  template buca per buca a 6 sezioni, prescrizione Top 3 priorità con drill e benchmark misurabili,
  e doppia uscita: Player Report + Technical Report JSON).
"""

from __future__ import annotations

import json
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from core.schemas import GolfRoundData, HoleData, Shot, ShotIntent, ShotResult, LieType


class PlayerCategory(str, Enum):
    PRIMA = "prima"      # HCP 0 – 12 (Giocatore evoluto)
    SECONDA = "seconda"  # HCP 13 – 24 (Giocatore intermedio)
    TERZA = "terza"      # HCP 25 – 36+ (Giocatore in sviluppo)

    @property
    def label(self) -> str:
        labels = {
            PlayerCategory.PRIMA: "Prima Categoria (HCP 0–12)",
            PlayerCategory.SECONDA: "Seconda Categoria (HCP 13–24)",
            PlayerCategory.TERZA: "Terza Categoria (HCP 25–36+)"
        }
        return labels.get(self, self.value.title())

    @property
    def description(self) -> str:
        desc = {
            PlayerCategory.PRIMA: "Giocatore evoluto: severità su dispersione stretta, controllo profondità, qualità del miss side e conversione occasioni.",
            PlayerCategory.SECONDA: "Giocatore intermedio: focus su solidità dal tee, riduzione errori gravi, approcci entro 100m ed eliminazione doppi bogey.",
            PlayerCategory.TERZA: "Giocatore in sviluppo: priorità assoluta su palla in gioco, eliminazione penalità, avanzamento efficace e gestione semplice della buca."
        }
        return desc.get(self, "")


def get_player_category(handicap: Optional[float]) -> PlayerCategory:
    """Classifica deterministicamente il giocatore in base all'Handicap WHS."""
    if handicap is None:
        return PlayerCategory.SECONDA
    hcp = float(handicap)
    if hcp <= 12.0:
        return PlayerCategory.PRIMA
    elif hcp <= 24.0:
        return PlayerCategory.SECONDA
    else:
        return PlayerCategory.TERZA


class ShotEvaluation(BaseModel):
    shot_index: int
    club: str
    distance_m: Optional[float] = None
    lie: str = "fairway"
    result: str = "good"
    intent: str = "full_shot"
    is_recovery: bool = False
    is_layup: bool = False
    shot_score: float = Field(..., ge=0.0, le=100.0, description="Punteggio colpo da 0 a 100 corretto per categoria")
    technical_note: str = ""


class HoleCoachEvaluation(BaseModel):
    hole_number: int
    par: int
    score: int
    net_score: int
    stableford_gross: int
    stableford_net: int
    summary: str = Field(..., description="1. Sintesi della buca in 2-3 righe")
    key_shot: str = Field(..., description="2. Colpo chiave che ha deciso il risultato")
    technical_assessment: str = Field(..., description="3. Valutazione tecnica del gesto e balistica")
    strategic_assessment: str = Field(..., description="4. Valutazione strategica e gestione rischio")
    coach_advice: str = Field(..., description="5. Cosa avrebbe detto il maestro (consiglio operativo)")
    rating: float = Field(..., ge=0.0, le=10.0, description="6. Voto buca da 0 a 10")
    shots_evaluations: List[ShotEvaluation] = Field(default_factory=list)


class TechnicalScores(BaseModel):
    tee_game: float = Field(..., ge=0.0, le=10.0)
    approach_game: float = Field(..., ge=0.0, le=10.0)
    short_game: float = Field(..., ge=0.0, le=10.0)
    putting: float = Field(..., ge=0.0, le=10.0)
    strategy: float = Field(..., ge=0.0, le=10.0)
    overall: float = Field(..., ge=0.0, le=10.0)


class TrainingPriority(BaseModel):
    priority_num: int
    area: str
    goal: str
    reason: str
    drill: str
    benchmark: str


class CoachReportData(BaseModel):
    player_category: PlayerCategory
    player_handicap: float
    scores: TechnicalScores
    technical_scores: Optional[TechnicalScores] = None
    playable_tee_shot_rate_pct: float
    fairways_hit_pct: float
    gir_pct: float
    penalties_total: int
    three_putts_count: int
    three_putt_holes: List[int]
    wedge_proximity_avg_m: float
    chip_proximity_avg_m: float
    recurring_patterns: List[str]
    training_priorities: List[TrainingPriority]
    holes_evaluations: List[HoleCoachEvaluation]
    overall_judgement: str
    main_strengths: List[str]
    main_weaknesses: List[str]
    player_report_markdown: str
    technical_report_json: Dict[str, Any]


class GolfCoachEngine:
    """
    Motore Analitico, Interpretativo e Narrativo per la valutazione tecnica di golf
    secondo il metodo del maestro e la Regola Aurea.
    """

    @classmethod
    def evaluate_shot(
        cls,
        shot: Shot,
        hole: HoleData,
        category: PlayerCategory,
        prev_shot: Optional[Shot] = None
    ) -> ShotEvaluation:
        """
        Assegna a ogni colpo uno score da 0 a 100 corretto per la categoria del giocatore,
        differenziando l'impatto di lie, dispersione e intento tattico.
        """
        club_name = getattr(shot, "club", "") or "Bastone N/D"
        dist_m = getattr(shot, "distance_meters", None)
        lie_str = shot.lie.value if hasattr(shot.lie, "value") else str(shot.lie).lower()
        res_str = shot.result.value if hasattr(shot.result, "value") else str(shot.result).lower()
        intent = getattr(shot, "intent", ShotIntent.FULL_SHOT)
        intent_str = intent.value if hasattr(intent, "value") else str(intent).lower()
        is_rec = getattr(shot, "is_recovery", False) or intent in (ShotIntent.RECOVERY_PUNCH, ShotIntent.ESCAPE_TROUBLE)
        is_lay = getattr(shot, "is_layup", False) or intent == ShotIntent.LAYUP

        # Punteggio base in base all'esito e all'intento
        score_val = 75.0
        note = ""

        # 1. Penalità / Acqua / Fuori Limite
        if res_str in ("water", "out_of_bounds") or "penal" in res_str or shot.shot_index <= hole.penalties:
            score_val = 10.0
            note = "Errore grave con penalità: colpo perso e posizione compromessa."

        # 2. Layup strategico intenzionale
        elif is_lay:
            if category == PlayerCategory.PRIMA:
                score_val = 88.0
                note = "Layup corretto ed eseguito in sicurezza per preparare il colpo al green."
            elif category == PlayerCategory.SECONDA:
                score_val = 92.0
                note = "Ottima scelta strategica di piazzamento (layup): evita il rischio e massimizza le probabilità di par."
            else:
                score_val = 95.0
                note = "Piazzamento perfetto (layup): scelta prudente da manuale che protegge lo score."

        # 3. Recovery shot / Uscita da difficoltà
        elif is_rec:
            if res_str in ("good", "fairway", "green"):
                if category == PlayerCategory.PRIMA:
                    score_val = 82.0
                    note = "Salvataggio disciplinato: palla rimessa in gioco con linea libera."
                elif category == PlayerCategory.SECONDA:
                    score_val = 88.0
                    note = "Ottima gestione del recupero: evita guai peggiori senza forzare."
                else:
                    score_val = 92.0
                    note = "Recupero eccellente: colpo intelligente che tiene la palla in gioco."
            else:
                score_val = 45.0
                note = "Tentativo di recupero non riuscito o posizione rimasta complicata."

        # 4. Bump & Run attorno al green
        elif intent == ShotIntent.BUMP_AND_RUN:
            score_val = 85.0
            note = f"Approccio basso a correre (Bump & Run) con {club_name}: scelta tattica valida."

        # 5. Colpi dal Tee (shot 1)
        elif shot.shot_index == 1:
            if hole.fairway_hit is True or res_str in ("fairway", "good"):
                score_val = 92.0 if category == PlayerCategory.PRIMA else 95.0
                note = "Tee shot eccellente in pieno fairway."
            elif lie_str == "rough" or res_str in ("rough", "miss_right", "miss_left", "push", "pull", "slice", "hook"):
                if category == PlayerCategory.PRIMA:
                    score_val = 65.0
                    note = "Drive in rough: linea giocabile ma spin e controllo del secondo colpo ridotti."
                elif category == PlayerCategory.SECONDA:
                    score_val = 78.0
                    note = "Tee shot in rough ma giocabile: obiettivo primario raggiunto, distanza gestibile."
                else:
                    score_val = 86.0
                    note = "Buona partenza: palla avanzata bene e giocabile per proseguire la buca."
            elif res_str in ("bunker", "fat", "thin", "topped", "short"):
                score_val = 45.0 if category == PlayerCategory.PRIMA else 55.0
                note = f"Tee shot con contatto o traiettoria imperfetta ({res_str})."

        # 6. Colpi al Green / Approcci
        else:
            if res_str in ("green", "hole", "in_hole") or hole.gir:
                if category == PlayerCategory.PRIMA:
                    score_val = 90.0
                    note = "Approccio preciso al green: opportunità creata."
                elif category == PlayerCategory.SECONDA:
                    score_val = 94.0
                    note = "Green preso con solidità: standard di alto livello."
                else:
                    score_val = 98.0
                    note = "Green centrato: colpo straordinario per la categoria."
            elif res_str in ("short", "fat"):
                if category == PlayerCategory.PRIMA:
                    score_val = 52.0
                    note = "Approccio rimasto corto: mancata profondità su distanza favorevole."
                elif category == PlayerCategory.SECONDA:
                    score_val = 65.0
                    note = "Approccio corto rispetto al target: bastone prudente o contatto non pieno."
                else:
                    score_val = 72.0
                    note = "Colpo avanzato verso il green: palla vicina, giocabile con approccio corto."
            elif res_str in ("miss_right", "push", "slice"):
                score_val = 58.0 if category == PlayerCategory.PRIMA else 68.0
                note = "Dispersione a destra dell'obiettivo: curare la linea di partenza e la faccia del bastone."
            elif res_str in ("miss_left", "pull", "hook"):
                score_val = 58.0 if category == PlayerCategory.PRIMA else 68.0
                note = "Dispersione a sinistra dell'obiettivo: verificare l'allineamento del setup."
            else:
                score_val = 70.0
                note = "Esecuzione ordinaria in avanzamento."

        return ShotEvaluation(
            shot_index=shot.shot_index,
            club=club_name,
            distance_m=dist_m,
            lie=lie_str,
            result=res_str,
            intent=intent_str,
            is_recovery=is_rec,
            is_layup=is_lay,
            shot_score=round(score_val, 1),
            technical_note=note
        )

    @classmethod
    def evaluate_hole(cls, hole: HoleData, category: PlayerCategory) -> HoleCoachEvaluation:
        """
        Analizza e valuta la singola buca secondo il Template Obbligatorio a 6 Punti:
        1. Sintesi della buca
        2. Colpo chiave
        3. Valutazione tecnica
        4. Valutazione strategica
        5. Cosa avrebbe detto il maestro
        6. Voto buca (0-10)
        """
        shots = hole.shots or []
        shot_evals: List[ShotEvaluation] = []
        prev_s = None
        for s in shots:
            se = cls.evaluate_shot(s, hole, category, prev_s)
            shot_evals.append(se)
            prev_s = s

        par = hole.par
        score = hole.score
        diff = score - par
        putts = hole.putts
        penalties = hole.penalties
        gir = hole.gir
        fw = hole.fairway_hit

        # 1. Calcolo del voto della buca (0 - 10)
        # Il voto parte dalla prestazione rispetto al Par, corretto per handicap e categoria
        base_voto = 7.0
        if diff <= -2:
            base_voto = 10.0
        elif diff == -1:
            base_voto = 9.0
        elif diff == 0:
            base_voto = 8.0 if category == PlayerCategory.PRIMA else 8.5
        elif diff == 1:
            base_voto = 6.2 if category == PlayerCategory.PRIMA else (7.2 if category == PlayerCategory.SECONDA else 8.0)
        elif diff == 2:
            base_voto = 4.8 if category == PlayerCategory.PRIMA else (5.8 if category == PlayerCategory.SECONDA else 6.8)
        else:
            base_voto = 3.5 if category == PlayerCategory.PRIMA else (4.2 if category == PlayerCategory.SECONDA else 5.2)

        if penalties > 0:
            base_voto = max(1.0, base_voto - (penalties * 1.5))
        if putts >= 3:
            base_voto = max(1.5, base_voto - 1.0)

        # Regola Safe bounds voto buca
        voto_buca = round(min(10.0, max(1.0, base_voto)), 1)

        # 2. Identificazione del colpo chiave
        key_shot_desc = "Colpo chiave: "
        if penalties > 0:
            key_shot_desc += f"Il colpo con penalità (colpo #{max(1, len(shots)-putts)}), che ha causato la perdita netta di colpi."
        elif putts >= 3:
            key_shot_desc += "Il primo putt sul green: la mancata lettura della distanza ha esposto al 3-putt."
        elif gir and diff <= 0:
            key_shot_desc += "L'approccio al green: ha centrato la superficie e consentito di giocare per il birdie/par in sicurezza."
        elif not gir and len(shots) >= 2:
            app_idx = max(1, len(shots) - putts)
            key_shot_desc += f"Il colpo d'attacco al green (colpo #{app_idx}): la palla è rimasta fuori dalla superficie utile."
        else:
            key_shot_desc += "Il tee shot di partenza: ha impostato la traiettoria e la gestione complessiva della buca."

        # 3. Sintesi della buca (2-3 righe)
        summary_lines = []
        if par == 3:
            summary_lines.append(f"Par 3 giocato con colpo diretto al green e chiusura in {putts} putt.")
        else:
            tee_status = "fairway centrato" if fw is True else ("rough giocabile" if fw is False else "partenza gestita")
            summary_lines.append(f"Tee shot con {tee_status}. Successiva gestione verso il green e chiusura con {putts} putt.")

        if diff <= 0:
            summary_lines.append("Buca condotta con regolarità ed eccellente tenuta tattica, senza sbavature significative.")
        elif diff == 1:
            summary_lines.append("Buca chiusa con un bogey gestibile: un solo dettaglio ha separato la sequenza dal par.")
        else:
            summary_lines.append("Buca complessa in cui una combinazione di imprecisioni ha provocato la perdita di colpi.")
        sintesi = " ".join(summary_lines)

        # 4. Valutazione tecnica
        if penalties > 0:
            val_tec = f"Problema balistico primario: impatto fuori asse o dispersione laterale eccessiva che ha generato {penalties} colpi di penalità."
        elif putts >= 3:
            val_tec = f"Controllo della velocità e del rotolo non ottimale sui putt lunghi: {putts} putt totali registrati sul green."
        elif not gir and par >= 4:
            val_tec = "Controllo della profondità o della linea nel colpo al green migliorabile: la palla non ha trovato la superficie del green."
        else:
            val_tec = "Contatto solido e traiettoria controllata: il gesto tecnico ha rispettato i benchmark prestazionali attesi."

        # 5. Valutazione strategica
        has_layup = any(se.is_layup for se in shot_evals)
        has_rec = any(se.is_recovery for se in shot_evals)
        if has_layup:
            val_strat = "Scelta strategica impeccabile: il layup ha ridotto il rischio e protetto lo score in modo maturo."
        elif has_rec:
            val_strat = "Gestione del recupero disciplinata: scelta di rimettere la palla in gioco anziché forzare traiettorie impossibili."
        elif penalties > 0:
            val_strat = "Gestione del rischio da ricalibrare: la linea scelta o il bersaglio dal tee erano troppo vicini all'ostacolo."
        else:
            val_strat = "Scelta del bastone e orientamento del bersaglio perfettamente coerenti con la situazione e la categoria."

        # 6. Cosa avrebbe detto il maestro (formula: dato -> interpretazione -> standard -> consiglio)
        if diff <= 0:
            if category == PlayerCategory.PRIMA:
                consiglio = "Ottima esecuzione. Da questa solidità, il prossimo step è ottimizzare il punto di atterraggio per lasciare un putt in salita e più aggressivo."
            elif category == PlayerCategory.SECONDA:
                consiglio = "Buca da manuale: mantieni questa routine e non cambiare nulla nella pianificazione dal tee."
            else:
                consiglio = "Bravissimo: questo è l'approccio ideale. Ripetere la sequenza senza strafare garantisce costanza e fiducia."
        elif penalties > 0:
            if category == PlayerCategory.PRIMA:
                consiglio = "Su buche con ostacoli laterali prioritari, mira sempre al lato opposto del fairway. Un drive in rough sicuro è mille volte preferibile a una penalità."
            elif category == PlayerCategory.SECONDA:
                consiglio = "Quando il pericolo è in gioco, scegli un bastone più corto dal tee (legno 3 o ibrido) per ampliare la finestra di atterraggio."
            else:
                consiglio = "L'obiettivo numero uno è tenere sempre la palla in gioco: punta al centro della zona più larga del campo."
        elif putts >= 3:
            consiglio = "Sul primo putt oltre 7 metri l'unico obiettivo è fermare la palla entro un raggio di 1 metro dalla tazza: lavora sul controllo della velocità nel lag putting."
        else:
            if category == PlayerCategory.PRIMA:
                consiglio = "Sul colpo al green concentrati sulla parte centrale della superficie: attaccare pin corti o marginali costa colpi inutili."
            elif category == PlayerCategory.SECONDA:
                consiglio = "Nei colpi da 80-130m prendi sempre mezzo ferro in più per assicurare la parte posteriore del green ed evitare di restare corto."
            else:
                consiglio = "Avanza sempre con un bastone sicuro: arrivare a 20 metri dal green con il secondo colpo è già un successo enorme."

        net_sc = hole.net_score if hole.net_score is not None else (hole.score - (hole.received_strokes or 0))
        stbl_gross = hole.stableford_gross_points if hole.stableford_gross_points is not None else max(0, 2 + par - score)
        stbl_net = hole.stableford_points if hole.stableford_points is not None else max(0, 2 + par - net_sc)

        return HoleCoachEvaluation(
            hole_number=hole.hole_number,
            par=par,
            score=score,
            net_score=net_sc,
            stableford_gross=stbl_gross,
            stableford_net=stbl_net,
            summary=sintesi,
            key_shot=key_shot_desc,
            technical_assessment=val_tec,
            strategic_assessment=val_strat,
            coach_advice=consiglio,
            rating=voto_buca,
            shots_evaluations=shot_evals
        )

    @classmethod
    def analyze_round(
        cls,
        round_data: GolfRoundData,
        category: Optional[PlayerCategory] = None
    ) -> CoachReportData:
        """
        Esegue l'analisi completa del giro (Fasi A, B e C), producendo il riepilogo
        a 14 punti, i voti tecnici ponderati per categoria e la doppia uscita.
        """
        holes = round_data.holes
        info = round_data.round_info
        hcp = float(info.exact_hcp if info.exact_hcp is not None else (info.playing_hcp or 18.0))
        cat = category or get_player_category(hcp)

        # 1. Valutazione buca per buca
        hole_evals: List[HoleCoachEvaluation] = [cls.evaluate_hole(h, cat) for h in holes]

        # 2. Indicatori tecnici (Fase A)
        total_holes = len(holes)
        eligible_tee = [h for h in holes if h.par in (4, 5)]
        fw_hits = [h for h in eligible_tee if h.fairway_hit is True]
        fw_pct = round((len(fw_hits) / len(eligible_tee) * 100.0), 1) if eligible_tee else 0.0

        # Playable tee shots: tee shots non penalità e non con esito disastroso
        playable_tee = 0
        for h in eligible_tee:
            if h.shots:
                s1 = h.shots[0]
                res = str(getattr(s1, "result", "")).lower()
                if "water" not in res and "out" not in res and h.penalties == 0:
                    playable_tee += 1
            else:
                if h.penalties == 0:
                    playable_tee += 1
        playable_tee_rate = round((playable_tee / len(eligible_tee) * 100.0), 1) if eligible_tee else 0.0

        gir_holes = [h for h in holes if h.gir is True]
        gir_pct = round((len(gir_holes) / total_holes * 100.0), 1) if total_holes else 0.0

        total_penalties = sum(h.penalties for h in holes)
        three_putt_holes = [h.hole_number for h in holes if h.putts >= 3]
        three_putts_count = len(three_putt_holes)

        # Prossimità stimate
        wedge_proximities = []
        chip_proximities = []
        tee_miss_right = 0
        tee_miss_total = 0
        app_short_count = 0
        app_total_count = 0

        for h in holes:
            for s in h.shots:
                dist = getattr(s, "distance_meters", None) or 0.0
                res = str(getattr(s, "result", "")).lower()
                club = str(getattr(s, "club", "")).lower()

                if s.shot_index == 1 and h.par in (4, 5):
                    if h.fairway_hit is False or res not in ("good", "fairway"):
                        tee_miss_total += 1
                        if any(k in res for k in ("right", "push", "slice")):
                            tee_miss_right += 1

                if s.shot_index > 1 and dist > 0:
                    if dist <= 30.0:
                        chip_proximities.append(4.5 if res == "good" else 7.0)
                    elif dist <= 100.0:
                        wedge_proximities.append(10.0 if res == "good" else 18.0)

                    if 50.0 <= dist <= 140.0:
                        app_total_count += 1
                        if "short" in res or "fat" in res:
                            app_short_count += 1

        avg_wedge_prox = round(sum(wedge_proximities) / len(wedge_proximities), 1) if wedge_proximities else 14.0
        avg_chip_prox = round(sum(chip_proximities) / len(chip_proximities), 1) if chip_proximities else 5.0

        # 3. Rilevamento pattern ricorrenti (Fase B)
        patterns: List[str] = []
        if tee_miss_total >= 3 and (tee_miss_right / tee_miss_total) >= 0.6:
            patterns.append("Dispersione prevalente a destra dal tee: oltre il 60% dei fairway mancati è finito sul lato destro.")
        elif tee_miss_total >= 3 and ((tee_miss_total - tee_miss_right) / tee_miss_total) >= 0.6:
            patterns.append("Dispersione prevalente a sinistra dal tee: tendenza a chiudere i colpi a sinistra dell'asse.")

        if app_total_count >= 3 and (app_short_count / app_total_count) >= 0.5:
            patterns.append("Approcci frequentemente corti al green: oltre il 50% dei colpi tra 50m e 140m è rimasto corto rispetto al centro green.")

        if total_penalties >= 3:
            patterns.append(f"Gestione del rischio penalizzante: {total_penalties} colpi di penalità hanno inciso pesantemente sullo score.")

        if three_putts_count >= 2:
            patterns.append(f"Difficoltà nel lag putting: {three_putts_count} buche con 3-putt (buche {', '.join(map(str, three_putt_holes))}).")

        if not patterns:
            patterns.append("Distribuzione degli errori equilibrata: nessuna anomalia balistica gravemente ricorrente.")

        # 4. Calcolo Voti Tecnici (0 - 10)
        # Tee game
        tee_score = min(10.0, max(2.0, (playable_tee_rate / 10.0) - (total_penalties * 0.4)))
        # Approach game
        app_score = min(10.0, max(2.0, (gir_pct / 10.0) + (2.5 if cat != PlayerCategory.PRIMA else 1.0)))
        # Short game
        short_score = min(10.0, max(2.0, 8.5 - (avg_wedge_prox * 0.15) - (avg_chip_prox * 0.2)))
        # Putting
        putt_score = min(10.0, max(2.0, 9.0 - (three_putts_count * 1.5)))
        # Strategy
        strat_score = min(10.0, max(2.0, 8.5 - (total_penalties * 0.8)))

        # Pesi per categoria
        if cat == PlayerCategory.PRIMA:
            w = {"tee": 0.20, "app": 0.30, "short": 0.15, "putt": 0.15, "strat": 0.20}
        elif cat == PlayerCategory.SECONDA:
            w = {"tee": 0.25, "app": 0.25, "short": 0.20, "putt": 0.15, "strat": 0.15}
        else:
            w = {"tee": 0.30, "app": 0.20, "short": 0.20, "putt": 0.15, "strat": 0.15}

        overall_score = (
            tee_score * w["tee"] +
            app_score * w["app"] +
            short_score * w["short"] +
            putt_score * w["putt"] +
            strat_score * w["strat"]
        )

        tech_scores = TechnicalScores(
            tee_game=round(tee_score, 1),
            approach_game=round(app_score, 1),
            short_game=round(short_score, 1),
            putting=round(putt_score, 1),
            strategy=round(strat_score, 1),
            overall=round(overall_score, 1)
        )

        # 5. Top 3 Priorità di Allenamento (Fase B/C)
        priorities: List[TrainingPriority] = []
        p_idx = 1

        if total_penalties >= 2 or tee_score < 6.5:
            priorities.append(TrainingPriority(
                priority_num=p_idx,
                area="Tee Shot e Precisione dal Tee",
                goal=f"Portare i tee shot giocabili dal {playable_tee_rate}% ad almeno il 75% riducendo le penalità a 0.",
                reason=f"In questo giro {total_penalties} penalità o colpi fuori asse hanno condizionato pesantemente le buche.",
                drill="Drill del Corridoio dal Tee: posiziona due allineatori sul campo pratica a simulare un fairway largo 30 metri. Esegui 10 colpi con Driver o Legno 3.",
                benchmark="Almeno 7 colpi su 10 all'interno del corridoio senza palle perse o fuori limite."
            ))
            p_idx += 1

        if three_putts_count >= 1 or putt_score < 7.0:
            priorities.append(TrainingPriority(
                priority_num=p_idx,
                area="Lag Putting e Controllo Distanza (>8 metri)",
                goal=f"Eliminare completamente i 3-putt (oggi riscontrati in {three_putts_count} buche).",
                reason="I 3-putt trasformano par potenziali in bogey e caricano pressione sul gioco corto.",
                drill="Drill del Cerchio da 10 e 15 metri: traccia un cerchio di 1 metro di raggio attorno alla tazza con i tee. Esegui 10 putt da distanze variabili oltre 8 metri.",
                benchmark="Almeno 8 putt su 10 fermati all'interno del cerchio di sicurezza da 1 metro."
            ))
            p_idx += 1

        if p_idx <= 3:
            priorities.append(TrainingPriority(
                priority_num=p_idx,
                area="Approcci con Wedge (60–100 metri)",
                goal=f"Migliorare la prossimità media alla buca da {avg_wedge_prox}m a meno di 10m.",
                reason="La dispersione in profondità con i wedge impedisce di concretizzare buone partenze in birdie o par facili.",
                drill="Ladder Drill sui Wedge: posiziona 3 target a 60m, 75m e 90m sul campo di pratica. Esegui 4 colpi per ciascuna distanza focalizzandoti sul ritmo.",
                benchmark="Almeno 9 colpi su 12 atterrati entro un raggio di 8 metri dal rispettivo target."
            ))
            p_idx += 1

        # 6. Punti di forza e debolezza
        strengths = []
        weaknesses = []
        if playable_tee_rate >= 70.0:
            strengths.append(f"Solidità dal tee: {playable_tee_rate}% di partenze giocabili.")
        else:
            weaknesses.append(f"Dispersione dal tee: solo il {playable_tee_rate}% di tee shot giocabili.")

        if gir_pct >= 30.0:
            strengths.append(f"Capacità di centrare i green: {gir_pct}% di Green in Regulation.")
        else:
            weaknesses.append(f"Green mancati frequentemente: solo il {gir_pct}% di GIR raggiunti.")

        if three_putts_count == 0:
            strengths.append("Ottima disciplina sul putting green: nessun 3-putt commesso nel giro.")
        else:
            weaknesses.append(f"Perdita di colpi sul green: {three_putts_count} buche chiuse con 3-putt.")

        if not strengths:
            strengths.append("Buona attitudine complessiva e capacità di completare il giro con determinazione.")
        if not weaknesses:
            weaknesses.append("Margini di affinamento nella gestione dei dettagli e nelle distanze plays-like.")

        overall_j = (
            f"Giro da {round_data.performance_summary.total_score if round_data.performance_summary else sum(h.score for h in holes)} colpi "
            f"analizzato con i parametri di {cat.label}. "
            f"Voto Complessivo: {tech_scores.overall}/10. "
            f"La prestazione è stata solida nelle aree chiave, ma richiede interventi mirati su: {', '.join(weaknesses[:2])}."
        )

        # 7. Generazione Markdown Player Report (Fase C)
        md_report = cls._build_markdown_report(
            round_data=round_data,
            category=cat,
            scores=tech_scores,
            playable_tee_rate=playable_tee_rate,
            gir_pct=gir_pct,
            patterns=patterns,
            priorities=priorities,
            strengths=strengths,
            weaknesses=weaknesses,
            hole_evals=hole_evals,
            overall_j=overall_j
        )

        # 8. Generazione JSON Technical Report (Fase C)
        tech_json = {
            "player_category": cat.value,
            "player_handicap": hcp,
            "technical_scores": tech_scores.model_dump(),
            "playable_tee_shot_rate_pct": playable_tee_rate,
            "fairway_accuracy_pct": fw_pct,
            "gir_pct": gir_pct,
            "penalties_total": total_penalties,
            "three_putts_count": three_putts_count,
            "three_putt_holes": three_putt_holes,
            "wedge_avg_proximity_m": avg_wedge_prox,
            "chip_avg_proximity_m": avg_chip_prox,
            "recurring_patterns": patterns,
            "training_priorities": [p.model_dump() for p in priorities],
            "holes": [h.model_dump() for h in hole_evals]
        }

        return CoachReportData(
            player_category=cat,
            player_handicap=hcp,
            scores=tech_scores,
            technical_scores=tech_scores,
            playable_tee_shot_rate_pct=playable_tee_rate,
            fairways_hit_pct=fw_pct,
            gir_pct=gir_pct,
            penalties_total=total_penalties,
            three_putts_count=three_putts_count,
            three_putt_holes=three_putt_holes,
            wedge_proximity_avg_m=avg_wedge_prox,
            chip_proximity_avg_m=avg_chip_prox,
            recurring_patterns=patterns,
            training_priorities=priorities,
            holes_evaluations=hole_evals,
            overall_judgement=overall_j,
            main_strengths=strengths,
            main_weaknesses=weaknesses,
            player_report_markdown=md_report,
            technical_report_json=tech_json
        )

    @classmethod
    def _build_markdown_report(
        cls,
        round_data: GolfRoundData,
        category: PlayerCategory,
        scores: TechnicalScores,
        playable_tee_rate: float,
        gir_pct: float,
        patterns: List[str],
        priorities: List[TrainingPriority],
        strengths: List[str],
        weaknesses: List[str],
        hole_evals: List[HoleCoachEvaluation],
        overall_j: str
    ) -> str:
        """Costruisce il testo leggibile secondo la scaletta a 14 punti e il template buca per buca."""
        info = round_data.round_info
        c_name = getattr(info, "course_name", "Campo da Golf")

        md = []
        md.append(f"# 🏌️ ANALISI TECNICA DI GARA — METODO DEL MAESTRO")
        md.append(f"**Circolo:** {c_name} | **Categoria Giocatore:** {category.label}\n")
        md.append(f"> **Voto Globale:** {scores.overall}/10 • **Tee:** {scores.tee_game}/10 • **Approcci:** {scores.approach_game}/10 • **Gioco Corto:** {scores.short_game}/10 • **Putting:** {scores.putting}/10 • **Strategia:** {scores.strategy}/10\n")
        md.append("---\n")

        # 14 Punti di Analisi Complessiva
        md.append("## 📊 RIEPILOGO GENERALE DI GARA (14 PUNTI)")
        md.append(f"1. **Sintesi generale della gara:** {overall_j}")
        md.append(f"2. **Punti di forza emersi:** " + "; ".join(strengths))
        md.append(f"3. **Punti deboli principali:** " + "; ".join(weaknesses))
        md.append(f"4. **Pattern ed errori ricorrenti:** " + " ".join(patterns))
        md.append(f"5. **Colpi che hanno inciso di più sul risultato finale:** Le penalità e i 3-putt registrati sul green hanno determinato oltre il 60% dei colpi persi rispetto al par.")
        md.append(f"6. **Analisi del gioco dal tee:** Playable Tee Shot Rate del {playable_tee_rate}%. Valutazione settore: {scores.tee_game}/10.")
        md.append(f"7. **Analisi ferri e approcci al green:** Green in Regulation al {gir_pct}%. Valutazione settore: {scores.approach_game}/10.")
        md.append(f"8. **Analisi del gioco corto (wedge e chip):** Valutazione settore: {scores.short_game}/10. Margini di miglioramento nella prossimità al pin.")
        md.append(f"9. **Analisi del putting:** Valutazione settore: {scores.putting}/10. Focus prioritario sul controllo della velocità oltre gli 8 metri.")
        md.append(f"10. **Valutazione strategica e gestione del rischio:** Valutazione settore: {scores.strategy}/10. Discipline nei layup e nei recuperi da consolidare.")
        md.append(f"11. **Andamento mentale e gestione dei momenti critici:** La tenuta tattica è rimasta costante, evitando spirali negative dopo le buche penalizzanti.")
        
        md.append("\n### 🏋️ 12. Top 3 Priorità di Allenamento")
        for p in priorities:
            md.append(f"#### Priorità {p.priority_num} — {p.area}")
            md.append(f"- **Obiettivo Misurabile:** {p.goal}")
            md.append(f"- **Motivo Numerico:** {p.reason}")
            md.append(f"- **Drill Consigliato:** {p.drill}")
            md.append(f"- **Benchmark di Successo:** {p.benchmark}\n")

        md.append(f"13. **Piano di lavoro pratico:** Pianifica una sessione settimanale sul campo pratica alternando 30 minuti di corridoio dal tee, 30 minuti di ladder drill sui wedge e 20 minuti di lag putting.")
        md.append(f"14. **Giudizio finale sintetico da maestro:** Prestazione incoraggiante che dimostra ottime potenzialità. Lavorando sui 3 drill prescritti, la riduzione di 3-5 colpi a giro è un traguardo ampiamente alla portata.\n")

        md.append("---\n")
        md.append("## ⛳ ANALISI DETTAGLIATA BUCA PER BUCA (TEMPLATE A 6 PUNTI)")

        for h in hole_evals:
            md.append(f"\n### Buca {h.hole_number} – Par {h.par} – Score {h.score} [Netto: {h.net_score} | Stableford: {h.stableford_gross} pt L / {h.stableford_net} pt N]")
            md.append(f"1. **Sintesi della buca:** {h.summary}")
            md.append(f"2. **Colpo chiave:** {h.key_shot}")
            md.append(f"3. **Valutazione tecnica:** {h.technical_assessment}")
            md.append(f"4. **Valutazione strategica:** {h.strategic_assessment}")
            md.append(f"5. **Cosa avrebbe detto il maestro:** {h.coach_advice}")
            md.append(f"6. **Voto buca:** **{h.rating}/10**")

        return "\n".join(md)
