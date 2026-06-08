import os
import time
import random
from typing_extensions import TypedDict

from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import logging
load_dotenv(override=True)
import tiktoken

# Lazy initialization
llm_registry = None

logger = logging.getLogger()

def log_stream(text):
    for handler in logger.handlers:
        stream = getattr(handler, "stream", None)
        if stream:
            stream.write(text)
            stream.flush()

def _init_llm_registry():
    global llm_registry
    if llm_registry is not None:
        return

    llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if llm_provider == "gemini":
        model_names = os.getenv("GEMINI_MODELS", "").split(",")
        model_temps = [float(x) for x in os.getenv("GEMINI_TEMPERATURES", "").split(",")]
    else:
        model_names = os.getenv("OLLAMA_NAMES", "").split(",")
        model_temps = [float(x) for x in os.getenv("OLLAMA_TEMPERATURES", "").split(",")]


    # Safety: ensure lengths match
    if len(model_names) != len(model_temps):
        raise ValueError("MODELS and TEMPERATURES must have the same length.")

    # Build registry based on provider
    if llm_provider == "gemini":
        llm_registry = {
            name: ChatGoogleGenerativeAI(model=name, temperature=temperature, max_retries=5, timeout=1800)
            for name, temperature in zip(model_names, model_temps)
        }
    else:
        llm_registry = {
            name: ChatOllama(model=name, temperature=temperature)
            for name, temperature in zip(model_names, model_temps)
        }

    for llm in llm_registry.values():
        logging.info(f"Initialized model {llm.model} with temperature {llm.temperature}")

def get_llm_for_agent(agent):
    _init_llm_registry()
    model_name = agent.name
    return llm_registry[model_name]

class Message(TypedDict):
    role: str
    content: str

def chat_with_model(
    agent,
    history: list[Message],
    verbose: bool = False,
) -> str:
    llm = get_llm_for_agent(agent)

    max_attempts = 5
    base_delay = 5  # seconds
    for attempt in range(max_attempts):
        try:
            t0 = time.time()
            ai_msg = llm.invoke(history)
            dt = time.time() - t0
            break
        except Exception as e:
            if attempt < max_attempts - 1 and ("504" in str(e) or "DeadlineExceeded" in str(e) or "deadline" in str(e).lower()):
                delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
                logging.warning(f"DeadlineExceeded on attempt {attempt + 1}, retrying in {delay:.1f}s... ({e})")
                time.sleep(delay)
            else:
                raise

    res_text = ai_msg.content if isinstance(ai_msg.content, str) else "".join(
        part["text"] if isinstance(part, dict) else str(part) for part in ai_msg.content
    )

    input_tokens = ai_msg.usage_metadata.get("input_tokens")
    output_tokens = ai_msg.usage_metadata.get("output_tokens")
    agent.input_tokens += input_tokens
    agent.output_tokens += output_tokens
    agent.elapsed_time_seconds += dt

    if verbose:
        logging.info(f"LLM call took {dt:.2f} seconds")
        logging.info(f"LLM call took {input_tokens} input tokens")
        logging.info(f"LLM call took {output_tokens} output tokens")
        logging.info(f"Executed LLM for {agent.name}")

    return res_text

def count_tokens(messages, model):
    enc = tiktoken.encoding_for_model(model)
    tokens = 0
    for m in messages:
        tokens += len(enc.encode(m.content))
    return tokens