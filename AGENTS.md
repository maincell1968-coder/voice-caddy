# VOICE CADDY PRO - REGOLE DI SISTEMA & PROTEZIONE DATI

## 🛡️ REGOLA FONDAMENTALE: ZERO PERDITA DATI (SAFEVAULT POLICY)
È fatto espresso e assoluto divieto di cancellare, svuotare, resettare o sovrascrivere i file utente e di database durante qualsiasi modifica di codice, aggiornamento dell'interfaccia grafica o rilascio Git:
1. `voice_caddy.db` (database partite, scorecard, giri storici e statistiche).
2. `voice_caddy/data/profiles/*.json` (profili giocatore, handicap, sacca bastoni, marche, flessibilità shaft, distanze carry).
3. `voice_caddy/data/users.json` (account utenti, ruoli, configurazioni IA).
4. `voice_caddy/data/telegram_config.json` e `telegram_users.json` (accoppiamento bot Telegram).

## 🧪 ISOLAMENTO DEI TEST AUTOMATIZZATI
Qualsiasi test automatizzato deve obbligatoriamente utilizzare directory temporanee (`tempfile`) o database in memoria (`:memory:`), senza mai puntare ai file operativi in produzione.

## ⛳ REGOLA DI SISTEMA: CALCOLO E REPORTISTICA DI GARA (LORDO E NETTO)
Nel riepilogo di gara, scorecard e report finale (PDF, HTML, Streamlit, Telegram) DEVE SEMPRE comparire sia il risultato **lordo** che il risultato **netto** (colpi e punti Stableford), applicando le formule e la struttura definita in `.agents/rules/tournament_scoring_rules.md`:
1. **Gare Stableford**: obbligo di indicare colpi lordi, colpi netti, punti Stableford netti e punti Stableford lordi.
2. **Gare a colpi / Stroke Play / Medal**: obbligo di indicare colpi lordi e colpi netti.
3. **Distribuzione handicap**: applicazione rigorosa dello Stroke Index della buca prima del calcolo dei punti Stableford (Regola 21.1 e Regola 3 R&A/USGA).
4. **Report finale**: inclusione di tutte le sezioni obbligatorie A-G (formula, metodo di calcolo, tabella risultati, anomalie/validazioni, classifica netta, classifica lorda, nota di conformità).

