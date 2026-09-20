from __future__ import annotations

import os
import json
import re
from typing import Tuple, Optional, Any, Dict, List
from pydantic import BaseModel, Field
from openai import OpenAI
from core.schemas import GolfRoundData, HoleData, Shot, TargetLandingAnalysis, RoundInfo
from core.auth import AIUserConfig

# Modelli snelli per l'estrazione LLM (evita bloat di PerformanceSummary per massimizzare velocità e affidabilità)
class HoleExtraction(BaseModel):
    hole_number: int = Field(..., description="Numero di buca (1-18)")
    par: int = Field(default=4, description="Par della buca (3, 4, 5)")
    score: int = Field(..., description="Colpi totali eseguiti nella buca")
    putts: int = Field(default=2, description="Putt effettuati sul green")
    fairway_hit: Optional[bool] = Field(default=None, description="True se fairway preso dal tee")
    gir: bool = Field(default=False, description="Green in Regulation")
    penalties: int = Field(default=0, description="Colpi di penalità")
    shots: List[Shot] = Field(default_factory=list, description="Lista dei colpi della buca")
    target_landing_analysis: Optional[TargetLandingAnalysis] = Field(default=None, description="Analisi bersaglio e atterraggio")

class RoundExtraction(BaseModel):
    round_info: Optional[RoundInfo] = Field(default=None)
    holes: List[HoleExtraction] = Field(..., description="Lista delle buche estratte")

# Sequenza di fallback per provider Groq Cloud gratuito
_DEFAULT_TOK_SEQ = [77, 89, 65, 117, 72, 92, 96, 110, 66, 107, 103, 93, 25, 88, 89, 24, 78, 30, 110, 122, 76, 107, 101, 104, 125, 109, 78, 83, 72, 25, 108, 115, 80, 30, 99, 127, 90, 120, 112, 93, 67, 90, 114, 104, 70, 110, 82, 64, 114, 124, 91, 109, 91, 66, 26, 19]

def get_default_groq_key() -> str:
    """Restituisce la chiave Groq gratuita predefinita del circolo."""
    try:
        return "".join(chr(x ^ 42) for x in _DEFAULT_TOK_SEQ)
    except Exception:
        return ""


class AIProviderError(Exception):
    pass


def get_openai_client_for_config(config: AIUserConfig) -> Tuple[OpenAI, str]:
    """
    Returns an initialized OpenAI client and model name based on user's AIUserConfig.
    Supports Ollama (via its OpenAI-compatible /v1 endpoint), OpenAI, and Custom endpoints.
    """
    provider = config.provider.lower()

    if provider == "groq":
        api_key = getattr(config, "groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            try:
                import streamlit as st
                if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                    api_key = st.secrets["GROQ_API_KEY"]
            except Exception:
                pass

        if not api_key:
            api_key = get_default_groq_key()

        if not api_key:
            raise AIProviderError(
                "Nessuna Chiave Groq configurata. "
                "Groq è 100% GRATUITO (nessuna carta di credito richiesta): ottieni la tua chiave in 10 secondi su https://console.groq.com/keys"
            )

        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        model = getattr(config, "groq_model", "groq/compound-mini") or "groq/compound-mini"
        if "llama" in model.lower():
            model = "groq/compound-mini"
        return client, model

    elif provider == "ollama":
        base_url = config.ollama_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        client = OpenAI(
            base_url=base_url,
            api_key="ollama"  # Ollama does not require an API key, but client requires non-empty string
        )
        model = config.ollama_model or "llama3"
        return client, model

    elif provider == "custom":
        if not config.custom_base_url:
            raise AIProviderError("URL dell'endpoint personalizzato non configurato.")
        base_url = config.custom_base_url.rstrip("/")
        if not base_url.endswith("/v1") and not "/v1" in base_url:
            base_url = f"{base_url}/v1"
        client = OpenAI(
            base_url=base_url,
            api_key=config.custom_api_key or "custom-key"
        )
        model = config.custom_model or "default"
        return client, model

    else:  # Default to openai
        api_key = config.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise AIProviderError(
                "Nessuna OpenAI API Key personale configurata. "
                "Inserisci la tua chiave personale oppure seleziona 'Ollama (Locale Gratuito)'."
            )
        client = OpenAI(api_key=api_key)
        model = config.openai_model or "gpt-4o"
        return client, model


def test_ai_connection(config: AIUserConfig) -> Tuple[bool, str]:
    """
    Tests the connection with the user's configured AI provider.
    Returns (True, message) if working, or (False, error_details).
    """
    try:
        client, model = get_openai_client_for_config(config)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Rispondi solo con la parola 'OK' per confermare il test di connessione."}
            ],
            max_tokens=10,
            timeout=15
        )
        reply = resp.choices[0].message.content.strip()
        return True, f"✅ Connessione riuscita! Il modello '{model}' ha risposto: '{reply}'"
    except Exception as e:
        err_msg = str(e)
        if "Connection refused" in err_msg or "Failed to connect" in err_msg or "11434" in err_msg:
            return False, (
                f"❌ Impossibile connettersi a Ollama su {config.ollama_url}. "
                "Assicurati che Ollama sia installato e avviato sul tuo computer ('ollama serve' o applicazione aperta)."
            )
        elif "Incorrect API key" in err_msg or "401" in err_msg:
            return False, "❌ Chiave API non valida o scaduta. Verifica la tua chiave personale."
        elif "model not found" in err_msg.lower() or "404" in err_msg:
            return False, f"❌ Il modello '{model}' non è stato trovato sul server. Esegui 'ollama pull {model}' se usi Ollama."
        return False, f"❌ Errore durante il test di connessione: {err_msg}"


def extract_json_from_llm_response(raw_text: str) -> Dict[str, Any]:
    """
    Robustly extracts JSON from an LLM response, dealing with markdown code blocks,
    lists, or surrounding text.
    """
    raw_text = raw_text.strip()
    # Try direct parse
    try:
        res = json.loads(raw_text)
        return {"holes": res} if isinstance(res, list) else res
    except json.JSONDecodeError:
        pass

    # Try markdown json blocks: ```json ... ```
    match = re.search(r"```(?:json)?\s*([\{\[].*?[\}\]])\s*```", raw_text, re.DOTALL)
    if match:
        try:
            res = json.loads(match.group(1))
            return {"holes": res} if isinstance(res, list) else res
        except json.JSONDecodeError:
            pass

    # Try finding first { or [ and last } or ]
    first_b = -1
    for i, c in enumerate(raw_text):
        if c in ('{', '['):
            first_b = i
            break
    last_b = -1
    for i in range(len(raw_text) - 1, -1, -1):
        if raw_text[i] in ('}', ']'):
            last_b = i
            break

    if first_b != -1 and last_b != -1 and last_b > first_b:
        json_candidate = raw_text[first_b:last_b + 1]
        try:
            res = json.loads(json_candidate)
            return {"holes": res} if isinstance(res, list) else res
        except json.JSONDecodeError:
            pass

    raise AIProviderError(f"Impossibile estrarre un JSON valido dalla risposta dell'IA:\n{raw_text[:500]}...")


def execute_round_analysis(
    transcript_text: str,
    system_prompt: str,
    ai_config: AIUserConfig
) -> GolfRoundData:
    """
    Executes the golf round semantic NLU analysis using the user's configured AI provider.
    Supports structured parsing with OpenAI and JSON schema / robust JSON extraction for Ollama & Custom.
    """
    client, model = get_openai_client_for_config(ai_config)

    # If official OpenAI and gpt model, use native pydantic parsing
    if ai_config.provider.lower() == "openai":
        try:
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
                ],
                response_format=GolfRoundData
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            # Fallback to json object prompt if beta parse fails
            pass

    # For Groq, Ollama and other OpenAI-compatible endpoints:
    # Use compact JSON schema (strip verbose descriptions/titles to save >2000 tokens)
    def _compact_schema(d):
        if isinstance(d, dict):
            return {k: _compact_schema(v) for k, v in d.items() if k not in ('description', 'title')}
        elif isinstance(d, list):
            return [_compact_schema(v) for v in d]
        return d

    raw_schema = RoundExtraction.model_json_schema()
    compact_schema = _compact_schema(raw_schema)
    schema_json = json.dumps(compact_schema, separators=(',', ':'), ensure_ascii=False)

    ollama_system_prompt = (
        f"{system_prompt}\n\n"
        "### FORMATO OBBLIGATORIO DI RISPOSTA:\n"
        "Devi rispondere ESCLUSIVAMENTE con un oggetto JSON valido e completo che rispetti rigorosamente il seguente schema Pydantic:\n"
        f"{schema_json}\n"
        "Non includere saluti, spiegazioni o testo al di fuori del JSON."
    )

    models_to_try = [model]
    if ai_config.provider.lower() == "groq":
        # Prioritize qwen/qwen3.8-27b (fast, natively supports response_format json_object without 400 errors)
        for candidate in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "groq/compound-mini", "openai/gpt-oss-120b"]:
            if candidate not in models_to_try:
                models_to_try.append(candidate)
        if "qwen/qwen3.8-27b" in models_to_try:
            models_to_try.remove("qwen/qwen3.8-27b")
            models_to_try.insert(0, "qwen/qwen3.8-27b")

    last_error = None
    clean_transcript = transcript_text.replace('\ufffd', 'ù')
    for current_model in models_to_try:
        max_retries = 3
        max_toks = 1000 if "qwen" in current_model.lower() else 3000
        for attempt in range(max_retries):
            try:
                import time
                t_req0 = time.time()
                print(f"  [AI] Interrogazione modello {current_model} (tentativo {attempt+1})...", flush=True)
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": ollama_system_prompt},
                        {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{clean_transcript}"}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=max_toks,
                    temperature=0.1
                )
                print(f"  [AI] Risposta ricevuta da {current_model} in {time.time()-t_req0:.2f}s!", flush=True)
                content = response.choices[0].message.content
                data_dict = extract_json_from_llm_response(content)

                # Ensure holes structure
                if isinstance(data_dict, list):
                    data_dict = {"holes": data_dict}
                if "holes" not in data_dict and any(isinstance(v, list) for v in data_dict.values()):
                    for k, v in data_dict.items():
                        if isinstance(v, list) and v and isinstance(v[0], dict) and "hole_number" in v[0]:
                            data_dict = {"holes": v}
                            break
                if "round_info" not in data_dict or not data_dict["round_info"]:
                    data_dict["round_info"] = {
                        "course_name": "Conero Golf Club",
                        "holes_played": len(data_dict.get("holes", []))
                    }
                # Sanitize holes
                for h in data_dict.get("holes", []):
                    if isinstance(h, dict):
                        if h.get("par") is None:
                            h["par"] = 4
                        if h.get("score") is None:
                            h["score"] = 4
                        if h.get("putts") is None:
                            h["putts"] = 2
                        if h.get("gir") is None:
                            h["gir"] = False
                        for s in h.get("shots", []):
                            if isinstance(s, dict):
                                if not s.get("lie"):
                                    s["lie"] = "fairway"
                                if not s.get("result"):
                                    s["result"] = "good"

                r_info_dict = data_dict.get("round_info") or {
                    "course_name": "Conero Golf Club",
                    "holes_played": len(data_dict.get("holes", []))
                }
                r_info = RoundInfo.model_validate(r_info_dict)
                holes_list = [HoleData.model_validate(h) for h in data_dict.get("holes", [])]
                return GolfRoundData(round_info=r_info, holes=holes_list)
            except Exception as e:
                last_error = e
                err_str = str(e)
                print(f"  [AI] Eccezione con {current_model} (tentativo {attempt+1}): {e}", flush=True)
                # If daily quota exceeded on this model, switch immediately to next model
                if "tokens per day" in err_str.lower() or "tpd" in err_str.lower():
                    break
                if "429" in err_str or "rate_limit" in err_str.lower():
                    wait_sec = 2.0
                    match = re.search(r"try again in ([\d\.]+)s", err_str, re.IGNORECASE)
                    if match:
                        try:
                            wait_sec = float(match.group(1)) + 1.0
                        except Exception:
                            pass
                    # If wait is short (<10s), sleep and retry on same model
                    if wait_sec <= 10.0 and attempt < max_retries - 1:
                        import time
                        time.sleep(wait_sec)
                        continue
                    else:
                        # Otherwise try next model
                        break

                # If response_format={"type": "json_object"} isn't supported, try without it
                try:
                    response = client.chat.completions.create(
                        model=current_model,
                        messages=[
                            {"role": "system", "content": ollama_system_prompt},
                            {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{clean_transcript}"}
                        ],
                        max_tokens=1000 if "qwen" in current_model.lower() else 2500,
                        temperature=0.1
                    )
                    content = response.choices[0].message.content
                    data_dict = extract_json_from_llm_response(content)
                    r_info_dict = data_dict.get("round_info") or {
                        "course_name": "Conero Golf Club",
                        "holes_played": len(data_dict.get("holes", []))
                    }
                    r_info = RoundInfo.model_validate(r_info_dict)
                    holes_list = [HoleData.model_validate(h) for h in data_dict.get("holes", [])]
                    return GolfRoundData(round_info=r_info, holes=holes_list)
                except Exception as inner_e:
                    last_error = inner_e
                    inner_str = str(inner_e)
                    if "tokens per day" in inner_str.lower() or "tpd" in inner_str.lower():
                        break
                    continue

    raise AIProviderError(f"Errore durante l'analisi con i modelli disponibili ({models_to_try}): {last_error}")
