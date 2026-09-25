from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
try:
    from monitoring.base_agent import ZeroCostBaseAgent
except ImportError:
    from voice_caddy.monitoring.base_agent import ZeroCostBaseAgent


class GolfIntelligenceAdvisorAgent(ZeroCostBaseAgent):
    """
    Agente di Intelligence Golfistica e Consulenza Statistica Avanzata (Zero Token Cost).
    Analizza i dati raccolti da sessioni Telegram e Browser e valuta:
    1. Quali statistiche golfistiche avanzate possiamo offrire agli utenti (Strokes Gained,
       dispersione, lie-to-green conversion, bounce-back rate, plays-like efficiency).
    2. In quali ambiti e contesti (allenamento, gara, gioco corto, driver, putt, strategia mentale)
       è possibile arricchire l'esperienza del giocatore.
    3. Catalogo e raccomandazione di tutta la suite di agenti specializzati, utili e gratuiti
       funzionali all'ecosistema Voice Caddy Pro.
    """

    def __init__(self, db_path: Optional[Path] = None, **kwargs):
        project_root = Path(__file__).resolve().parent.parent
        self.db_path = db_path or (project_root / "voice_caddy.db")
        super().__init__(name="GolfIntelligenceAdvisorAgent", **kwargs)

    def _register_default_tools(self) -> None:
        self.register_tool(
            "evaluate_collected_golf_telemetry",
            self.tool_evaluate_collected_golf_telemetry,
            "Analizza in profondità la telemetria golfistica storica registrata su SQLite (tabella rounds)"
        )
        self.register_tool(
            "recommend_advanced_golf_stats",
            self.tool_recommend_advanced_golf_stats,
            "Fornisce l'elenco delle statistiche avanzate calcolabili dal doppio flusso Telegram/Browser"
        )
        self.register_tool(
            "suggest_free_specialized_agents_suite",
            self.tool_suggest_free_specialized_agents_suite,
            "Propone l'ecosistema completo di agenti specializzati a costo zero per Voice Caddy Pro"
        )
        self.register_tool(
            "generate_strategic_intelligence_report",
            self.tool_generate_strategic_intelligence_report,
            "Produce il report strategico completo per lo sviluppo prodotto e l'arricchimento dell'esperienza utente"
        )

    def tool_evaluate_collected_golf_telemetry(self, db_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Ispeziona i record delle partite giocate per estrarre medie prestazionali
        e individuare margini di approfondimento statistico.
        """
        target_db = db_path or self.db_path
        if not target_db or (not target_db.exists() and str(target_db) != ":memory:"):
            return {
                "total_rounds_analyzed": 0,
                "data_depth": "Nessun giro registrato a database",
                "metrics_available": []
            }

        conn = self.guardrail.open_readonly_sqlite(target_db)
        try:
            cursor = conn.cursor()
            query = """
                SELECT COUNT(*) as cnt,
                       AVG(total_score) as avg_score,
                       AVG(total_putts) as avg_putts,
                       AVG(fairway_accuracy_pct) as avg_fir,
                       AVG(gir_pct) as avg_gir,
                       AVG(scrambling_pct) as avg_scrambling,
                       AVG(penalty_strokes) as avg_penalties
                FROM rounds
            """
            self.guardrail.assert_readonly_sql(query)
            cursor.execute(query)
            row = cursor.fetchone()
            cnt = row["cnt"] if row else 0

            return {
                "total_rounds_analyzed": cnt,
                "avg_score": round(row["avg_score"] or 0, 1),
                "avg_putts": round(row["avg_putts"] or 0, 1),
                "avg_fir_pct": round(row["avg_fir"] or 0, 1),
                "avg_gir_pct": round(row["avg_gir"] or 0, 1),
                "avg_scrambling_pct": round(row["avg_scrambling"] or 0, 1),
                "avg_penalties": round(row["avg_penalties"] or 0, 1),
                "data_depth": "Elevata" if cnt > 10 else ("Media" if cnt > 0 else "Base")
            }
        finally:
            conn.close()

    def tool_recommend_advanced_golf_stats(self) -> Dict[str, Any]:
        """
        Definisce e struttura 8 aree statistiche ad alto valore aggiunto
        calcolabili combinando i dati GPS/vocali di Telegram e l'analisi su Browser.
        """
        return {
            "ambiti_statistici_raccomandati": [
                {
                    "ambito": "1. Balistica & Precisione Partenze (Off-The-Tee)",
                    "statistica": "Ellisse di Dispersione & Miss-Side Tendency",
                    "descrizione": "Mappatura 2D dei tee shot: percentuale di miss a sinistra (hook/pull) vs destra (slice/push) divisa per Driver, Legno 3 e Ibrido. Consente di raccomandare il bastone dal tee con corridoio di dispersione compatibile con la larghezza del fairway.",
                    "valore_per_il_giocatore": "Eliminazione immediata dei colpi di penalità dal tee e miglior posizionamento per il secondo colpo."
                },
                {
                    "ambito": "2. Approccio al Green (Approach Game)",
                    "statistica": "Lie-to-GIR Conversion Matrix",
                    "descrizione": "Percentuale di Green Presi in Regolazione (GIR) calcolata in funzione del lie di partenza (Fairway vs Primo Taglio vs Rough profondo vs Bunker).",
                    "valore_per_il_giocatore": "Insegna a gestire l'approccio in base al rotolo della palla e al contatto (flyer lie nel rough vs controllo dello spin dal fairway)."
                },
                {
                    "ambito": "3. Analisi Avanzata Strokes Gained (Metodologia Mark Broadie / PGA)",
                    "statistica": "Strokes Gained 4-Way (OTT, APP, ARG, PUTT)",
                    "descrizione": "Scomposizione analitica del vantaggio/svantaggio di colpi guadagnati rispetto al benchmark della propria categoria (Scratch, HCP 10, HCP 20, HCP 30).",
                    "valore_per_il_giocatore": "Identificazione oggettiva di dove si perdono davvero colpi (es. 2.1 colpi persi sui putt < 2m vs solo 0.4 colpi persi dal tee)."
                },
                {
                    "ambito": "4. Condizioni Meteo & Orography (Plays-Like Accuracy)",
                    "statistica": "Indice di Efficienza Compensazione Pendenza & Vento",
                    "descrizione": "Correlazione tra la distanza nominale raccomandata (Plays Like Distance calcolata con Open-Elevation) e il reale atterraggio della palla.",
                    "valore_per_il_giocatore": "Fiducia cieca nelle correzioni in salita/discesa sui green rialzati o protetti da dislivelli marcati."
                },
                {
                    "ambito": "5. Resilienza Mentale & Psicologia di Gara",
                    "statistica": "Bounce-Back Factor & Tasso di Rimbalzo Post-Errore",
                    "descrizione": "Frequenza con cui il giocatore realizza Par o Birdie alla buca immediatamente successiva a un Double Bogey o triplo bogey.",
                    "valore_per_il_giocatore": "Monitoraggio della tenuta mentale: previene i 'buchi neri' dove un errore trascina con sé le 3 buche successive."
                },
                {
                    "ambito": "6. Putting Performance per Fasce di Distanza",
                    "statistica": "Make-Rate & Lag Putting Efficiency",
                    "descrizione": "Conversione imbucati in 3 fasce critiche: < 1.5 metri (pressure putts), 1.5-4 metri (scoring putts), > 7 metri (3-putt avoidance rate).",
                    "valore_per_il_giocatore": "Evita di sprecare 4-6 colpi a giro su putt corti affrettati."
                },
                {
                    "ambito": "7. Compliance & ROI dei Consigli del Caddy",
                    "statistica": "Caddy Advice Adherence vs Delta Punteggio",
                    "descrizione": "Confronto statistico tra le buche in cui l'utente ha seguito il bastone/bersaglio suggerito dall'IA vs le buche in cui ha forzato la scelta.",
                    "valore_per_il_giocatore": "Dimostra con i numeri quanto una strategia disciplinata e conservativa abbassi lo score."
                },
                {
                    "ambito": "8. Ritmo di Gioco & Indice di Affaticamento (Fatigue Curve)",
                    "statistica": "Front 9 vs Back 9 Performance Decay & Pace-of-Play",
                    "descrizione": "Analisi differenziale tra le prime 9 buche e le seconde 9 buche in relazione ai minuti trascorsi per buca.",
                    "valore_per_il_giocatore": "Indica se il peggioramento nelle buche finali è dovuto a calo energetico/disidratazione o rallentamenti di gruppo sul percorso."
                }
            ]
        }

    def tool_suggest_free_specialized_agents_suite(self) -> Dict[str, Any]:
        """
        Definisce l'ecosistema completo di agenti specializzati e gratuiti (Zero Token Cost)
        funzionali al progetto Voice Caddy Pro.
        """
        return {
            "suite_agenti_specializzati_gratuiti": [
                {
                    "nome_agente": "SafeVaultDataGuardianAgent",
                    "natura": "Process & Integrity Watcher (Zero Token)",
                    "ruolo": "Garante assoluto della SafeVault Policy. Esegue backup atomici orari, verifica l'integrità SQLite con PRAGMA integrity_check e blocca preventivamente qualsiasi comando distruttivo su database e profili utente.",
                    "utilità": "Prevenzione categorica di perdita dati durante aggiornamenti, rilasci o test."
                },
                {
                    "nome_agente": "PaceOfPlayMarshallAgent",
                    "natura": "Time & Sensor Watcher (Zero Token)",
                    "ruolo": "Monitora il tempo trascorso su ciascuna buca e l'intervallo tra i tee shot rispetto ai tempi target del circolo. Notifica il giocatore con notifiche discrete se il ritmo scende sotto lo standard.",
                    "utilità": "Migliora l'esperienza in campo, evita sanzioni federali per gioco lento ed evita rallentamenti a catena."
                },
                {
                    "nome_agente": "TacticalHazardRiskAgent",
                    "natura": "Geometric & Geospatial Engine (Zero Token)",
                    "ruolo": "Calcola matematicamente le coordinate dei pericoli (bunker, ostacoli d'acqua, out of bounds) rispetto alla linea di tiro, calcolando la percentuale di probabilità di errore basata sull'handicap.",
                    "utilità": "Suggerisce la zona di atterraggio più sicura ('fat part of the green' o 'safe side') senza consumare token di inferenza."
                },
                {
                    "nome_agente": "WHSHandicapAuditorAgent",
                    "natura": "Rule Engine & Compliance Watcher (Zero Token)",
                    "ruolo": "Applica deterministicamente le Regole R&A/USGA e WHS: calcolo Playing Handicap, assegnazione colpi ricevuti per Stroke Index, calcolo automatico Lordo/Netto e punteggio Stableford secondo le regole di sistema.",
                    "utilità": "Conformità garantita al 100% con le regole federali senza allucinazioni o errori matematici dell'LLM."
                },
                {
                    "nome_agente": "GPSDriftSensorWatcherAgent",
                    "natura": "Hardware & Geolocation Filter (Zero Token)",
                    "ruolo": "Analizza la precisione dei fix GPS ricevuti da Telegram. Filtra il jitter/drift quando il giocatore è fermo e applica lo snapping ai tee e ai fairway ufficiali.",
                    "utilità": "Elimina letture errate di distanza dovute a rimbalzi di segnale o scarsa ricezione satellitare tra gli alberi."
                },
                {
                    "nome_agente": "CaddyCoachOnDemandAgent",
                    "natura": "Hybrid On-Demand (Zero Token in standby, LLM solo su richiesta esplicita)",
                    "ruolo": "Applica il 'Metodo del Maestro' (.agents/rules/coach_analysis_rules.md). Rimane a costo zero durante tutto il monitoraggio e interviene con inferenza AI SOLO quando il giocatore chiede espressamente un debriefing approfondito a fine gara.",
                    "utilità": "Massima qualità di coaching con consumo di token ridotto al minimo indispensabile."
                }
            ]
        }

    def tool_generate_strategic_intelligence_report(self) -> Dict[str, Any]:
        """Genera il dossier strategico completo integrando telemetria reale e raccomandazioni."""
        telemetry = self.tool_evaluate_collected_golf_telemetry()
        stats = self.tool_recommend_advanced_golf_stats()
        agents = self.tool_suggest_free_specialized_agents_suite()

        return {
            "title": "Voice Caddy Pro - Golf Intelligence & Zero-Cost Architecture Dossier",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "telemetry_state": telemetry,
            "advanced_stats_roadmap": stats["ambiti_statistici_raccomandati"],
            "agent_ecosystem_proposal": agents["suite_agenti_specializzati_gratuiti"]
        }

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Esegue il ciclo di analisi e aggiorna le metriche relative alla golf intelligence."""
        cycle_start = time.time()

        telemetry = self.execute_tool("evaluate_collected_golf_telemetry", db_path=self.db_path)
        stats = self.execute_tool("recommend_advanced_golf_stats")
        agents = self.execute_tool("suggest_free_specialized_agents_suite")

        # Emissione metriche per Prometheus
        self.emit_metric("voice_caddy_golf_rounds_evaluated_total", float(telemetry.get("total_rounds_analyzed", 0)))
        self.emit_metric("voice_caddy_golf_avg_score", float(telemetry.get("avg_score", 0.0)))
        self.emit_metric("voice_caddy_golf_avg_gir_percent", float(telemetry.get("avg_gir_pct", 0.0)))
        self.emit_metric("voice_caddy_golf_avg_fir_percent", float(telemetry.get("avg_fir_pct", 0.0)))

        self.state["last_run"] = cycle_start
        self.state["last_telemetry"] = telemetry
        self.state["cycle_count"] = int(self.state.get("cycle_count") or 0) + 1
        self.persist_state()

        return {
            "rounds_analyzed": telemetry.get("total_rounds_analyzed", 0),
            "recommended_stats_count": len(stats["ambiti_statistici_raccomandati"]),
            "proposed_agents_count": len(agents["suite_agenti_specializzati_gratuiti"]),
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000.0, 2)
        }
