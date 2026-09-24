# VOICE CADDY PRO - REGOLE DI SISTEMA & PROTEZIONE DATI

## 🛡️ REGOLA FONDAMENTALE: ZERO PERDITA DATI (SAFEVAULT POLICY)
È fatto espresso e assoluto divieto di cancellare, svuotare, resettare o sovrascrivere i file utente e di database durante qualsiasi modifica di codice, aggiornamento dell'interfaccia grafica o rilascio Git:
1. `voice_caddy.db` (database partite, scorecard, giri storici e statistiche).
2. `voice_caddy/data/profiles/*.json` (profili giocatore, handicap, sacca bastoni, marche, flessibilità shaft, distanze carry).
3. `voice_caddy/data/users.json` (account utenti, ruoli, configurazioni IA).
4. `voice_caddy/data/telegram_config.json` e `telegram_users.json` (accoppiamento bot Telegram).
5. `voice_caddy/data/coordinate_campi.xlsx` e `tactical_courses.json` (database coordinate GPS buche, tee, larghezze fairway, landing areas e centro green).

## 🧪 ISOLAMENTO DEI TEST AUTOMATIZZATI
Qualsiasi test automatizzato deve obbligatoriamente utilizzare directory temporanee (`tempfile`) o database in memoria (`:memory:`), senza mai puntare ai file operativi in produzione.

## ⛳ REGOLA DI SISTEMA: CALCOLO E REPORTISTICA DI GARA (LORDO E NETTO)
Nel riepilogo di gara, scorecard e report finale (PDF, HTML, Streamlit, Telegram) DEVE SEMPRE comparire sia il risultato **lordo** che il risultato **netto** (colpi e punti Stableford), applicando le formule e la struttura definita in `.agents/rules/tournament_scoring_rules.md`:
1. **Gare Stableford**: obbligo di indicare colpi lordi, colpi netti, punti Stableford netti e punti Stableford lordi.
2. **Gare a colpi / Stroke Play / Medal**: obbligo di indicare colpi lordi e colpi netti.
3. **Distribuzione handicap**: applicazione rigorosa dello Stroke Index della buca prima del calcolo dei punti Stableford (Regola 21.1 e Regola 3 R&A/USGA).
4. **Report finale**: inclusione di tutte le sezioni obbligatorie A-G (formula, metodo di calcolo, tabella risultati, anomalie/validazioni, classifica netta, classifica lorda, nota di conformità).

## 🏆 REGOLA AUREA: ANALISI TECNICA DI GARA DELL'IA (METODO DEL MAESTRO)
Ogni volta che l'IA analizza la prestazione di golf dell'utente (sia nel report riepilogativo della gara che nell'analisi specifica buca per buca), DEVE applicare rigorosamente le regole e le soglie definite in `.agents/rules/coach_analysis_rules.md`:
1. **Giudizio Tecnico Sempre Presente**: se il giocatore gioca bene, spiegare come, dove e perché e come consolidare; se gioca male, spiegare esattamente dove, quando, quanto e perché ha perso colpi.
2. **Divieto Assoluto di Banalità**: è tassativamente vietato esprimere commenti generici, sbrigativi o vaghi (es. "niente da dire, tutto ok", "devi migliorare il gioco corto", "serve più precisione").
3. **Formula Obbligatoria del Giudizio**:
   `Dato osservato → Interpretazione tecnica → Impatto sul risultato → Standard per categoria → Consiglio operativo`.
4. **Differenziazione per Categoria**:
   - *Prima Categoria (HCP 0–12)*: severità su dispersione, controllo profondità, miss side, gestione rischio.
   - *Seconda Categoria (HCP 13–24)*: solidità partenze, riduzione doppi bogey, approcci <100m.
   - *Terza Categoria (HCP 25–36+)*: palla in gioco, eliminazione penalità, avanzamento efficace.
5. **Template Obbligatori e Doppia Uscita**: rispetto della struttura a 6 sezioni buca per buca, del riepilogo a 14 punti con Top 3 priorità di allenamento misurabili, e generazione di doppia uscita (*Player Report* leggibile + *Technical Report* strutturato JSON).

