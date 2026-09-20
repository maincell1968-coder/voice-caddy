from __future__ import annotations

import os
import json
from pathlib import Path
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"


class PlayerCategory(str, Enum):
    CATEGORY_1 = "Prima Categoria (HCP 0 - 9)"
    CATEGORY_2 = "Seconda Categoria (HCP 10 - 18)"
    CATEGORY_3 = "Terza Categoria (HCP 19 - 54)"


class ShaftFlex(str, Enum):
    REGULAR = "Regular"
    STIFF = "Stiff"
    X_STIFF = "Extra Stiff (X-Stiff)"
    SENIOR = "Senior / Lite"
    LADIES = "Ladies"


class ClubDetail(BaseModel):
    club_name: str = Field(..., description="Nome della mazza (es. Driver, Legno 3, Ferro 7, Pitching Wedge)")
    brand: Optional[str] = Field(default="Generica", description="Marca del bastone (es. TaylorMade, Callaway, Titleist, Ping, Mizuno, Cobra, PXG)")
    model_type: Optional[str] = Field(default="", description="Modello o tipo bastone (es. Qi10, Stealth 2, Apex 21, T200, G430, CB/Blade)")
    shaft_flex: Optional[ShaftFlex] = Field(default=ShaftFlex.REGULAR, description="Flessibilità dello shaft")
    carry_meters: float = Field(..., description="Distanza media di volo/totale in metri")


CLUB_HIERARCHY_RANK = {
    "driver": 1,
    "legno 2": 2,
    "legno 3": 3,
    "legno 4": 4,
    "legno 5": 5,
    "legno 7": 6,
    "legno 9": 7,
    "legno": 8,
    "ibrido 2": 9,
    "ibrido 3": 10,
    "ibrido 4": 11,
    "ibrido 5": 12,
    "ibrido 6": 13,
    "ibrido": 14,
    "driving iron": 15,
    "ferro 1": 16,
    "ferro 2": 17,
    "ferro 3": 18,
    "ferro 4": 19,
    "ferro 5": 20,
    "ferro 6": 21,
    "ferro 7": 22,
    "ferro 8": 23,
    "ferro 9": 24,
    "pitching wedge": 25,
    "pw": 25,
    "gap wedge": 26,
    "gw": 26,
    "approach wedge": 27,
    "approach wedge (aw)": 27,
    "approach": 27,
    "aw": 27,
    "sand wedge": 28,
    "sw": 28,
    "lob wedge": 29,
    "lw": 29,
    "wedge": 30,
    "chipper": 31,
    "putter": 999,
    "putt": 999,
}


def sort_clubs_by_distance(clubs: List[ClubDetail]) -> List[ClubDetail]:
    """
    Allinea e ordina i bastoni della sacca in base alla distanza:
    dal Driver più lungo fino al Putter.
    
    Regole di ordinamento:
    1. Tutti i bastoni di distanza sono ordinati in ordine decrescente di carry_meters.
    2. A parità di distanza, viene rispettata la gerarchia canonica dei bastoni da golf.
    3. Il Putter è posizionato sempre come ultimo bastone della sacca.
    """
    def _rank(name: str) -> int:
        n = name.lower().strip()
        for key, r in CLUB_HIERARCHY_RANK.items():
            if key in n:
                return r
        return 50

    def _sort_key(c: ClubDetail):
        n = c.club_name.lower().strip()
        is_putt = 1 if ("putt" in n) else 0
        dist = float(c.carry_meters) if c.carry_meters is not None else 0.0
        rank = _rank(c.club_name)
        return (is_putt, -dist, rank, n)

    return sorted(clubs, key=_sort_key)


def get_default_bag() -> List[ClubDetail]:
    raw_bag = [
        ClubDetail(club_name="Driver", brand="TaylorMade", model_type="Qi10 / Stealth 2", shaft_flex=ShaftFlex.STIFF, carry_meters=220),
        ClubDetail(club_name="Legno 3", brand="Callaway", model_type="Paradym Ai Smoke", shaft_flex=ShaftFlex.STIFF, carry_meters=195),
        ClubDetail(club_name="Ibrido 4", brand="Ping", model_type="G430", shaft_flex=ShaftFlex.REGULAR, carry_meters=175),
        ClubDetail(club_name="Ferro 5", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=160),
        ClubDetail(club_name="Ferro 7", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=145),
        ClubDetail(club_name="Ferro 9", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=125),
        ClubDetail(club_name="Pitching Wedge", brand="Titleist", model_type="Vokey SM9", shaft_flex=ShaftFlex.STIFF, carry_meters=110),
        ClubDetail(club_name="Sand Wedge (56°)", brand="Titleist", model_type="Vokey SM9", shaft_flex=ShaftFlex.STIFF, carry_meters=85),
        ClubDetail(club_name="Putter", brand="Scotty Cameron", model_type="Phantom X", shaft_flex=ShaftFlex.REGULAR, carry_meters=0)
    ]
    return sort_clubs_by_distance(raw_bag)


class UserProfile(BaseModel):
    player_name: str = Field(default="Giocatore Conero", description="Nome o identificativo del giocatore")
    handicap: float = Field(default=14.0, ge=0.0, le=54.0, description="Handicap ufficiale di gioco")
    category: PlayerCategory = Field(default=PlayerCategory.CATEGORY_2, description="Categoria del giocatore")
    preferred_ball: Optional[str] = Field(default="Titleist Pro V1", description="Marca/modello di palla preferita")
    clubs_in_bag: List[ClubDetail] = Field(default_factory=get_default_bag, description="Lista completa delle mazze presenti in sacca con dettagli e distanze")
    caddy_tone: str = Field(default="professionale", description="Stile e tono del caddy: professionale, arrabbiato, spensierato, psicologo")
    notes: Optional[str] = Field(default="", description="Note tattiche personali o obiettivi di stagione")

    def sort_clubs(self) -> None:
        """Ordina i bastoni in sacca dal Driver più lungo fino al Putter."""
        self.clubs_in_bag = sort_clubs_by_distance(self.clubs_in_bag)

    def recommend_club_for_distance(self, distance_meters: float) -> Optional[ClubDetail]:
        """
        Consiglia il bastone ottimale dalla sacca in base alla distanza richiesta (in metri),
        escludendo il Putter e selezionando il bastone con carry più vicino.
        """
        if not self.clubs_in_bag:
            return None
        eligible_clubs = [
            c for c in self.clubs_in_bag
            if "putt" not in c.club_name.lower() and c.carry_meters and c.carry_meters > 0
        ]
        if not eligible_clubs:
            return None
        return min(eligible_clubs, key=lambda c: abs(c.carry_meters - distance_meters))

    @classmethod
    def determine_category(cls, hcp: float) -> PlayerCategory:
        if hcp <= 9.4:
            return PlayerCategory.CATEGORY_1
        elif hcp <= 18.4:
            return PlayerCategory.CATEGORY_2
        else:
            return PlayerCategory.CATEGORY_3

    def get_tone_system_instruction(self) -> str:
        cat = self.determine_category(self.handicap)
        if cat == PlayerCategory.CATEGORY_1:
            return (
                "ATTEGGIAMENTO E TONO DIALETTICO: PRIMA CATEGORIA (HCP BASSO / SINGLE DIGIT). "
                "Sii SEVERO, MOLTO ESIGENTE, DIRETTO E RIGOROSO. Tratta il giocatore come un professionista PGA. "
                "Non tollerare sbavature tattiche o errori di scelta del bastone. Punta alla massima precisione "
                "di prossimità alla bandiera e punisci severamente i colpi di penalità e gli errori di Course Management."
            )
        elif cat == PlayerCategory.CATEGORY_2:
            return (
                "ATTEGGIAMENTO E TONO DIALETTICO: SECONDA CATEGORIA (HCP MEDIO 10-18). "
                "Sii BILANCIATO, COSTRUTTIVO ED ANALITICO. Riconosci i colpi di qualità ma evidenzia con fermezza "
                "gli errori di strategia o le sbavature nel gioco corto che impediscono di scendere a single digit."
            )
        else:
            return (
                "ATTEGGIAMENTO E TONO DIALETTICO: TERZA CATEGORIA (HCP ALTO / PRINCIPIANTI 19-54). "
                "Sii MOLTO INCORAGGIANTE, DIDATTICO, PAZIENTE E SUPPORTIVO. Focalizzati sul rafforzare la fiducia, "
                "sull'eliminazione dei grandi errori (penalità/fuori limite) e sul divertimento in campo. "
                "Non essere mai inutilmente severo e spiega i concetti tecnici in modo semplice ed accessibile."
            )

    def format_club_distances_prompt_context(self) -> str:
        if not self.clubs_in_bag:
            return "Distanze e dettagli bastoni non specificati."
        lines = []
        for c in self.clubs_in_bag:
            brand_str = f" [{c.brand} {c.model_type}]" if c.brand else ""
            lines.append(f"- {c.club_name}{brand_str}: ~{int(c.carry_meters)} metri (Shaft: {c.shaft_flex.value if hasattr(c.shaft_flex, 'value') else c.shaft_flex})")
        return "Dettaglio Sacca e Distanze del Giocatore:\n" + "\n".join(lines)

    def save_to_file(self, file_path: str | Path = "user_profile.json") -> bool:
        self.sort_clubs()
        try:
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            # Backup preventivo prima di sovrascrivere
            if p.exists():
                try:
                    bak_path = p.with_suffix(".json.bak")
                    p.replace(bak_path) if not bak_path.exists() else None
                    # Copia di backup corrente
                    import shutil
                    shutil.copy2(p, p.with_suffix(".json.bak"))
                except Exception:
                    pass
            p.write_text(self.model_dump_json(indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    @classmethod
    def load_from_file(cls, file_path: str | Path = "user_profile.json") -> Optional[UserProfile]:
        p = Path(file_path)
        if not p.exists():
            return None

        raw_text = ""
        try:
            raw_text = p.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            profile = cls.model_validate(data)
            profile.sort_clubs()
            return profile
        except Exception as e:
            # Recupero di emergenza (Fault-Tolerant): estrai i dati anche se lo schema è parzialmente variato
            try:
                if raw_text:
                    data = json.loads(raw_text)
                    recovered_clubs = []
                    for c_raw in data.get("clubs_in_bag", []):
                        try:
                            recovered_clubs.append(ClubDetail.model_validate(c_raw))
                        except Exception:
                            # Tenta estrazione manuale
                            c_name = str(c_raw.get("club_name", "Bastone"))
                            c_carry = float(c_raw.get("carry_meters", 100.0))
                            recovered_clubs.append(ClubDetail(
                                club_name=c_name,
                                brand=str(c_raw.get("brand", "Generica")),
                                model_type=str(c_raw.get("model_type", "")),
                                carry_meters=c_carry
                            ))
                    
                    cat_val = data.get("category")
                    try:
                        valid_cat = PlayerCategory(cat_val)
                    except Exception:
                        valid_cat = cls.determine_category(float(data.get("handicap", 14.0)))

                    recovered_profile = cls(
                        player_name=str(data.get("player_name", "Giocatore")),
                        handicap=float(data.get("handicap", 14.0)),
                        category=valid_cat,
                        preferred_ball=data.get("preferred_ball", "Titleist Pro V1"),
                        clubs_in_bag=recovered_clubs or get_default_bag(),
                        notes=str(data.get("notes", ""))
                    )
                    recovered_profile.sort_clubs()
                    return recovered_profile
            except Exception:
                pass

            # Se proprio irrecuperabile, salva copia di backup del file danneggiato
            try:
                import time
                corrupt_copy = p.parent / f"{p.stem}_corrupted_{int(time.time())}.json.bak"
                p.rename(corrupt_copy)
            except Exception:
                pass
            return None

    def save_for_user(self, user_id: str) -> bool:
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        file_path = PROFILES_DIR / f"{user_id}.json"
        saved = self.save_to_file(file_path)
        try:
            from core.db import DatabaseManager
            DatabaseManager().save_user_profile(user_id, self.model_dump_json(indent=2))
        except Exception:
            pass
        return saved

    @classmethod
    def load_for_user(cls, user_id: str, default_name: str = "Giocatore") -> UserProfile:
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        file_path = PROFILES_DIR / f"{user_id}.json"
        bak_path = PROFILES_DIR / f"{user_id}.json.bak"

        # 1. Prova a caricare dal database protetto SQLite
        db_profile = None
        try:
            from core.db import DatabaseManager
            db_json = DatabaseManager().get_user_profile(user_id)
            if db_json:
                data = json.loads(db_json)
                db_profile = cls.model_validate(data)
                db_profile.sort_clubs()
        except Exception:
            pass

        # 2. Prova a caricare dal file principale JSON
        file_profile = cls.load_from_file(file_path)

        # 3. Se fallisce ma esiste una copia .bak, tenta il recupero dal backup
        if file_profile is None and bak_path.exists():
            file_profile = cls.load_from_file(bak_path)

        # 4. Sincronizzazione intelligente (Fault-Tolerant & Anti-Loss):
        # Se esistono sia DB che file, privilegia quello con la sacca più completa (più bastoni)
        if db_profile and file_profile:
            if len(db_profile.clubs_in_bag) > len(file_profile.clubs_in_bag):
                profile = db_profile
                profile.save_to_file(file_path)
            else:
                profile = file_profile
                try:
                    from core.db import DatabaseManager
                    DatabaseManager().save_user_profile(user_id, profile.model_dump_json(indent=2))
                except Exception:
                    pass
            return profile
        elif db_profile:
            db_profile.save_to_file(file_path)
            return db_profile
        elif file_profile:
            try:
                from core.db import DatabaseManager
                DatabaseManager().save_user_profile(user_id, file_profile.model_dump_json(indent=2))
            except Exception:
                pass
            return file_profile

        # 5. Solo se nessun file o record esiste, crea il profilo iniziale
        profile = cls(
            player_name=default_name,
            handicap=14.0,
            category=PlayerCategory.CATEGORY_2,
            preferred_ball="Titleist Pro V1",
            clubs_in_bag=get_default_bag()
        )
        profile.save_for_user(user_id)
        return profile


def parse_user_setup_transcript(setup_transcript_text: str, ai_config: Optional[Any] = None, api_key: Optional[str] = None) -> UserProfile:
    """
    Parses a short audio voice setup memo into a structured UserProfile Pydantic object.
    """
    from core.ai_provider import get_openai_client_for_config, extract_json_from_llm_response
    from core.auth import AIUserConfig

    if ai_config is None:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("Configurazione IA non trovata. Configura la tua IA personale.")
        config = AIUserConfig(provider="openai", openai_api_key=key)
    else:
        config = ai_config

    client, model = get_openai_client_for_config(config)

    system_prompt = (
        "Sei un assistente specializzato per Voice Caddy. "
        "Analizza l'audio di presentazione dell'utente ed estrai: "
        "1. Handicap di gioco (0-54). "
        "2. Le mazze presenti in sacca con eventuale marca, modello e distanze in metri. "
        "3. Nome del giocatore se menzionato. "
        "Assegna la PlayerCategory corretta."
    )

    if config.provider.lower() == "openai":
        try:
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Audio di presentazione e setup dell'utente:\n\n{setup_transcript_text}"}
                ],
                response_format=UserProfile
            )
            profile = completion.choices[0].message.parsed
            profile.category = UserProfile.determine_category(profile.handicap)
            profile.sort_clubs()
            return profile
        except Exception:
            pass

    # Ollama / Custom fallback
    schema_json = json.dumps(UserProfile.model_json_schema(), ensure_ascii=False)
    extended_prompt = f"{system_prompt}\n\nRispondi solo con un JSON conforme al seguente schema:\n{schema_json}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": extended_prompt},
            {"role": "user", "content": f"Audio di presentazione e setup dell'utente:\n\n{setup_transcript_text}"}
        ],
        temperature=0.1
    )
    raw = response.choices[0].message.content
    data_dict = extract_json_from_llm_response(raw)
    profile = UserProfile.model_validate(data_dict)
    profile.category = UserProfile.determine_category(profile.handicap)
    profile.sort_clubs()
    return profile
