from __future__ import annotations

import json
import random
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHRASES_FILE = PROJECT_ROOT / "data" / "caddy_phrases.json"


class CaddyTone(str, Enum):
    PROFESSIONALE = "professionale"
    ARRABBIATO = "arrabbiato"
    SPENSIERATO = "spensierato"
    PSICOLOGO = "psicologo"

    @property
    def display_name(self) -> str:
        names = {
            CaddyTone.PROFESSIONALE: "👔 Professionale (PGA Tour)",
            CaddyTone.ARRABBIATO: "🤬 Arrabbiato (Brontolone Romagnolo)",
            CaddyTone.SPENSIERATO: "🍻 Spensierato (Amico al Bar)",
            CaddyTone.PSICOLOGO: "🧘 Psicologo (Mental Coach Zen)",
        }
        return names.get(self, self.value.title())

    @property
    def short_label(self) -> str:
        labels = {
            CaddyTone.PROFESSIONALE: "👔 Professionale",
            CaddyTone.ARRABBIATO: "🤬 Arrabbiato",
            CaddyTone.SPENSIERATO: "🍻 Spensierato",
            CaddyTone.PSICOLOGO: "🧘 Psicologo",
        }
        return labels.get(self, self.value.title())

    @property
    def badge_color(self) -> str:
        colors = {
            CaddyTone.PROFESSIONALE: "#3B82F6",  # Blue
            CaddyTone.ARRABBIATO: "#EF4444",     # Red
            CaddyTone.SPENSIERATO: "#F59E0B",    # Amber
            CaddyTone.PSICOLOGO: "#10B981",      # Emerald
        }
        return colors.get(self, "#6B7280")

    @property
    def description(self) -> str:
        desc = {
            CaddyTone.PROFESSIONALE: "Asciutto, tecnico e disciplinato. Focus su distanze, pendenze, strategie conservative e course management puro.",
            CaddyTone.ARRABBIATO: "Brontolone romagnolo, ironico e sarcastico. Si lamenta della sacca che pesa e delle palline perse, ma tiene sinceramente al tuo score.",
            CaddyTone.SPENSIERATO: "L'amico simpatico del circolo. Zero ansia, celebra ogni bel colpo con una birra promessa e ridimensiona ogni disastro con un sorriso.",
            CaddyTone.PSICOLOGO: "Mental coach PGA. Respira, rilascia la tensione, 'il colpo prima non esiste più'. Focus assoluto sul qui ed ora.",
        }
        return desc.get(self, "")

    @property
    def sample_quote(self) -> str:
        quotes = {
            CaddyTone.PROFESSIONALE: "«Piano di gioco: fairway, centro green, due putt. Niente eroismi.»",
            CaddyTone.ARRABBIATO: "«Fairway largo 40 metri e tu hai scelto il cespuglio. Preparo il rastrello...»",
            CaddyTone.SPENSIERATO: "«Ogni birdie una birra, ogni bogey una birra di consolazione: vinciamo noi!»",
            CaddyTone.PSICOLOGO: "«Un respiro profondo. Il colpo precedente è concluso: ora c'è solo questa palla.»",
        }
        return quotes.get(self, "")


class CaddyPersonalityEngine:
    """
    Motore di Gestione Personalità e Reattività del Caddie.
    1. Fornisce battute reattive istantanee anti-ripetizione da caddy_phrases.json.
    2. Genera il System Prompt per Cloud LLM specializzato sui 4 archetipi.
    3. Esegue la chat conversazionale con contesto reale (sacca bastoni, handicap, campo).
    """

    _instance: Optional[CaddyPersonalityEngine] = None

    def __init__(self, phrases_path: Optional[Path] = None):
        self.phrases_path = phrases_path or PHRASES_FILE
        self.phrases_catalog: Dict[str, Dict[str, List[str]]] = {}
        self._used_history: Dict[str, Dict[str, Set[str]]] = {}
        self.load_catalog()

    @classmethod
    def get_instance(cls) -> CaddyPersonalityEngine:
        if cls._instance is None:
            cls._instance = CaddyPersonalityEngine()
        return cls._instance

    def load_catalog(self) -> None:
        """Carica il catalogo delle frasi da JSON con gestione errori."""
        if self.phrases_path.is_file():
            try:
                with open(self.phrases_path, "r", encoding="utf-8") as f:
                    self.phrases_catalog = json.load(f)
            except Exception:
                self.phrases_catalog = {}
        else:
            self.phrases_catalog = {}

    def get_phrase(
        self,
        situation: str,
        tone: str | CaddyTone = CaddyTone.PROFESSIONALE,
        session_id: str = "default",
        **ctx: Any
    ) -> str:
        """
        Recupera una battuta casuale non ancora utilizzata nella sessione corrente,
        compilando i segnaposto dinamici {distanza}, {ferro}, {buca}, ecc.
        """
        tone_str = tone.value if isinstance(tone, CaddyTone) else str(tone).lower().strip()
        sit_str = str(situation).upper().strip()

        situations_dict = self.phrases_catalog.get(sit_str, {})
        pool = situations_dict.get(tone_str, [])

        if not pool:
            # Fallback generico
            return self._generic_fallback(sit_str, tone_str, **ctx)

        sess_dict = self._used_history.setdefault(session_id, {})
        used = sess_dict.setdefault(f"{sit_str}_{tone_str}", set())

        available = [p for p in pool if p not in used]
        if not available:
            # Tutte le battute del pool sono state usate: reset della memoria per questa situazione
            used.clear()
            available = pool

        chosen = random.choice(available)
        used.add(chosen)

        return self._format_phrase(chosen, **ctx)

    def _format_phrase(self, template: str, **ctx: Any) -> str:
        """Sostituisce i segnaposto in modo tollerante agli errori."""
        defaults = {
            "buca": "1",
            "par": "4",
            "distanza": "150",
            "distanza_eff": "150",
            "distanza_centro": "155",
            "carry": "140",
            "ferro": "Ferro 7",
            "score": "2",
            "score_totale": "78",
            "buca_next": "prossima",
            "nome": "Campione"
        }
        safe_ctx = {**defaults, **{k: str(v) for k, v in ctx.items() if v is not None}}
        try:
            return template.format(**safe_ctx)
        except Exception:
            # Fallback safe replace se mancano placeholder sconosciuti
            res = template
            for k, v in safe_ctx.items():
                res = res.replace(f"{{{k}}}", str(v))
            return res

    def _generic_fallback(self, situation: str, tone_str: str, **ctx: Any) -> str:
        """Frase di riserva se il catalogo non contiene la specifica combinazione."""
        buca = ctx.get("buca", "1")
        if tone_str == "arrabbiato":
            return f"Buca {buca}. Concentrati e non farmi camminare per niente."
        elif tone_str == "spensierato":
            return f"Buca {buca}! Sorriso, swing sciolto e via."
        elif tone_str == "psicologo":
            return f"Buca {buca}. Respira, sii presente nel gesto."
        return f"Buca {buca}. Routine consolidata e centro fairway."

    def build_system_prompt(
        self,
        tone: str | CaddyTone,
        user_profile: Optional[Any] = None,
        active_course: Optional[Any] = None,
        current_hole: Optional[int] = None,
        current_score: Optional[int] = None
    ) -> str:
        """
        Genera il System Prompt personalizzato per il Cloud LLM (Groq, OpenAI, Ollama),
        calibrato esattamente sull'archetipo scelto dal giocatore e arricchito con la sacca reale.
        """
        tone_str = tone.value if isinstance(tone, CaddyTone) else str(tone).lower().strip()

        tone_instructions = {
            "professionale": (
                "SEI: Un caddie professionista del PGA Tour di altissimo livello.\n"
                "TONO: Estremamente tecnico, asciutto, lucido, rigoroso ed elegante. Niente battute dispersive.\n"
                "OBIETTIVO: Massimizzare il punteggio, minimizzare i rischi, calcolare dispersioni, vento, dislivelli orografici e target sicuri sul green.\n"
                "REGOLA D'ORO: Consiglia sempre il bastone che offre il minor rischio di penalità."
            ),
            "arrabbiato": (
                "SEI: Un brontolone romagnolo verace, caddie esperto ma stanco di portare sacche pesanti a giocatori che non ragionano.\n"
                "TONO: Molto ironico, sarcastico, comico, pungente. Ti lamenti sempre della sacca, delle palline perse nel lago che costano 5 euro, "
                "dei fairway larghi 40 metri mancati per fare 'il fenomeno'. MA ATTENZIONE: non sei MAI offensivo o volgare; sei un amico "
                "che borbotta come nei film comici italiani perché in fondo ci tiene allo score del giocatore.\n"
                "OBIETTIVO: Dare ottimi consigli tecnici ma conditi con umorismo sarcastico romagnolo."
            ),
            "spensierato": (
                "SEI: L'amico perfetto del circolo da golf, quello con cui si va a giocare per farsi due risate e poi fermarsi alla buca 19 a bere una birra.\n"
                "TONO: Allegro, positivo, scanzonato, incoraggiante, zero ansia da prestazione. Ridimensiona ogni disastro ('il campo ti voleva bene e voleva farti esplorare la natura'). "
                "Celebra ogni bel colpo con entusiasmo ('birra pagata!').\n"
                "OBIETTIVO: Rendere il giro di golf un piacere rilassante e spensierato."
            ),
            "psicologo": (
                "SEI: Un Mental Coach sportivo certificato specializzato nel gioco mentale del golf (stile Zen / Inner Game of Golf).\n"
                "TONO: Calmo, riflessivo, empatico, focalizzato sul respiro, sulla postura e sull'accettazione ('il colpo precedente non esiste più').\n"
                "OBIETTIVO: Gestire la frustrazione dopo un errore, evitare spirali negative dopo un doppio bogey, invitare alla visualizzazione della traiettoria e al ritmo corporeo.\n"
                "REGOLA D'ORO: 'Un colpo alla volta, la presenza è tutto'."
            )
        }

        persona_guide = tone_instructions.get(tone_str, tone_instructions["professionale"])

        # Contesto Giocatore & Sacca
        profile_context = ""
        if user_profile:
            name = getattr(user_profile, "player_name", "Giocatore")
            hcp = getattr(user_profile, "handicap", 14.0)
            ball = getattr(user_profile, "preferred_ball", "Titleist Pro V1")
            bag_details = ""
            if hasattr(user_profile, "format_club_distances_prompt_context"):
                bag_details = user_profile.format_club_distances_prompt_context()
            elif hasattr(user_profile, "clubs_in_bag"):
                clubs_str = ", ".join([f"{c.club_name} ({int(c.carry_meters)}m)" for c in user_profile.clubs_in_bag if c.carry_meters])
                bag_details = f"Sacca: {clubs_str}"

            profile_context = f"""
DATI GIOCATORE:
- Nome: {name}
- Handicap: {hcp}
- Palla preferita: {ball}
{bag_details}
"""

        # Contesto Campo Attivo
        course_context = ""
        if active_course:
            c_name = getattr(active_course, "name", "Campo da Golf")
            holes_info = getattr(active_course, "holes_count", 18)
            course_context = f"\nCAMPO ATTIVO: {c_name} ({holes_info} buche)."
            if current_hole:
                hole_obj = active_course.get_hole(current_hole) if hasattr(active_course, "get_hole") else None
                if hole_obj:
                    course_context += f" Buca attuale: #{current_hole} (Par {hole_obj.par}, {hole_obj.distance_meters}m, {hole_obj.slope_elevation_profile})."

        prompt = f"""Tu sei VOICE CADDY, l'assistente IA ufficiale di caddie per il golfista.
Rispondi SEMPRE in italiano, in modo conciso, realistico, competente e rigorosamente fedele alla personalità assegnata.

{persona_guide}
{profile_context}
{course_context}

LINEE GUIDA CHAT:
1. Mantieni sempre la voce e il carattere del tuo stile in ogni singola frase.
2. Fai sempre riferimento ai bastoni reali presenti nella sacca del giocatore e alle sue reali distanze in metri.
3. Se l'utente chiede quale bastone tirare, calcola dislivello, ostacoli e suggerisci il bastone più adatto dalla sua sacca.
4. Sii sintetico e brillante: massimo 2-3 frasi o un breve elenco tattico, senza dilungarti eccessivamente.
"""
        return prompt.strip()

    def chat_with_caddy(
        self,
        message: str,
        tone: str | CaddyTone,
        history: List[Dict[str, str]],
        user_profile: Any,
        ai_config: Any,
        active_course: Optional[Any] = None,
        current_hole: Optional[int] = None
    ) -> str:
        """
        Esegue la chiamata al Cloud LLM (Groq, OpenAI, Ollama) applicando la personalità scelta.
        """
        try:
            from core.ai_provider import get_openai_client_for_config, AIProviderError
        except ImportError:
            from voice_caddy.core.ai_provider import get_openai_client_for_config, AIProviderError

        system_prompt = self.build_system_prompt(
            tone=tone,
            user_profile=user_profile,
            active_course=active_course,
            current_hole=current_hole
        )

        messages = [{"role": "system", "content": system_prompt}]
        for h in history[-8:]:  # Ultimi 8 messaggi di contesto per efficienza
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        try:
            client, model = get_openai_client_for_config(ai_config)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.75,
                max_tokens=400
            )
            return response.choices[0].message.content.strip()
        except AIProviderError as e:
            return f"⚠️ Errore AI Caddie: {e}"
        except Exception as e:
            return f"⚠️ Connessione con il Cloud Caddie temporaneamente non disponibile ({e})."
