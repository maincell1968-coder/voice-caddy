from __future__ import annotations

import os
import json
import re
from typing import Tuple, Optional, Any, Dict
from openai import OpenAI
from core.schemas import GolfRoundData
from core.auth import AIUserConfig


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
            raise AIProviderError(
                "Nessuna Chiave Groq configurata. "
                "Groq è 100% GRATUITO (nessuna carta di credito richiesta): ottieni la tua chiave in 10 secondi su https://console.groq.com/keys"
            )

        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        model = getattr(config, "groq_model", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile"
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

    # For Ollama and other OpenAI-compatible endpoints:
    # Append explicit JSON schema instructions
    schema_json = json.dumps(GolfRoundData.model_json_schema(), ensure_ascii=False)
    ollama_system_prompt = (
        f"{system_prompt}\n\n"
        "### FORMATO OBBLIGATORIO DI RISPOSTA:\n"
        "Devi rispondere ESCLUSIVAMENTE con un oggetto JSON valido e completo che rispetti rigorosamente il seguente schema Pydantic:\n"
        f"{schema_json}\n"
        "Non includere saluti, spiegazioni o testo al di fuori del JSON."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ollama_system_prompt},
                {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        data_dict = extract_json_from_llm_response(content)
        return GolfRoundData.model_validate(data_dict)
    except Exception as e:
        # If response_format={"type": "json_object"} isn't supported by old local server, try without response_format
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": ollama_system_prompt},
                    {"role": "user", "content": f"Ecco la trascrizione del giro da golf da analizzare:\n\n{transcript_text}"}
                ],
                temperature=0.1
            )
            content = response.choices[0].message.content
            data_dict = extract_json_from_llm_response(content)
            return GolfRoundData.model_validate(data_dict)
        except Exception as inner_e:
            raise AIProviderError(f"Errore durante l'analisi con il modello '{model}': {inner_e}")
