# VOICE CADDY PRO — REGOLE DI SISTEMA: CALCOLO E REPORTISTICA DI GARA (LORDO E NETTO)

Questo documento definisce le regole e le procedure vincolanti che ogni agente AI, modulo software o generatore di report di Voice Caddy DEVE applicare per il calcolo e la visualizzazione dei punteggi di gara, distinguendo tra gare **Stableford** e gare **a colpi / Stroke Play / Medal**.

---

## 1. Riferimenti Regolamentari Ufficiali
- **Regola 21.1 delle Regole del Golf R&A / USGA**: La Stableford è una forma di Stroke Play in cui il punteggio è espresso in punti assegnati per ciascuna buca. Nelle gare con handicap, i colpi di handicap spettanti devono essere applicati al punteggio registrato per la buca PRIMA del calcolo dei punti Stableford.
- **Regola 3 delle Regole del Golf R&A / USGA**: Il punteggio netto di una buca o del giro equivale al punteggio lordo rettificato dai colpi di handicap spettanti al giocatore.
- **World Handicap System (WHS) / Federazione Italiana Golf (FIG)**: Il Playing Handicap (Handicap di Gioco) determina i colpi ricevuti dal giocatore (o, in caso di handicap plus, i colpi da aggiungere).

---

## 2. Definizioni Operative e Formule di Calcolo

### A. Colpi Lordi (Gross Score)
- **Per una buca**: Numero reale di colpi eseguiti dal giocatore (inclusi putt ed eventuali penalità).
- **Per il giro**: Somma dei colpi effettivi di tutte le buche completate e valide:
  $$\text{colpi\_lordi\_totale} = \sum \text{colpi\_lordi\_buca}$$

### B. Colpi Netti (Net Score)
- Colpi lordi rettificati dai colpi di handicap ricevuti.
- **Per una buca**:
  $$\text{colpi\_netto\_buca} = \text{colpi\_lordi\_buca} - \text{colpi\_hcp\_buca}$$
- **Per il giro**:
  $$\text{colpi\_netto\_totale} = \text{colpi\_lordi\_totale} - \text{playing\_handicap}$$
- **In caso di Playing Handicap Plus (negativo)**:
  $$\text{colpi\_netto\_totale} = \text{colpi\_lordi\_totale} + |\text{playing\_handicap}|$$

### C. Distribuzione dei Colpi di Handicap (Stroke Index)
- I colpi di handicap devono essere distribuiti sulle buche secondo lo Stroke Index (SI) / Handicap Stroke Index del percorso.
- Se il giocatore riceve $N$ colpi ($N \le 18$): assegna 1 colpo alle buche con $\text{Stroke Index} \le N$.
- Se $N > 18$: assegna 1 colpo a tutte le 18 buche; assegna il secondo colpo alle buche con $\text{Stroke Index} \le (N - 18)$; prosegui con lo stesso criterio per ulteriori colpi ($N > 36$).
- Se il percorso è su 9 buche: la distribuzione avviene in proporzione (modulo 9 o secondo tabella specifica del circolo).
- Se l'handicap è Plus: i colpi vengono sottratti a partire dalle buche con Stroke Index più alto (buche più facili).

### D. Calcolo Punti Stableford Netti
- Per ogni buca, calcola prima il punteggio netto:
  $$\text{colpi\_netto\_buca} = \text{colpi\_lordi\_buca} - \text{colpi\_hcp\_buca}$$
- Confronta il punteggio netto con il Par della buca:
  - Più di 1 colpo sopra il par netto (Doppio bogey netto o peggio): **0 punti**
  - 1 colpo sopra il par netto (Bogey netto): **1 punto**
  - Par netto: **2 punti**
  - 1 colpo sotto il par netto (Birdie netto): **3 punti**
  - 2 colpi sotto il par netto (Eagle netto): **4 punti**
  - 3 colpi sotto il par netto (Albatross netto): **5 punti**
  - 4 colpi sotto il par netto: **6 punti**
- **Formula sintetica**:
  $$\text{punti\_stableford\_netto\_buca} = \max(0, 2 + \text{par\_buca} - \text{colpi\_netto\_buca})$$

### E. Calcolo Punti Stableford Lordi
- Non applicare i colpi di handicap; confronta direttamente i colpi lordi effettivi con il Par della buca:
  $$\text{punti\_stableford\_lordo\_buca} = \max(0, 2 + \text{par\_buca} - \text{colpi\_lordi\_buca})$$

### F. Totali Stableford del Giro
$$\text{punti\_stableford\_netto\_totale} = \sum \text{punti\_stableford\_netto\_buca}$$
$$\text{punti\_stableford\_lordo\_totale} = \sum \text{punti\_stableford\_lordo\_buca}$$

---

## 3. Regola Obbligatoria per i Report e i Fogli di Riepilogo

Nel report finale (PDF, HTML, Dashboard Streamlit, Notifiche Telegram) è **fatto obbligo assoluto** di includere sempre sia il risultato **lordo** che il risultato **netto**:

1. **Nelle gare Stableford**:
   - Punti Stableford netti
   - Punti Stableford lordi
   - Colpi netti
   - Colpi lordi
   - Handicap Index, Course Handicap e Playing Handicap applicato (es. 95% WHS).

2. **Nelle gare a colpi / Stroke Play / Medal**:
   - Colpi netti
   - Colpi lordi
   - Handicap Index, Course Handicap e Playing Handicap applicato (100%).

3. **Dati non omettibili**:
   - Se un dato non è calcolabile per mancanza di informazioni, indicare chiaramente:
     `"Dato non calcolabile: mancano [specificare dati mancanti]"`.

---

## 4. Struttura Obbligatoria del Riepilogo di Gara (Sezioni A - G)

Ogni report completo generato da Voice Caddy deve contenere:
- **A. Riepilogo della formula di gara** (Stableford o Stroke Play / Medal).
- **B. Metodo di calcolo utilizzato** (esplicitando le regole R&A/WHS e le formule applicate).
- **C. Tabella risultati ufficiale**:
  - *Per Stableford*:
    `| Giocatore | HCP | Playing HCP | Colpi lordi | Colpi netti | Punti Stableford lordi | Punti Stableford netti | Posizione lorda | Posizione netta | Note |`
  - *Per Gara a Colpi*:
    `| Giocatore | HCP | Playing HCP | Colpi lordi | Colpi netti | Posizione lorda | Posizione netta | Note |`
- **D. Eventuali anomalie o dati mancanti** (validazione preliminare di tipo_gara, par, SI, colpi lordi, playing hcp).
- **E. Classifica netta**:
  - Stableford: ordinata per punti Stableford netti decrescenti.
  - Stroke Play: ordinata per colpi netti crescenti.
- **F. Classifica lorda**:
  - Stableford: ordinata per punti Stableford lordi decrescenti.
  - Stroke Play: ordinata per colpi lordi crescenti.
- **G. Nota finale di conformità**:
  - Dicitura esplicita che certifica la presenza e conformità di colpi netti, lordi e punti Stableford secondo la formula di gara.
