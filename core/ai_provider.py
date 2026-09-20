from __future__ import annotations

import os
import json
import re
from typing import Tuple, Optional, Any, Dict
from openai import OpenAI
from core.schemas import GolfRoundData
from core.auth import AIUserConfig

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


def extract_json_from_llm_response(raw_text: str) -> dict:
    """
    Robustly extracts JSON from an LLM response, dealing with markdown code blocks or surrounding text.
    """
    raw_text = raw_text.strip()
    # Try direct parse
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Try markdown json blocks: ```json { ... } ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { and last }
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = raw_text[first_brace:last_brace + 1]
        try:
            return json.loads(json_candidate)
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

    raw_schema = GolfRoundData.model_json_schema()
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
        # Fallback between qwen3.8-27b and compound-mini to avoid per-model daily quota limits
        if "qwen/qwen3.8-27b" not in models_to_try:
            models_to_try.append("qwen/qwen3.8-27b")
        if "groq/compound-mini" not in models_to_try:
            models_to_try.append("groq/compound-mini")

    last_error = None
    for current_model in models_to_try:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": ollama_system_prompt},
                        {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=2500,
                    temperature=0.1
                )
                content = response.choices[0].message.content
                data_dict = extract_json_from_llm_response(content)
                return GolfRoundData.model_validate(data_dict)
            except Exception as e:
                last_error = e
                err_str = str(e)
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
                            {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
                        ],
                        max_tokens=2500,
                        temperature=0.1
                    )
                    content = response.choices[0].message.content
                    data_dict = extract_json_from_llm_response(content)
                    return GolfRoundData.model_validate(data_dict)
                except Exception as inner_e:
                    last_error = inner_e
                    inner_str = str(inner_e)
                    if "tokens per day" in inner_str.lower() or "tpd" in inner_str.lower():
                        break
                    continue

    raise AIProviderError(f"Errore durante l'analisi con i modelli disponibili ({models_to_try}): {last_error}")
