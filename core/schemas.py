from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class LieType(str, Enum):
    TEE = "tee"
    FAIRWAY = "fairway"
    ROUGH = "rough"
    BUNKER = "bunker"
    GREEN = "green"
    HAZARD = "hazard"
    OUT_OF_BOUNDS = "out_of_bounds"
    UNKNOWN = "unknown"


class ShotResult(str, Enum):
    GOOD = "good"
    HOOK = "hook"
    SLICE = "slice"
    PULL = "pull"
    PUSH = "push"
    FAT = "fat"
    THIN = "thin"
    TOPPED = "topped"
    SHORT = "short"
    LONG = "long"
    FAIRWAY = "fairway"
    GREEN = "green"
    MISS_LEFT = "miss_left"
    MISS_RIGHT = "miss_right"
    BUNKER = "bunker"
    WATER = "water"


class ShotIntent(str, Enum):
    FULL_SHOT = "full_shot"            # Colpo pieno standard verso fairway o green
    LAYUP = "layup"                    # Piazzamento tattico intenzionale (es. Par 5 o prima di un ostacolo)
    RECOVERY_PUNCH = "recovery_punch"  # Uscita da difficoltà / colpo basso da alberi o rough per rimettersi in gioco
    BUMP_AND_RUN = "bump_and_run"      # Approccio basso a correre attorno al green con ferro medio (es. F6/F7 da 20-40m)
    PITCH_FLOP = "pitch_flop"          # Approccio alto / morbido con wedge
    CHIP = "chip"                      # Chip standard dal bordo green
    TEE_SHOT = "tee_shot"              # Colpo dal tee di partenza
    ESCAPE_TROUBLE = "escape_trouble"  # Uscita estrema di sicurezza laterale da ostacolo o boscaglia


class TargetLandingAnalysis(BaseModel):
    ideal_target_zone: str = Field(..., description="L'area di target ideale raccomandata per l'HCP del giocatore su questa buca")
    actual_landing_zone: str = Field(..., description="Dove è effettivamente atterrata la palla dal colpo del giocatore")
    tactical_verdict: str = Field(..., description="Esito strategico: es. 'Bravo! Posizionamento Tattico Perfetto', 'Ottimo Piazzamento', 'Deviazione Tattica a Destra', 'Errore di Selezione Target'")
    caddie_tactical_note: str = Field(..., description="Spiegazione tattica del caddie su come la posizione ha condizionato il colpo successivo")


class Shot(BaseModel):
    shot_index: int = Field(..., description="Indice progressivo del colpo alla buca (1, 2, 3...)")
    club: Optional[str] = Field(None, description="Bastone utilizzato (es. Driver, Ferro 7, Pitching Wedge, Putter)")
    distance_meters: Optional[float] = Field(None, description="Distanza del colpo o al bersaglio in metri")
    lie: LieType = Field(..., description="Superficie da cui si esegue il colpo")
    result: ShotResult = Field(..., description="Esito balistico o destinazione del colpo")
    intent: ShotIntent = Field(default=ShotIntent.FULL_SHOT, description="Intento tattico del colpo (pieno, layup, recovery, bump & run, ecc.)")
    is_recovery: bool = Field(default=False, description="True se il colpo è un'uscita da situazione di difficoltà (alberi, rough profondo, ecc.)")
    is_layup: bool = Field(default=False, description="True se il colpo è un piazzamento strategico conservativo (es. Par 5 o prima di ostacoli)")
    notes: Optional[str] = Field(default="", description="Sensazioni o dettagli tecnici specifici del colpo")
    latitude: Optional[float] = Field(default=None, description="Latitudine GPS del punto di esecuzione del colpo")
    longitude: Optional[float] = Field(default=None, description="Longitudine GPS del punto di esecuzione del colpo")
    altitude: Optional[float] = Field(default=None, description="Quota altimetrica in metri s.l.m. del punto del colpo")
    raw_distance: Optional[float] = Field(default=None, description="Distanza orizzontale in linea d'aria verso il green/pin in metri")
    plays_like_distance: Optional[float] = Field(default=None, description="Distanza effettiva balistica corretta per la pendenza (Plays Like) in metri")
    elevation_diff: Optional[float] = Field(default=None, description="Dislivello tra la palla e il green (+ salita, - discesa) in metri")



class HoleData(BaseModel):
    hole_number: int = Field(..., ge=1, le=18, description="Numero della buca (1-18)")
    par: int = Field(..., ge=3, le=5, description="Par della buca (3, 4 o 5)")
    score: int = Field(..., ge=1, description="Numero totale di colpi effettuati compresi i putt ed eventuali penalità (Score Lordo)")
    stroke_index: Optional[int] = Field(default=None, description="Stroke Index / HCP della buca")
    received_strokes: Optional[int] = Field(default=0, description="Colpi di handicap ricevuti sulla buca")
    net_score: Optional[int] = Field(default=None, description="Colpi netti della buca (score lordo - colpi ricevuti)")
    stableford_points: Optional[int] = Field(default=None, description="Punti Stableford netti della buca")
    stableford_gross_points: Optional[int] = Field(default=None, description="Punti Stableford lordi della buca")
    fairway_hit: Optional[bool] = Field(None, description="True se il primo colpo resta in fairway (solo Par 4 e 5), None su Par 3")
    gir: bool = Field(..., description="True se la palla raggiunge il green con (Par - 2) colpi o meno")
    putts: int = Field(..., ge=0, description="Numero totale di putt effettuati sul green")
    penalties: int = Field(default=0, ge=0, description="Numero di colpi di penalità subiti")
    shots: List[Shot] = Field(default_factory=list, description="Sequenza dettagliata dei colpi della buca")
    target_landing_analysis: Optional[TargetLandingAnalysis] = Field(None, description="Analisi comparativa dell'area di target ideale vs reale")
    root_cause_error: Optional[str] = Field(None, description="Causa tecnica o tattica principale dell'eventuale errore")


class StrokesLostBreakdown(BaseModel):
    tee_shots: float = Field(..., description="Colpi persi dal tee (drive e colpi di partenza)")
    approach_shots: float = Field(..., description="Colpi persi su approcci a lungo/medio raggio (>50m)")
    short_game_around_green: float = Field(..., description="Colpi persi nel gioco corto attorno al green (<50m)")
    putting: float = Field(..., description="Colpi persi sul green")
    penalties: float = Field(..., description="Colpi persi per penalità ed ostacoli fuori limite")


class ProfessionalDiagnosis(BaseModel):
    executive_narrative: str = Field(..., description="Sintesi executive professionale del giro in tono da caddie/PGA Coach")
    biggest_stroke_leak: str = Field(..., description="Analisi precisa dell'area in cui si sono dispersi maggiormente i colpi")
    technical_vs_tactical_split: str = Field(..., description="Distinzione tra errore di esecuzione tecnica vs errore di strategia/course management")
    course_management_score: int = Field(..., ge=1, le=100, description="Punteggio da 1 a 100 relativo alle decisioni strategiche e gestione del percorso")


class TrainingDrill(BaseModel):
    target_area: str = Field(..., description="Area di gioco target (es. Driver, Approcci 60-100m, Lag Putting)")
    drill_name: str = Field(..., description="Nome tecnico del drill (es. 'Drill del Cancello con i Tee')")
    objective: str = Field(..., description="Obiettivo biomeccanico o tattico dell'esercizio")
    setup_and_execution: str = Field(..., description="Istruzioni dettagliate di setup ed esecuzione sul campo di pratica")
    success_benchmark: str = Field(..., description="Target di successo quantificabile (es. 'Completa 8/10 tentativi entro 1.5 metri')")


class CourseManagementStats(BaseModel):
    layups_count: int = Field(default=0, description="Numero totale di layup tattici eseguiti nel giro")
    recoveries_count: int = Field(default=0, description="Numero totale di colpi di recovery/salvataggio eseguiti")
    bump_and_runs_count: int = Field(default=0, description="Numero di approcci a correre (Bump & Run) con ferri medi")
    recovery_success_rate: float = Field(default=0.0, description="Percentuale di buche con recovery chiuse con Par o Net Par")
    course_management_rating: str = Field(default="Standard", description="Valutazione strategica complessiva (es. 'Disciplina Eccellente', 'Strategia Solida', 'Troppi Rischi Inutili')")


class PerformanceSummary(BaseModel):
    total_score: int = Field(..., description="Score totale lordo del giro")
    total_score_net: Optional[int] = Field(default=None, description="Score totale netto del giro")
    total_stableford_points: Optional[int] = Field(default=None, description="Totale punti Stableford netti del giro")
    total_stableford_gross_points: Optional[int] = Field(default=None, description="Totale punti Stableford lordi del giro")
    total_putts: int = Field(..., description="Numero totale di putt del giro")
    fairway_accuracy_pct: float = Field(..., description="Percentuale di fairway presi dal tee nei Par 4 e Par 5")
    gir_pct: float = Field(..., description="Percentuale di Green in Regulation ottenuti nel giro")
    scrambling_pct: float = Field(..., description="Percentuale di salvataggi del par (o meglio) quando si manca il GIR")
    three_putt_holes: List[int] = Field(default_factory=list, description="Lista dei numeri di buca in cui si sono fatti 3 o più putt")
    penalty_strokes_total: int = Field(default=0, description="Somma totale dei colpi di penalità")
    primary_miss_tendency: str = Field(..., description="Tendenza o errore balistico ricorrente identificato")
    professional_diagnosis: ProfessionalDiagnosis = Field(..., description="Diagnosi di livello PGA Coach/Caddie professionale")
    strokes_lost_breakdown: StrokesLostBreakdown = Field(..., description="Ripartizione stimata dei colpi persi per area di gioco")
    training_drills_recommended: List[TrainingDrill] = Field(..., description="Drill di allenamento mirati con benchmark di successo quantificabili")
    course_management_stats: Optional[CourseManagementStats] = Field(default=None, description="Statistiche dettagliate di gestione del percorso e scelte tattiche")


class RoundInfo(BaseModel):
    course_name: Optional[str] = Field(default="Circolo Golf Non Specificato", description="Nome del campo da golf")
    date: Optional[str] = Field(default=None, description="Data del giro se menzionata")
    holes_played: int = Field(default=18, ge=1, le=18, description="Numero totale di buche analizzate")
    game_format: Optional[str] = Field(default="stableford", description="Formula di gara: 'stableford', 'stroke_play', 'medal'")
    player_name: Optional[str] = Field(default=None, description="Nome del giocatore")
    exact_hcp: Optional[float] = Field(default=None, description="Handicap Index WHS")
    course_hcp: Optional[float] = Field(default=None, description="Handicap di Campo (Course Handicap)")
    playing_hcp: Optional[int] = Field(default=None, description="Handicap di Gioco (Playing Handicap)")
    tee_name: Optional[str] = Field(default=None, description="Colore/Tee di partenza giocato")
    category: Optional[str] = Field(default=None, description="Categoria di gioco")


class GolfRoundData(BaseModel):
    round_info: RoundInfo
    holes: List[HoleData]
    performance_summary: PerformanceSummary
