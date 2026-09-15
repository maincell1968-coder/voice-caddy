from __future__ import annotations

import os
import json
from pathlib import Path
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI


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


def get_default_bag() -> List[ClubDetail]:
    return [
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


class UserProfile(BaseModel):
    player_name: str = Field(default="Giocatore Conero", description="Nome o identificativo del giocatore")
    handicap: float = Field(default=14.0, ge=0.0, le=54.0, description="Handicap ufficiale di gioco")
    category: PlayerCategory = Field(default=PlayerCategory.CATEGORY_2, description="Categoria del giocatore")
    preferred_ball: Optional[str] = Field(default="Titleist Pro V1", description="Marca/modello di palla preferita")
    clubs_in_bag: List[ClubDetail] = Field(default_factory=get_default_bag, description="Lista completa delle mazze presenti in sacca con dettagli e distanze")
    notes: Optional[str] = Field(default="", description="Note tattiche personali o obiettivi di stagione")

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
        try:
            p = Path(file_path)
            p.write_text(self.model_dump_json(indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    @classmethod
    def load_from_file(cls, file_path: str | Path = "user_profile.json") -> Optional[UserProfile]:
        p = Path(file_path)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return cls.model_validate(data)
            except Exception:
                return None
        return None


def parse_user_setup_transcript(setup_transcript_text: str, api_key: Optional[str] = None) -> UserProfile:
    """
    Parses a short audio voice setup memo into a structured UserProfile Pydantic object.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OpenAI API Key non trovata.")

    client = OpenAI(api_key=key)

    system_prompt = (
        "Sei un assistente specializzato per Voice Caddy. "
        "Analizza l'audio di presentazione dell'utente ed estrai: "
        "1. Handicap di gioco (0-54). "
        "2. Le mazze presenti in sacca con eventuale marca, modello e distanze in metri. "
        "3. Nome del giocatore se menzionato. "
        "Assegna la PlayerCategory corretta."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Audio di presentazione e setup dell'utente:\n\n{setup_transcript_text}"}
        ],
        response_format=UserProfile
    )
    profile: UserProfile = completion.choices[0].message.parsed
    profile.category = UserProfile.determine_category(profile.handicap)
    return profile
