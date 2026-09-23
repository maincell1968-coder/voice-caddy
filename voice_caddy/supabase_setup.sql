-- ==============================================================================
-- VOICE CADDY PRO — SETUP DATABASE SUPABASE (TABELLA GOLF_BAG & RLS)
-- ==============================================================================
--
-- ISTRUZIONI:
-- 1. Apri la tua Dashboard Supabase (https://supabase.com/dashboard)
-- 2. Seleziona il tuo progetto
-- 3. Nel menu laterale a sinistra, clicca su "SQL Editor"
-- 4. Crea una "New Query", incolla l'intero contenuto di questo file e clicca "Run"
-- ==============================================================================

-- 1. Abilita l'estensione pgcrypto per la generazione automatica di UUID
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2. Creazione della tabella persistente golf_bag
CREATE TABLE IF NOT EXISTS golf_bag (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bag_id text UNIQUE NOT NULL,
  clubs jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz DEFAULT now()
);

-- Commenti descrittivi sui campi
COMMENT ON TABLE golf_bag IS 'Archivio persistente della sacca bastoni di Voice Caddy Pro';
COMMENT ON COLUMN golf_bag.bag_id IS 'Identificativo univoco della sacca (default per utente primario)';
COMMENT ON COLUMN golf_bag.clubs IS 'Array JSON con tutti i bastoni, marche, shaft e carry in metri';
COMMENT ON COLUMN golf_bag.updated_at IS 'Data e ora dell ultimo salvataggio/aggiornamento';

-- 3. Abilitazione della protezione Row Level Security (RLS)
ALTER TABLE golf_bag ENABLE ROW LEVEL SECURITY;

-- 4. Politiche di Sicurezza (RLS Policies) per chiave 'anon' / 'authenticated'

-- Consenti la lettura dei dati della sacca
DROP POLICY IF EXISTS "Allow anon read golf_bag" ON golf_bag;
CREATE POLICY "Allow anon read golf_bag"
ON golf_bag FOR SELECT
TO anon, authenticated
USING (true);

-- Consenti l'inserimento di una nuova sacca
DROP POLICY IF EXISTS "Allow anon insert golf_bag" ON golf_bag;
CREATE POLICY "Allow anon insert golf_bag"
ON golf_bag FOR INSERT
TO anon, authenticated
WITH CHECK (true);

-- Consenti l'aggiornamento (upsert) della sacca esistente
DROP POLICY IF EXISTS "Allow anon update golf_bag" ON golf_bag;
CREATE POLICY "Allow anon update golf_bag"
ON golf_bag FOR UPDATE
TO anon, authenticated
USING (true)
WITH CHECK (true);

-- ==============================================================================
-- 5. TABELLA STORICO PARTITE (GOLF_ROUNDS) CON QUOTA E SALVATAGGIO CLOUD
-- ==============================================================================
CREATE TABLE IF NOT EXISTS golf_rounds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  round_key text UNIQUE NOT NULL,
  user_id text NOT NULL,
  group_name text DEFAULT 'strafatti',
  course_name text,
  date_played text,
  holes_played integer DEFAULT 18,
  total_score integer DEFAULT 0,
  total_putts integer DEFAULT 0,
  fairway_accuracy_pct real DEFAULT 0.0,
  gir_pct real DEFAULT 0.0,
  scrambling_pct real DEFAULT 0.0,
  penalty_strokes integer DEFAULT 0,
  primary_miss text DEFAULT '',
  round_data jsonb NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Indice per velocizzare le query storiche per giocatore
CREATE INDEX IF NOT EXISTS idx_golf_rounds_user ON golf_rounds (user_id, created_at DESC);

-- Abilitazione RLS su golf_rounds
ALTER TABLE golf_rounds ENABLE ROW LEVEL SECURITY;

-- Politiche RLS per golf_rounds
DROP POLICY IF EXISTS "Allow anon read golf_rounds" ON golf_rounds;
CREATE POLICY "Allow anon read golf_rounds"
ON golf_rounds FOR SELECT
TO anon, authenticated
USING (true);

DROP POLICY IF EXISTS "Allow anon insert golf_rounds" ON golf_rounds;
CREATE POLICY "Allow anon insert golf_rounds"
ON golf_rounds FOR INSERT
TO anon, authenticated
WITH CHECK (true);

DROP POLICY IF EXISTS "Allow anon update golf_rounds" ON golf_rounds;
CREATE POLICY "Allow anon update golf_rounds"
ON golf_rounds FOR UPDATE
TO anon, authenticated
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS "Allow anon delete golf_rounds" ON golf_rounds;
CREATE POLICY "Allow anon delete golf_rounds"
ON golf_rounds FOR DELETE
TO anon, authenticated
USING (true);
