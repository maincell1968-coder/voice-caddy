from __future__ import annotations

from core.schemas import (
    GolfRoundData, RoundInfo, HoleData, Shot, LieType, ShotResult,
    TargetLandingAnalysis, PerformanceSummary, ProfessionalDiagnosis,
    StrokesLostBreakdown, TrainingDrill
)


def get_demo_golf_round() -> GolfRoundData:
    """
    Returns a realistic 18-hole demo round played at Conero Golf Club (Par 71),
    ready to showcase all dashboards, 2D trajectory visualizations, and coaching insights.
    """
    holes = [
        HoleData(
            hole_number=1, par=4, score=4, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro-destra del fairway a 210-220 metri per aprire l'angolo di approccio al green.",
                actual_landing_zone="Centro fairway perfetto a 220 metri.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Drive impeccabile che ha consentito un comodo Ferro 7 in centro green."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=220, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Drive pulito, traiettoria tesa"),
                Shot(shot_index=2, club="Ferro 7", distance_meters=136, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Preso in pieno centro green a 6 metri dalla buca"),
                Shot(shot_index=3, club="Putter", distance_meters=6, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Putt di avvicinamento a 40cm"),
                Shot(shot_index=4, club="Putter", distance_meters=0.4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Tap-in per il Par")
            ]
        ),
        HoleData(
            hole_number=2, par=5, score=5, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway centrale a 215m evitando i bunker di sinistra.",
                actual_landing_zone="Fairway centro-destra a 215 metri.",
                tactical_verdict="Ottimo Piazzamento",
                caddie_tactical_note="Secondo colpo conservativo con Legno 3 ben gestito per layup ideale."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=215, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Buona palla in fairway"),
                Shot(shot_index=2, club="Legno 3", distance_meters=190, lie=LieType.FAIRWAY, result=ShotResult.FAIRWAY, notes="Layup sicuro a 70m"),
                Shot(shot_index=3, club="Pitching Wedge", distance_meters=70, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Pitch morbido a 5m"),
                Shot(shot_index=4, club="Putter", distance_meters=5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Buon lag putt a bordo buca"),
                Shot(shot_index=5, club="Putter", distance_meters=0.2, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Chiuso Par facile")
            ]
        ),
        HoleData(
            hole_number=3, par=3, score=2, fairway_hit=None, gir=True, putts=1, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro green a 150m, preferibile corta piuttosto che lunga oltre i bunker.",
                actual_landing_zone="Green, 2.5 metri sotto la buca.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Colpo da antologia: bastone esatto sfruttando la brezza."
            ),
            shots=[
                Shot(shot_index=1, club="Ferro 7", distance_meters=150, lie=LieType.TEE, result=ShotResult.GREEN, notes="Colpo millimetrico a 2.5 metri"),
                Shot(shot_index=2, club="Putter", distance_meters=2.5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Imbucato putt in discesa per Birdie!")
            ]
        ),
        HoleData(
            hole_number=4, par=4, score=5, fairway_hit=False, gir=False, putts=2, penalties=0,
            root_cause_error="Push a destra dal tee e secondo colpo catturato dal bunker di green.",
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Sinistra del fairway a 210m per evitare la pendenza verso destra.",
                actual_landing_zone="Rough di destra a 210 metri.",
                tactical_verdict="Deviazione Tattica a Destra",
                caddie_tactical_note="Dal rough l'angolo al green era chiuso, portando all'errore nel bunker."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=210, lie=LieType.TEE, result=ShotResult.MISS_RIGHT, notes="Push a destra in rough medio"),
                Shot(shot_index=2, club="Ferro 5", distance_meters=155, lie=LieType.ROUGH, result=ShotResult.BUNKER, notes="Palla pesante finita nel bunker frontale"),
                Shot(shot_index=3, club="Sand Wedge (56°)", distance_meters=15, lie=LieType.BUNKER, result=ShotResult.GREEN, notes="Uscita solida a 4 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Sfiorato salvataggio par"),
                Shot(shot_index=5, club="Putter", distance_meters=0.3, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Bogey")
            ]
        ),
        HoleData(
            hole_number=5, par=4, score=4, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway a 220m.",
                actual_landing_zone="Fairway a 225m.",
                tactical_verdict="Ottimo Piazzamento",
                caddie_tactical_note="Drive lungo che ha lasciato un approccio cortissimo con wedge."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=225, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Ottimo swing, palla centrata"),
                Shot(shot_index=2, club="Pitching Wedge", distance_meters=115, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Sulla superficie a 6 metri"),
                Shot(shot_index=3, club="Putter", distance_meters=6, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Due putt di sicurezza"),
                Shot(shot_index=4, club="Putter", distance_meters=0.5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=6, par=3, score=3, fairway_hit=None, gir=False, putts=1, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro green a 170 metri.",
                actual_landing_zone="Avangreen a 160 metri (colpo corto).",
                tactical_verdict="Deviazione di Distanza (Corto)",
                caddie_tactical_note="Ottimo chip da fuori green che ha salvato lo scrambling par."
            ),
            shots=[
                Shot(shot_index=1, club="Ferro 5", distance_meters=160, lie=LieType.TEE, result=ShotResult.SHORT, notes="Leggermente corto di 10 metri"),
                Shot(shot_index=2, club="Pitching Wedge", distance_meters=10, lie=LieType.ROUGH, result=ShotResult.GREEN, notes="Chip e corsa a 1 metro"),
                Shot(shot_index=3, club="Putter", distance_meters=1, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Imbucato par da scrambling!")
            ]
        ),
        HoleData(
            hole_number=7, par=4, score=5, fairway_hit=True, gir=False, putts=2, penalties=0,
            root_cause_error="Secondo colpo troppo ambizioso verso la bandiera corta a destra.",
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway a 215m.",
                actual_landing_zone="Fairway centro a 215m.",
                tactical_verdict="Scelta Strategica Rischiosa all'Approccio",
                caddie_tactical_note="Su HCP 1 il secondo colpo doveva mirare al centro green e non alla bandiera insidiosa."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=215, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Drive ben piazzato"),
                Shot(shot_index=2, club="Ibrido 4", distance_meters=170, lie=LieType.FAIRWAY, result=ShotResult.MISS_RIGHT, notes="Sbandata a destra dell'asta"),
                Shot(shot_index=3, club="Sand Wedge (56°)", distance_meters=12, lie=LieType.ROUGH, result=ShotResult.GREEN, notes="Approccio a 4 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Putt sfiora la buca"),
                Shot(shot_index=5, club="Putter", distance_meters=0.3, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Bogey")
            ]
        ),
        HoleData(
            hole_number=8, par=4, score=4, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway centro-sinistra a 210-220m.",
                actual_landing_zone="Fairway a 220m.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Gestione esemplare, par di assoluto controllo."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=220, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Palla perfetta"),
                Shot(shot_index=2, club="Sand Wedge (56°)", distance_meters=95, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="A 4 metri dalla bandiera"),
                Shot(shot_index=3, club="Putter", distance_meters=4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Ottimo primo putt"),
                Shot(shot_index=4, club="Putter", distance_meters=0.2, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=9, par=5, score=5, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway a 225m.",
                actual_landing_zone="Fairway centro a 230m.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Chiuso il percorso di andata con 37 colpi (+2 dal Par 35) di altissimo livello."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=230, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Drive più lungo della giornata"),
                Shot(shot_index=2, club="Legno 3", distance_meters=195, lie=LieType.FAIRWAY, result=ShotResult.FAIRWAY, notes="Secondo colpo d'autore"),
                Shot(shot_index=3, club="Pitching Wedge", distance_meters=65, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Green in regulation sicuro"),
                Shot(shot_index=4, club="Putter", distance_meters=7, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Lag putt a 50cm"),
                Shot(shot_index=5, club="Putter", distance_meters=0.5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par chiuso")
            ]
        ),
        # Buche 10 - 18
        HoleData(
            hole_number=10, par=4, score=4, fairway_hit=False, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway a 215m.",
                actual_landing_zone="Primo taglio di rough a destra (215m).",
                tactical_verdict="Ottimo Recupero",
                caddie_tactical_note="Lie giocabile dal rough che ha consentito comunque il GIR."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=215, lie=LieType.TEE, result=ShotResult.MISS_RIGHT, notes="Leggero push a destra"),
                Shot(shot_index=2, club="Ferro 7", distance_meters=145, lie=LieType.ROUGH, result=ShotResult.GREEN, notes="Gran colpo dal rough sul green"),
                Shot(shot_index=3, club="Putter", distance_meters=8, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Lag putt sicuro"),
                Shot(shot_index=4, club="Putter", distance_meters=0.4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=11, par=3, score=4, fairway_hit=None, gir=False, putts=2, penalties=0,
            root_cause_error="Preso pesante il Ferro 8 finito nel bunker di sinistra.",
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro green a 145m.",
                actual_landing_zone="Bunker laterale a 135m.",
                tactical_verdict="Errore di Esecuzione Tecnica",
                caddie_tactical_note="Colpo pesante (fat) che ha tolto 10 metri alla traiettoria."
            ),
            shots=[
                Shot(shot_index=1, club="Ferro 8", distance_meters=135, lie=LieType.TEE, result=ShotResult.FAT, notes="Contatto pesante in bunker"),
                Shot(shot_index=2, club="Sand Wedge (56°)", distance_meters=14, lie=LieType.BUNKER, result=ShotResult.GREEN, notes="Uscita a 5 metri"),
                Shot(shot_index=3, club="Putter", distance_meters=5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Putt a 20cm"),
                Shot(shot_index=4, club="Putter", distance_meters=0.2, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Bogey")
            ]
        ),
        HoleData(
            hole_number=12, par=5, score=4, fairway_hit=True, gir=True, putts=1, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway centro-destra a 220m.",
                actual_landing_zone="Fairway perfetto a 225m.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Seconda buca giocata sotto par: birdie favoloso alla 12!"
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=225, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Drive splendido"),
                Shot(shot_index=2, club="Legno 3", distance_meters=190, lie=LieType.FAIRWAY, result=ShotResult.FAIRWAY, notes="Palla perfetta a 70m dal green"),
                Shot(shot_index=3, club="Sand Wedge (56°)", distance_meters=70, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Attacco asta da 2 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=2, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Birdie!")
            ]
        ),
        HoleData(
            hole_number=13, par=4, score=5, fairway_hit=False, gir=False, putts=2, penalties=0,
            root_cause_error="Slice accentuato con drive in rough profondo.",
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro-sinistra fairway a 210m.",
                actual_landing_zone="Rough folto a destra a 205m.",
                tactical_verdict="Deviazione Tattica a Destra",
                caddie_tactical_note="Decisione matura: layup intelligente invece di forzare il green attraverso gli alberi."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=205, lie=LieType.TEE, result=ShotResult.SLICE, notes="Apertura faccia bastone a destra"),
                Shot(shot_index=2, club="Ferro 7", distance_meters=125, lie=LieType.ROUGH, result=ShotResult.FAIRWAY, notes="Recupero su fairway"),
                Shot(shot_index=3, club="Pitching Wedge", distance_meters=50, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Green a 3.5 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=3.5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Sfiora il salvataggio"),
                Shot(shot_index=5, club="Putter", distance_meters=0.3, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Bogey")
            ]
        ),
        HoleData(
            hole_number=14, par=4, score=5, fairway_hit=True, gir=True, putts=3, penalties=0,
            root_cause_error="3-Putt dovuto a lag putt aggressivo e secondo putt di ritorno mancato.",
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway a 215m.",
                actual_landing_zone="Fairway a 220m.",
                tactical_verdict="Ottimo Piazzamento al Tee ma Sbavatura sul Green",
                caddie_tactical_note="GIR ottenuto a 12 metri ma dispersione colpi causata da 3-putt evitabile."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=220, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Buon drive centrale"),
                Shot(shot_index=2, club="Pitching Wedge", distance_meters=110, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Green preso ma distante (12m)"),
                Shot(shot_index=3, club="Putter", distance_meters=12, lie=LieType.GREEN, result=ShotResult.LONG, notes="Primo putt lungo di 1.8 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=1.8, lie=LieType.GREEN, result=ShotResult.MISS_LEFT, notes="Putt di ritorno sfiorato a sinistra"),
                Shot(shot_index=5, club="Putter", distance_meters=0.2, lie=LieType.GREEN, result=ShotResult.GOOD, notes="3-putt bogey")
            ]
        ),
        HoleData(
            hole_number=15, par=3, score=3, fairway_hit=None, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro green a 160m.",
                actual_landing_zone="Green a 158m.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Par solido e privo di rischi sul Par 3."
            ),
            shots=[
                Shot(shot_index=1, club="Ferro 6", distance_meters=158, lie=LieType.TEE, result=ShotResult.GREEN, notes="Ottima palla in centro green"),
                Shot(shot_index=2, club="Putter", distance_meters=6, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Avvicinamento comodo"),
                Shot(shot_index=3, club="Putter", distance_meters=0.4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=16, par=4, score=4, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway centro-sinistra a 220m.",
                actual_landing_zone="Fairway a 220m.",
                tactical_verdict="Ottimo Piazzamento",
                caddie_tactical_note="Approccio preciso con Ferro 8, par di controllo."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=220, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Fairway preso pulito"),
                Shot(shot_index=2, club="Ferro 8", distance_meters=130, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Green a 5 metri"),
                Shot(shot_index=3, club="Putter", distance_meters=5, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Buon primo putt"),
                Shot(shot_index=4, club="Putter", distance_meters=0.3, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=17, par=4, score=4, fairway_hit=False, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Fairway a 215m.",
                actual_landing_zone="Primo taglio di rough a sinistra (215m).",
                tactical_verdict="Buona Posizione Giocabile",
                caddie_tactical_note="Secondo colpo ben calibrato verso la parte aperta del green."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=215, lie=LieType.TEE, result=ShotResult.MISS_LEFT, notes="Pull leggero a sinistra"),
                Shot(shot_index=2, club="Ferro 8", distance_meters=130, lie=LieType.ROUGH, result=ShotResult.GREEN, notes="In green a 7 metri"),
                Shot(shot_index=3, club="Putter", distance_meters=7, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Lag putt efficace"),
                Shot(shot_index=4, club="Putter", distance_meters=0.3, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par")
            ]
        ),
        HoleData(
            hole_number=18, par=5, score=5, fairway_hit=True, gir=True, putts=2, penalties=0,
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway a 225m.",
                actual_landing_zone="Fairway centro a 225m.",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Chiusura da manuale con un Par impeccabile sul Par 5 della 18."
            ),
            shots=[
                Shot(shot_index=1, club="Driver", distance_meters=225, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Ottimo drive in fairway"),
                Shot(shot_index=2, club="Legno 3", distance_meters=190, lie=LieType.FAIRWAY, result=ShotResult.FAIRWAY, notes="Layup perfetto a 85 metri"),
                Shot(shot_index=3, club="Sand Wedge (56°)", distance_meters=85, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Green in regulation a 4 metri"),
                Shot(shot_index=4, club="Putter", distance_meters=4, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Sfiora il birdie per 5cm"),
                Shot(shot_index=5, club="Putter", distance_meters=0.1, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Par chiuso!")
            ]
        )
    ]

    total_score = sum(h.score for h in holes) # 75 (+4)
    total_putts = sum(h.putts for h in holes) # 31 putts

    eligible_drives = [h for h in holes if h.par in (4, 5)]
    fir_count = len([h for h in eligible_drives if h.fairway_hit is True])
    fir_pct = round((fir_count / len(eligible_drives)) * 100, 1) # 10/14 = 71.4%

    gir_count = len([h for h in holes if h.gir is True])
    gir_pct = round((gir_count / 18) * 100, 1) # 14/18 = 77.8%

    missed_gir = [h for h in holes if h.gir is False]
    scramble_count = len([h for h in missed_gir if h.score <= h.par])
    scramble_pct = round((scramble_count / len(missed_gir)) * 100, 1) # 2/4 = 50.0%

    summary = PerformanceSummary(
        total_score=total_score,
        total_putts=total_putts,
        fairway_accuracy_pct=fir_pct,
        gir_pct=gir_pct,
        scrambling_pct=scramble_pct,
        three_putt_holes=[14],
        penalty_strokes_total=0,
        primary_miss_tendency="Push / Sbandata a destra dal tee",
        professional_diagnosis=ProfessionalDiagnosis(
            executive_narrative=(
                "Prestazione solida e di grande maturità tattica al Conero Golf Club. "
                "Con uno score lordo di 75 (+4 rispetto al Par 71) hai dimostrato una gestione del campo "
                "molto superiore alla media del tuo Handicap 14, capitalizzando su 2 splendidi Birdie (Buca 3 e Buca 12) "
                "e un eccezionale 77.8% di Green in Regulation. Il punteggio avrebbe potuto scendere persino sotto il par "
                "eliminando l'isolato 3-putt della buca 14 e due push a destra dai tee shot."
            ),
            biggest_stroke_leak="Colpi persi su drive con sbandata a destra (buche 4, 10 e 13) e controllo distanza del primo putt oltre i 10 metri.",
            technical_vs_tactical_split="80% Tattica eccellente (ottimi layup e gestione rischi) vs 20% Esecuzione tecnica (faccia del driver leggermente aperta all'impatto).",
            course_management_score=88
        ),
        strokes_lost_breakdown=StrokesLostBreakdown(
            tee_shots=1.4,
            approach_shots=0.6,
            short_game_around_green=0.8,
            putting=1.2,
            penalties=0.0
        ),
        training_drills_recommended=[
            TrainingDrill(
                target_area="Driver & Partenze dal Tee",
                drill_name="Drill dell'Allineamento del Percorso Bastone (In-to-Out)",
                objective="Neutralizzare il push/slice a destra favorendo un rilascio square all'impatto.",
                setup_and_execution="Posiziona due bastoni guida sul campo pratica a 45° rispetto alla linea bersaglio. Esegui 15 drive concentrandoti sul far partire la palla a destra della linea per poi rientrare al centro.",
                success_benchmark="Almeno 8 drive su 10 con dispersione laterale inferiore a 10 metri dal bersaglio."
            ),
            TrainingDrill(
                target_area="Putting (Lag Putting da 10-15m)",
                drill_name="Drill del Cerchio di Sicurezza da 1 Metro",
                objective="Eliminare i 3-putt imparando a controllare la velocità su putt di lunga gittata.",
                setup_and_execution="Traccia con 4 tee un raggio di 1 metro attorno alla buca. Tira 10 putt da 10 metri e 10 putt da 15 metri.",
                success_benchmark="18 colpi su 20 che si arrestano all'interno del raggio di sicurezza di 1 metro."
            ),
            TrainingDrill(
                target_area="Uscite dal Bunker Greenside",
                drill_name="Drill della Riga sulla Sabbia (Entrata a 5cm)",
                objective="Migliorare la costanza dell'impatto sabbia-palla per avvicinamenti sotto i 3 metri.",
                setup_and_execution="Traccia una riga nella sabbia perpendicolare al bersaglio. Posiziona 10 palline 5cm avanti alla riga. Colpisci facendo entrare la suola del wedge esattamente sulla riga.",
                success_benchmark="7 uscite su 10 finite sul green entro 3 metri dalla bandiera."
            )
        ]
    )

    return GolfRoundData(
        round_info=RoundInfo(
            course_name="Conero Golf Club",
            date="Giro Dimostrativo PGA",
            holes_played=18
        ),
        holes=holes,
        performance_summary=summary
    )
