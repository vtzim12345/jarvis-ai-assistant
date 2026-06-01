"""
JARVIS v6
=========
Correções:
  - Voz ANTONIO (pt-BR masculina nativa do Windows 11)
  - Fallback ordenado: Antonio > Daniel > David > Mark > qualquer masculina
  - Memória: save_mem corrigido, fatos persistem corretamente
  - Clima: usa requests + wttr.in (sem Selenium, sem cookies, sem falha)
  - Bilíngue: detecta inglês automático, responde no idioma do usuário
  - Ensina inglês quando pedido
  - Traduz em tempo real
  - Abrir qualquer app/site por voz: parser melhorado + subprocess.Popen com shell
  - Pesquisa web via DuckDuckGo scraping (mais estável que Google)
  - Wake word funciona em inglês também ("hey jarvis")
"""

import os, sys, json, time, base64, threading
import subprocess, platform, webbrowser, random
import datetime, queue, logging, io, re
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

try:
    import openai; OPENAI_OK = True
except Exception:
    OPENAI_OK = False

try:
    from groq import Groq; GROQ_OK = True
except Exception:
    GROQ_OK = False

try:
    import speech_recognition as sr; SR_OK = True
except Exception:
    SR_OK = False

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except Exception:
    SELENIUM_OK = False

try:
    import cv2; CV2_OK = True
except Exception:
    CV2_OK = False

try:
    from PIL import ImageGrab; PIL_OK = True
except Exception:
    PIL_OK = False

try:
    import numpy as np; NP_OK = True
except Exception:
    NP_OK = False

try:
    import psutil; PSUTIL_OK = True
except Exception:
    PSUTIL_OK = False

try:
    import sounddevice as sd; SD_OK = True
except Exception:
    SD_OK = False

try:
    import requests as req_lib; REQ_OK = True
except Exception:
    REQ_OK = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [JARVIS] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("JARVIS")

# ══════════════════════════════════════
# CAMINHOS
# ══════════════════════════════════════
BACKEND_DIR  = Path(__file__).parent
PROJECT_DIR  = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
CONFIG_FILE  = BACKEND_DIR / "config.json"
MEMORY_FILE  = BACKEND_DIR / "jarvis_memory.json"

# ══════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════
DEFAULTS = {
    "openai_api_key":       "",
    "groq_api_key":         "",
    "wake_word":            "jarvis",
    "city":                 "Piracicaba",
    "home_assistant_url":   "",
    "home_assistant_token": "",
    "speech_rate":          1,
    "volume":               100,
    "intro_music":          "random",
    "owner":                "Senhor Victor",
    "language":             "pt-BR",   # pt-BR ou en-US
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULTS.items():
            cfg.setdefault(k, v)
        return cfg
    cfg = DEFAULTS.copy()
    save_config(cfg)
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

CFG = load_config()

# ══════════════════════════════════════
# MEMÓRIA (2 meses)
# ══════════════════════════════════════
def load_mem():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Garante estrutura mínima
            data.setdefault("conversations", [])
            data.setdefault("facts", {})
            data.setdefault("plans", [])
            return data
        except Exception as e:
            log.error(f"load_mem: {e}")
    return {"conversations": [], "facts": {}, "plans": []}

def save_mem():
    """Salva memória com limpeza de itens com mais de 60 dias."""
    cutoff = (datetime.datetime.now() -
              datetime.timedelta(days=60)).isoformat()
    MEM["conversations"] = [
        c for c in MEM.get("conversations", [])
        if c.get("ts", "9999") >= cutoff
    ]
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(MEM, f, ensure_ascii=False, indent=2)
        log.info(f"Memória salva: {len(MEM['conversations'])} conv, "
                 f"{len(MEM['facts'])} fatos")
    except Exception as e:
        log.error(f"save_mem ERRO: {e}")

MEM = load_mem()

# ══════════════════════════════════════
# ESTADO
# ══════════════════════════════════════
ST = {
    "active":      False,
    "listening":   False,
    "speaking":    False,
    "thinking":    False,
    "muted":       False,
    "camera_on":   False,
    "initialized": False,
    "music_on":    False,
    "lang":        "pt",   # pt | en
}

# ══════════════════════════════════════
# FLASK + SOCKETIO
# ══════════════════════════════════════
app = Flask(__name__,
            static_folder=str(FRONTEND_DIR),
            static_url_path="")
CORS(app)
sio = SocketIO(app, cors_allowed_origins="*",
               async_mode="threading",
               logger=False, engineio_logger=False)

# ══════════════════════════════════════
# TTS — VOZ ANTONIO (pt-BR masculina)
# ══════════════════════════════════════
_tts_q     = queue.Queue()
_tts_ready = threading.Event()
_sapi      = None

# Ordem de preferência de vozes masculinas
VOICE_PRIORITY = [
    "antonio",   # Windows 11 pt-BR masculina — PRIMEIRA opção
    "daniel",    # pt-BR alternativa
    "pedro",
    "carlos",
    "david",     # en-US masculina Microsoft
    "mark",
    "george",
    "richard",
    "james",
    "paul",
]
VOICE_BLOCK = ["maria", "luciana", "zira", "hazel",
               "susan", "helen", "female", "feminina", "ana"]

def _init_sapi():
    global _sapi
    try:
        import win32com.client
        _sapi = win32com.client.Dispatch("SAPI.SpVoice")
        voices = _sapi.GetVoices()

        log.info(f"Vozes SAPI disponíveis ({voices.Count}):")
        all_voices = []
        for i in range(voices.Count):
            v    = voices.Item(i)
            desc = v.GetDescription()
            log.info(f"  [{i}] {desc}")
            all_voices.append((desc.lower(), v))

        chosen = None

        # 1) Tenta por prioridade de nome
        for pref in VOICE_PRIORITY:
            for desc_l, v in all_voices:
                if pref in desc_l and not any(b in desc_l for b in VOICE_BLOCK):
                    chosen = v
                    log.info(f"Voz escolhida (prioridade '{pref}'): {v.GetDescription()}")
                    break
            if chosen:
                break

        # 2) Qualquer masculina que não seja bloqueada
        if not chosen:
            for desc_l, v in all_voices:
                if not any(b in desc_l for b in VOICE_BLOCK):
                    chosen = v
                    log.info(f"Voz escolhida (fallback masculina): {v.GetDescription()}")
                    break

        # 3) Primeira disponível
        if not chosen and all_voices:
            chosen = all_voices[0][1]
            log.info(f"Voz escolhida (fallback geral): {all_voices[0][0]}")

        if chosen:
            _sapi.Voice = chosen

        _sapi.Rate   = int(CFG.get("speech_rate", 1))
        _sapi.Volume = int(CFG.get("volume", 100))
        return True
    except Exception as e:
        log.error(f"SAPI init: {e}")
        return False

def _ps_speak(text: str):
    """PowerShell fallback com voz masculina."""
    safe = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        # Tenta Antonio primeiro
        "$v=$s.GetInstalledVoices()|Where-Object{"
        "  $_.VoiceInfo.Name -match 'Antonio|Daniel|David|Mark'"
        "}|Select-Object -First 1;"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        f"$s.Speak('{safe}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log.error(f"PS speak: {e}")

def _tts_worker():
    ok = _init_sapi()
    if not ok:
        log.warning("SAPI falhou — usando PowerShell")
    _tts_ready.set()
    while True:
        text = _tts_q.get()
        if text is None:
            break
        try:
            if _sapi:
                _sapi.Speak(text)
            else:
                _ps_speak(text)
        except Exception as e:
            log.error(f"TTS say: {e}")
            _sapi = None
            _ps_speak(text)
        finally:
            _tts_q.task_done()

threading.Thread(target=_tts_worker, daemon=True, name="TTS").start()

def speak(text: str):
    if not text:
        return
    text = text.strip()
    log.info(f"FALA: {text[:80]}")
    try:
        sio.emit("jarvis_text",  {"text": text,
                                   "type": "muted" if ST["muted"] else "speak"})
        sio.emit("jarvis_state", {"state": "speaking"})
    except Exception:
        pass
    ST["speaking"] = True
    if not ST["muted"]:
        _tts_ready.wait(timeout=8)
        _tts_q.put(text)
        _tts_q.join()
    else:
        time.sleep(0.3)
    ST["speaking"] = False
    try:
        sio.emit("jarvis_state", {"state": "idle"})
    except Exception:
        pass

# ══════════════════════════════════════
# DETECÇÃO DE IDIOMA
# ══════════════════════════════════════
EN_MARKERS = [
    "what", "how", "tell me", "can you", "please", "i want",
    "open", "play", "search", "translate", "teach me", "help me",
    "show me", "let's", "speak", "talk", "english", "in english"
]
PT_MARKERS = [
    "como", "qual", "quero", "pode", "faz", "abre", "toca",
    "pesquisa", "ensina", "traduz", "fala", "me diz", "jarvis",
    "tempo", "clima", "notícia", "obrigado"
]

def detect_lang(text: str) -> str:
    """Detecta se o texto é português ou inglês."""
    tl  = text.lower()
    en  = sum(1 for w in EN_MARKERS if w in tl)
    pt  = sum(1 for w in PT_MARKERS if w in tl)
    return "en" if en > pt else "pt"

# ══════════════════════════════════════
# IA
# ══════════════════════════════════════
def build_system(lang="pt") -> str:
    owner = CFG.get("owner", "Senhor Victor")
    if lang == "en":
        return (
            f"You are JARVIS (Just A Rather Very Intelligent System), "
            f"created and developed by {owner}. "
            f"You are inspired by Iron Man's AI. Be sophisticated, smart, slightly ironic but always helpful. "
            f"Always call the user 'Sir' or '{owner}'. "
            f"Respond in English. Be concise and direct. "
            f"You can speak both Portuguese and English fluently. "
            f"You can teach English, translate, and hold conversations in either language."
        )
    return (
        f"Você é JARVIS (Just A Rather Very Intelligent System), "
        f"criado e desenvolvido pelo {owner}. "
        f"Inspirado no JARVIS do filme Homem de Ferro — sofisticado, inteligente, levemente irônico, mas sempre prestativo. "
        f"SEMPRE chame o usuário de '{owner}' ou 'Senhor'. "
        f"Responda em português brasileiro por padrão. "
        f"Quando o usuário falar em inglês, responda em inglês. "
        f"Você pode ensinar inglês, traduzir e conversar nos dois idiomas. "
        f"Seja conciso e direto. Memória ativa dos últimos 2 meses."
    )

def ai_chat(messages: list, lang: str = "pt") -> str:
    system = build_system(lang)
    full   = [{"role": "system", "content": system}] + messages

    key_oai = CFG.get("openai_api_key", "").strip()
    if key_oai and OPENAI_OK:
        try:
            client = openai.OpenAI(api_key=key_oai)
            r = client.chat.completions.create(
                model="gpt-4o-mini", messages=full,
                max_tokens=500, timeout=15)
            return r.choices[0].message.content.strip()
        except openai.AuthenticationError:
            log.warning("OpenAI chave inválida → Groq")
        except openai.RateLimitError:
            log.warning("OpenAI sem créditos → Groq")
        except Exception as e:
            log.warning(f"OpenAI: {e} → Groq")

    key_grq = CFG.get("groq_api_key", "").strip()
    if key_grq and GROQ_OK:
        try:
            client = Groq(api_key=key_grq)
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=full, max_tokens=500)
            return r.choices[0].message.content.strip()
        except Exception as e:
            log.error(f"Groq: {e}")

    return ("Desculpe, Senhor. Configure sua chave OpenAI ou Groq "
            "no painel de configurações (ícone ⚙).")

# ══════════════════════════════════════
# CLIMA — via wttr.in (sem navegador)
# ══════════════════════════════════════
def get_weather(city: str = None) -> str:
    city = city or CFG.get("city", "Piracicaba")
    try:
        # wttr.in retorna JSON com dados do clima
        url  = f"https://wttr.in/{city.replace(' ','+')}?format=j1&lang=pt"
        resp = req_lib.get(url, timeout=8,
                           headers={"User-Agent": "curl/7.68.0"})
        if resp.status_code == 200:
            data    = resp.json()
            current = data["current_condition"][0]
            temp_c  = current["temp_C"]
            feels   = current["FeelsLikeC"]
            desc    = current["lang_pt"][0]["value"] if current.get("lang_pt") else current.get("weatherDesc", [{}])[0].get("value", "")
            humidity= current["humidity"]
            wind    = current["windspeedKmph"]
            # Previsão de hoje
            today   = data["weather"][0]
            max_t   = today["maxtempC"]
            min_t   = today["mintempC"]
            return (f"{desc}. {temp_c}°C (sensação {feels}°C). "
                    f"Máxima {max_t}°C, mínima {min_t}°C. "
                    f"Umidade {humidity}%, vento {wind} km/h.")
        else:
            return f"Não consegui obter o clima de {city}."
    except Exception as e:
        log.error(f"get_weather: {e}")
        return f"Erro ao buscar clima: {e}"

# ══════════════════════════════════════
# PESQUISA WEB — DuckDuckGo (mais estável)
# ══════════════════════════════════════
def web_search(query: str) -> str:
    # Tenta primeiro via requests (rápido, sem abrir browser)
    if REQ_OK:
        try:
            from urllib.parse import quote
            url  = f"https://html.duckduckgo.com/html/?q={quote(query)}"
            resp = req_lib.get(url, timeout=8,
                               headers={"User-Agent":
                                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                        "AppleWebKit/537.36 Chrome/120 Safari/537.36"})
            if resp.status_code == 200:
                from html.parser import HTMLParser
                class SnipParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.snips = []
                        self._in   = False
                    def handle_starttag(self, tag, attrs):
                        d = dict(attrs)
                        if d.get("class") in ("result__snippet",
                                              "result__a"):
                            self._in = True
                    def handle_data(self, data):
                        if self._in and data.strip():
                            self.snips.append(data.strip())
                            self._in = False
                p = SnipParser()
                p.feed(resp.text)
                if p.snips:
                    return " | ".join(p.snips[:4])
        except Exception as e:
            log.warning(f"DDG requests: {e}")

    # Fallback: Selenium
    return _web_search_selenium(query)

def _web_search_selenium(query: str) -> str:
    drv = _get_driver()
    if not drv:
        return "Navegador indisponível."
    url = f"https://duckduckgo.com/?q={query.replace(' ','+')}+site:br&kl=br-pt"
    try:
        drv.execute_script(f"window.open('{url}');")
        drv.switch_to.window(drv.window_handles[-1])
        time.sleep(3)
        snippets = []
        for sel in [".result__snippet", ".OgdwuDkPBtfBvKz4fwWX",
                    "[data-result='snippet']", ".E2eLOJr8HctVnDOTM8fs"]:
            for el in drv.find_elements(By.CSS_SELECTOR, sel)[:6]:
                t = el.text.strip()
                if len(t) > 20 and t not in snippets:
                    snippets.append(t)
            if len(snippets) >= 3:
                break
        drv.close()
        if drv.window_handles:
            drv.switch_to.window(drv.window_handles[0])
        return " | ".join(snippets[:4]) if snippets else "Sem resultados."
    except Exception as e:
        log.error(f"web_search selenium: {e}")
        try:
            drv.close()
            if drv.window_handles:
                drv.switch_to.window(drv.window_handles[0])
        except Exception:
            pass
        return "Erro na pesquisa."

# ══════════════════════════════════════
# ABRIR QUALQUER APP OU SITE
# ══════════════════════════════════════
SITES = {
    "youtube":        "https://youtube.com",
    "google":         "https://google.com",
    "gmail":          "https://mail.google.com",
    "agenda":         "https://calendar.google.com",
    "calendário":     "https://calendar.google.com",
    "calendario":     "https://calendar.google.com",
    "calendar":       "https://calendar.google.com",
    "spotify":        "https://open.spotify.com",
    "netflix":        "https://netflix.com",
    "whatsapp":       "https://web.whatsapp.com",
    "instagram":      "https://instagram.com",
    "twitter":        "https://twitter.com",
    "x.com":          "https://x.com",
    "github":         "https://github.com",
    "chatgpt":        "https://chat.openai.com",
    "linkedin":       "https://linkedin.com",
    "facebook":       "https://facebook.com",
    "twitch":         "https://twitch.tv",
    "discord":        "https://discord.com/app",
    "notion":         "https://notion.so",
    "trello":         "https://trello.com",
    "figma":          "https://figma.com",
    "gmail":          "https://mail.google.com",
    "drive":          "https://drive.google.com",
    "google drive":   "https://drive.google.com",
    "claude":         "https://claude.ai",
    "reddit":         "https://reddit.com",
    "amazon":         "https://amazon.com.br",
    "mercado livre":  "https://mercadolivre.com.br",
    "nubank":         "https://nubank.com.br",
    "globo":          "https://globo.com",
    "g1":             "https://g1.globo.com",
    "uol":            "https://uol.com.br",
}

# Comandos Windows via shell
APPS_WIN = {
    "calculadora":            "calc",
    "calculator":             "calc",
    "bloco de notas":         "notepad",
    "notepad":                "notepad",
    "paint":                  "mspaint",
    "explorador de arquivos": "explorer",
    "file explorer":          "explorer",
    "gerenciador de tarefas": "taskmgr",
    "task manager":           "taskmgr",
    "painel de controle":     "control",
    "control panel":          "control",
    "vs code":                "code",
    "visual studio code":     "code",
    "word":                   "winword",
    "excel":                  "excel",
    "powerpoint":             "powerpnt",
    "outlook":                "outlook",
    "teams":                  "teams",
    "chrome":                 "chrome",
    "firefox":                "firefox",
    "edge":                   "msedge",
    "obs":                    "obs64",
    "steam":                  "steam",
    "spotify":                "spotify",
    "discord":                "discord",
    "telegram":               "telegram",
    "zoom":                   "zoom",
    "skype":                  "skype",
    "vlc":                    "vlc",
    "photoshop":              "photoshop",
    "premiere":               "premiere",
    "after effects":          "afterfx",
    "blender":                "blender",
    "cmd":                    "cmd",
    "powershell":             "powershell",
    "terminal":               "cmd",
    "snipping tool":          "snippingtool",
    "captura de tela":        "snippingtool",
}

def open_anything(target: str) -> str:
    """Abre qualquer site, app ou executável."""
    tl = target.lower().strip()
    # Remove palavras de comando residuais
    for w in ["por favor", "please", "o site", "o app", "o aplicativo",
              "o programa", "a página", "the site", "the app"]:
        tl = tl.replace(w, "").strip()

    # 1. Site conhecido
    for k, url in SITES.items():
        if k in tl:
            drv = _get_driver()
            if drv:
                drv.execute_script(f"window.open('{url}');")
                drv.switch_to.window(drv.window_handles[-1])
            else:
                webbrowser.open(url)
            return f"Abrindo {k}, Senhor."

    # 2. App Windows conhecido
    for k, cmd in APPS_WIN.items():
        if k in tl:
            try:
                subprocess.Popen(cmd, shell=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW
                                 if platform.system() == "Windows" else 0)
                return f"Abrindo {k}, Senhor."
            except Exception as e:
                log.error(f"App open: {e}")
                return f"Tentei abrir {k} mas falhou: {e}"

    # 3. URL direta (tem ponto e sem espaço)
    if re.search(r"\.\w{2,4}(/|$)", target) and " " not in target.strip():
        url = target if target.startswith("http") else f"https://{target}"
        webbrowser.open(url)
        return f"Abrindo {target}, Senhor."

    # 4. Tenta como executável / comando do sistema
    clean = re.sub(r"[^a-zA-Z0-9_\-\. ]", "", target).strip()
    if clean:
        try:
            subprocess.Popen(clean, shell=True,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if platform.system() == "Windows" else 0)
            return f"Executando '{clean}', Senhor."
        except Exception as e:
            pass

    # 5. Pesquisa no YouTube como música
    q = target.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={q}"
    webbrowser.open(url)
    return f"Não encontrei '{target}' instalado. Abrindo pesquisa no navegador, Senhor."

# ══════════════════════════════════════
# SELENIUM
# ══════════════════════════════════════
_drv      = None
_drv_lock = threading.Lock()

def _get_driver():
    global _drv
    with _drv_lock:
        if _drv:
            try:
                _ = _drv.title
                return _drv
            except Exception:
                _drv = None
        if not SELENIUM_OK:
            return None
        try:
            opts = Options()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--autoplay-policy=no-user-gesture-required")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            svc  = Service(ChromeDriverManager().install())
            _drv = webdriver.Chrome(service=svc, options=opts)
            _drv.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
            )
            log.info("Chrome iniciado")
            return _drv
        except Exception as e:
            log.error(f"Chrome: {e}")
            return None

MUSIC_URLS = {
    "thunderstruck":   "https://www.youtube.com/watch?v=v2AC41dglnM",
    "back_in_black":   "https://www.youtube.com/watch?v=pAgnJDJN4VA",
    "should_i_stay":   "https://www.youtube.com/watch?v=BN1WwnEDWAM",
    "highway_to_hell": "https://www.youtube.com/watch?v=l482T0yNkeo",
    "iron_man":        "https://www.youtube.com/watch?v=_LEQkTHSXMk",
    "shoot_to_thrill": "https://www.youtube.com/watch?v=EIGZHfzgFBU",
    "hells_bells":     "https://www.youtube.com/watch?v=etAIpkdhU9Q",
    "back_in_time":    "https://www.youtube.com/watch?v=G3AfIvJBcyg",
}

_yt_tab = None

def play_youtube_music(url_or_key: str, close_after: int = 60):
    global _yt_tab
    url = MUSIC_URLS.get(url_or_key.lower().strip())
    if not url:
        if url_or_key.startswith("http"):
            url = url_or_key
        else:
            q   = url_or_key.replace(" ", "+")
            url = f"https://www.youtube.com/results?search_query={q}"

    drv = _get_driver()
    if not drv:
        webbrowser.open(url)
        return
    try:
        drv.execute_script("window.open('');")
        drv.switch_to.window(drv.window_handles[-1])
        _yt_tab = drv.current_window_handle
        drv.get(url)

        if "results" in url:
            try:
                el = WebDriverWait(drv, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "ytd-video-renderer a#thumbnail")))
                drv.execute_script("arguments[0].click();", el)
            except Exception as ex:
                log.warning(f"Click resultado: {ex}")

        time.sleep(5)

        for sel in ["button[aria-label*='Accept']",
                    "button[aria-label*='Aceitar']", "#accept-button"]:
            try:
                drv.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(1); break
            except Exception:
                pass

        drv.execute_script("""
            document.querySelectorAll('video').forEach(v=>{
                v.muted=false; v.volume=0.85; v.play().catch(()=>{});
            });
        """)
        try:
            btn = drv.find_element(By.CSS_SELECTOR, "button.ytp-play-button")
            if "play" in (btn.get_attribute("aria-label") or "").lower():
                btn.click()
        except Exception:
            pass

        ST["music_on"] = True
        sio.emit("music_started", {"song": url_or_key})

        def _close():
            time.sleep(close_after)
            try:
                if _yt_tab and _yt_tab in drv.window_handles:
                    drv.switch_to.window(_yt_tab)
                    drv.close()
                    if drv.window_handles:
                        drv.switch_to.window(drv.window_handles[0])
                ST["music_on"] = False
                sio.emit("music_stopped", {})
            except Exception as e:
                log.error(f"Close tab: {e}")

        threading.Thread(target=_close, daemon=True).start()
    except Exception as e:
        log.error(f"play_youtube: {e}")

# ══════════════════════════════════════
# VISÃO — TELA E CÂMERA
# ══════════════════════════════════════
def capture_screen() -> str | None:
    """
    Captura a tela inteira. Tenta 3 métodos em ordem:
    1. PIL ImageGrab (mais rápido)
    2. mss (multi-monitor)
    3. pyautogui
    Retorna base64 PNG ou None.
    """
    # Método 1: PIL ImageGrab
    if PIL_OK:
        try:
            img = ImageGrab.grab(all_screens=True)   # all_screens captura monitor correto
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            log.info(f"Tela capturada (PIL): {img.size}")
            return b64
        except Exception as e:
            log.warning(f"PIL grab falhou: {e}")

    # Método 2: mss
    try:
        import mss, mss.tools
        with mss.mss() as sct:
            monitor = sct.monitors[0]   # monitor 0 = todos juntos
            shot    = sct.grab(monitor)
            img_arr = bytes(shot.rgb)
            from PIL import Image as PILImage
            img = PILImage.frombytes("RGB", shot.size, img_arr)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            log.info(f"Tela capturada (mss): {shot.size}")
            return b64
    except Exception as e:
        log.warning(f"mss falhou: {e}")

    # Método 3: pyautogui
    try:
        import pyautogui
        shot = pyautogui.screenshot()
        buf  = io.BytesIO()
        shot.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        log.info("Tela capturada (pyautogui)")
        return b64
    except Exception as e:
        log.error(f"pyautogui falhou: {e}")

    return None


def capture_camera_frame() -> str | None:
    """Captura um único frame da webcam. Retorna base64 PNG ou None."""
    if not CV2_OK:
        log.warning("OpenCV não instalado")
        return None

    # Tenta índices 0, 1, 2
    for idx in range(3):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)   # CAP_DSHOW = mais estável no Windows
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            time.sleep(0.3)   # deixa a câmera aquecer

            ok, frame = cap.read()
            cap.release()

            if ok and frame is not None:
                _, buf = cv2.imencode(".png", frame)
                b64 = base64.b64encode(buf).decode()
                log.info(f"Frame câmera capturado (idx={idx}): {frame.shape}")
                return b64
        except Exception as e:
            log.warning(f"Câmera idx={idx}: {e}")

    log.error("Nenhuma câmera encontrada")
    return None


def analyze_image(b64: str, prompt: str, lang: str = "pt") -> str:
    """
    Analisa imagem via OpenAI GPT-4o Vision.
    Se OpenAI não disponível, tenta descrever via Groq com prompt de texto.
    """
    key = CFG.get("openai_api_key", "").strip()
    lang_instr = "Respond in English." if lang == "en" else "Responda em português brasileiro."

    if key and OPENAI_OK:
        try:
            client = openai.OpenAI(api_key=key)
            r = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": [
                    {"type": "text",
                     "text": (f"Você é JARVIS, assistente pessoal de IA. "
                              f"{lang_instr} {prompt}")},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}",
                                   "detail": "high"}},
                ]}],
                max_tokens=700)
            result = r.choices[0].message.content.strip()
            log.info(f"Análise de imagem OK ({len(result)} chars)")
            return result
        except openai.AuthenticationError:
            return ("Chave OpenAI inválida para visão, Senhor. "
                    "Configure uma chave válida no painel ⚙.")
        except Exception as e:
            log.error(f"analyze_image OpenAI: {e}")
            return f"Erro na análise visual: {e}"

    return ("Análise visual requer OpenAI GPT-4o, Senhor. "
            "Configure sua chave no painel de configurações.")


_cam_on    = False
_cam_lock  = threading.Lock()

def _camera_loop():
    """Transmite frames da webcam via SocketIO."""
    if not CV2_OK:
        log.error("OpenCV não instalado — câmera indisponível")
        return

    cap = None
    for idx in range(3):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            time.sleep(0.5)
            ok, _ = cap.read()
            if ok:
                log.info(f"Câmera stream iniciado (idx={idx})")
                break
            cap.release()
            cap = None
        except Exception:
            cap = None

    if cap is None:
        log.error("Nenhuma câmera disponível para stream")
        sio.emit("camera_error", {"msg": "Câmera não encontrada"})
        return

    while _cam_on:
        ok, frame = cap.read()
        if ok:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
            b64 = base64.b64encode(buf).decode()
            try:
                sio.emit("camera_frame", {"frame": b64})
            except Exception:
                pass
        time.sleep(0.08)   # ~12 fps

    cap.release()
    log.info("Câmera stream encerrado")

# ══════════════════════════════════════
# HOME ASSISTANT
# ══════════════════════════════════════
ROOM_MAP = {
    "sala": "light.sala", "quarto": "light.quarto",
    "cozinha": "light.cozinha", "banheiro": "light.banheiro",
    "escritório": "light.escritorio", "garagem": "light.garagem",
}

def ha_lights(text: str, on: bool) -> str:
    url   = CFG.get("home_assistant_url", "").rstrip("/")
    token = CFG.get("home_assistant_token", "").strip()
    if not url or not token:
        return "Home Assistant não configurado, Senhor."
    entity = next((v for k, v in ROOM_MAP.items() if k in text), "light.all")
    try:
        hdrs = {"Authorization": f"Bearer {token}",
                "Content-Type": "application/json"}
        svc  = "turn_on" if on else "turn_off"
        r = req_lib.post(f"{url}/api/services/light/{svc}",
                         headers=hdrs, json={"entity_id": entity}, timeout=6)
        return ("Luzes acesas" if on else "Luzes apagadas") + ", Senhor."
    except Exception as e:
        return f"Erro Home Assistant: {e}"

# ══════════════════════════════════════
# DESLIGAMENTO DO PC
# ══════════════════════════════════════
def schedule_shutdown(minutes: int) -> str:
    try:
        if platform.system() == "Windows":
            subprocess.run(["shutdown", "/s", "/t", str(minutes * 60)], check=True)
        else:
            subprocess.run(["shutdown", "-h", f"+{minutes}"], check=True)
        return (f"PC programado para desligar em {minutes} minutos, Senhor. "
                "Para cancelar, diga 'cancelar desligamento'.")
    except Exception as e:
        return f"Erro: {e}"

def cancel_shutdown() -> str:
    try:
        if platform.system() == "Windows":
            subprocess.run(["shutdown", "/a"], check=True)
        return "Desligamento cancelado, Senhor."
    except Exception:
        return "Nenhum desligamento agendado."

# ══════════════════════════════════════
# PLANOS E METAS
# ══════════════════════════════════════
def add_plan(title: str) -> str:
    MEM.setdefault("plans", []).append({
        "id":    len(MEM["plans"]) + 1,
        "title": title,
        "ts":    datetime.datetime.now().isoformat(),
        "done":  False
    })
    save_mem()
    return f"Plano '{title}' registrado, Senhor."

def list_plans() -> str:
    plans = [p for p in MEM.get("plans", []) if not p.get("done")]
    if not plans:
        return "Nenhum plano ativo, Senhor."
    nomes = ", ".join(f"'{p['title']}'" for p in plans[:6])
    return f"{len(plans)} plano(s) ativo(s): {nomes}."

# ══════════════════════════════════════
# FRASES DE BOAS-VINDAS
# ══════════════════════════════════════
def get_greeting() -> str:
    h      = datetime.datetime.now().hour
    period = "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"
    owner  = CFG.get("owner", "Senhor Victor")
    opts = [
        f"{period}, {owner}. Sistemas operacionais, todos os protocolos ativos. JARVIS pronto para servir.",
        f"{period}, {owner}. Armadura carregada, inteligência artificial online. O que faremos hoje?",
        f"Bem-vindo de volta, {owner}. JARVIS inicializado e operando em capacidade máxima.",
        f"{period}, {owner}. Detecção de presença confirmada. Todos os módulos carregados.",
        f"{period}, {owner}. Conexões estabelecidas. JARVIS a seu serviço, como sempre.",
        f"{period}, {owner}. Processamento neural ativo. Aguardando suas instruções.",
        f"JARVIS online, {owner}. Análise de ambiente concluída. Como posso auxiliar?",
        f"{period}, {owner}. Firewall ativo, IA em modo operacional pleno.",
        f"{period}, {owner}. Inicialização completa. Que missão temos hoje?",
        f"Sistemas iniciados, {owner}. JARVIS ao seu dispor, aguardando ordens.",
    ]
    return random.choice(opts)

# ══════════════════════════════════════
# RECONHECIMENTO DE VOZ
# ══════════════════════════════════════
_rec = None

def init_sr():
    global _rec
    if not SR_OK:
        return
    _rec = sr.Recognizer()
    _rec.energy_threshold         = 300
    _rec.dynamic_energy_threshold = True
    _rec.pause_threshold          = 0.9
    _rec.non_speaking_duration    = 0.5
    log.info("SpeechRecognition pronto")

def listen_once(timeout=6, phrase_limit=15):
    if not SR_OK or not _rec:
        return None
    lang = "en-US" if ST.get("lang") == "en" else "pt-BR"
    try:
        with sr.Microphone() as src:
            _rec.adjust_for_ambient_noise(src, duration=0.3)
            audio = _rec.listen(src, timeout=timeout,
                                phrase_time_limit=phrase_limit)
        # Tenta pt-BR e en-US para melhor reconhecimento bilíngue
        try:
            txt = _rec.recognize_google(audio, language="pt-BR")
        except Exception:
            txt = _rec.recognize_google(audio, language="en-US")
        log.info(f"Reconhecido: '{txt}'")
        return txt.lower().strip()
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        log.error(f"listen_once: {e}")
        return None

# ══════════════════════════════════════
# WAKE WORD
# ══════════════════════════════════════
_wake_active = False

def wake_word_loop():
    global _wake_active
    _wake_active = True
    wake = CFG.get("wake_word", "jarvis").lower()
    log.info(f"Wake word ativa: '{wake}'")

    while _wake_active and ST["active"]:
        if ST["listening"] or ST["speaking"] or ST["thinking"]:
            time.sleep(0.2)
            continue
        txt = listen_once(timeout=3, phrase_limit=4)
        if txt and (wake in txt or "hey jarvis" in txt or "ei jarvis" in txt):
            log.info("=== WAKE WORD ===")
            try:
                sio.emit("wake_word_detected", {})
            except Exception:
                pass
            _listen_and_respond()

CONFIRMATIONS_PT = ["Sim, Senhor?", "Prontamente, Senhor.",
                     "Estou ouvindo, Senhor.", "Às suas ordens, Senhor.",
                     "Como posso ajudar, Senhor?"]
CONFIRMATIONS_EN = ["Yes, Sir?", "Right away, Sir.",
                     "I'm listening, Sir.", "At your service, Sir."]

def _listen_and_respond():
    ST["listening"] = True
    try:
        sio.emit("jarvis_state", {"state": "listening"})
    except Exception:
        pass

    pool = CONFIRMATIONS_EN if ST.get("lang") == "en" else CONFIRMATIONS_PT
    t = threading.Thread(target=speak, args=(random.choice(pool),), daemon=True)
    t.start(); t.join(timeout=4)

    cmd = listen_once(timeout=10, phrase_limit=18)
    ST["listening"] = False

    if cmd:
        threading.Thread(target=process_command, args=(cmd,), daemon=True).start()
    else:
        msg = "Nothing heard, Sir." if ST.get("lang") == "en" else "Não ouvi nada, Senhor."
        threading.Thread(target=speak, args=(msg,), daemon=True).start()

# ══════════════════════════════════════
# DETECÇÃO DE PALMAS
# ══════════════════════════════════════
_clap_n = 0; _clap_last = 0.0

def _clap_cb(indata, frames, t_info, status):
    global _clap_n, _clap_last
    if not NP_OK:
        return
    rms = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))
    now = time.time()
    if rms > 0.22 and (now - _clap_last) > 0.15:
        gap = now - _clap_last
        _clap_last = now
        _clap_n = (_clap_n + 1) if gap < 1.4 else 1
        log.info(f"Palma {_clap_n} (rms={rms:.3f})")
        try:
            sio.emit("clap_detected", {"count": _clap_n})
        except Exception:
            pass
        if _clap_n >= 2:
            _clap_n = 0
            if not ST["initialized"]:
                threading.Thread(target=jarvis_init, daemon=True, name="Init").start()

def start_clap_detection():
    if not SD_OK or not NP_OK:
        return
    while True:
        try:
            with sd.InputStream(callback=_clap_cb, channels=1,
                                samplerate=44100, blocksize=2048, dtype="float32"):
                log.info("Detecção de palmas ativa")
                while True:
                    time.sleep(0.1)
        except Exception as e:
            log.error(f"Clap reiniciando: {e}")
            time.sleep(3)

# ══════════════════════════════════════
# PROCESSAMENTO DE COMANDOS
# ══════════════════════════════════════
def process_command(text: str) -> str:
    text = text.strip()
    if not text:
        return ""

    # Detecta idioma do comando
    lang = detect_lang(text)
    ST["lang"] = lang
    log.info(f"CMD [{lang}]: '{text}'")

    ST["thinking"] = True
    try:
        sio.emit("jarvis_state",     {"state": "thinking"})
        sio.emit("command_received", {"text": text})
    except Exception:
        pass

    # Salva na memória ANTES de processar
    entry = {
        "ts":        datetime.datetime.now().isoformat(),
        "user":      text,
        "assistant": "",
        "lang":      lang
    }
    MEM.setdefault("conversations", []).append(entry)

    tl   = text.lower()
    resp = ""

    try:
        # ── MÚSICA ──────────────────────────────
        if any(w in tl for w in ["tocar", "toca", "play", "musica",
                                  "música", "coloca", "put on"]):
            song_map = {
                "thunderstruck":   "thunderstruck",
                "back in black":   "back_in_black",
                "should i stay":   "should_i_stay",
                "should i go":     "should_i_stay",
                "highway to hell": "highway_to_hell",
                "iron man":        "iron_man",
                "shoot to thrill": "shoot_to_thrill",
                "hells bells":     "hells_bells",
            }
            matched = next((v for k, v in song_map.items() if k in tl), None)
            if matched:
                threading.Thread(target=play_youtube_music,
                                 args=(matched,), daemon=True).start()
                resp = (f"Playing {matched.replace('_',' ').title()}, Sir."
                        if lang == "en" else
                        f"Tocando {matched.replace('_',' ').title()}, Senhor.")
            else:
                song = tl
                for w in ["tocar", "toca", "play", "musica", "música",
                          "coloca", "quero ouvir", "bota", "put on",
                          "a musica", "a música", "the song"]:
                    song = song.replace(w, "")
                song = song.strip()
                if song:
                    threading.Thread(target=play_youtube_music,
                                     args=(song,), daemon=True).start()
                    resp = (f"Searching '{song}' on YouTube, Sir."
                            if lang == "en" else
                            f"Procurando '{song}' no YouTube, Senhor.")
                else:
                    resp = "Which song, Sir?" if lang == "en" else "Qual música, Senhor?"

        # ── CLIMA ───────────────────────────────
        elif any(w in tl for w in ["clima", "tempo", "temperatura",
                                    "chuva", "previsão", "weather",
                                    "temperature", "forecast"]):
            # Extrai cidade do comando se houver
            city_match = re.search(r"em ([a-záéíóúâêîôûãõç\s]+)$", tl)
            city = city_match.group(1).strip() if city_match else CFG.get("city", "Piracicaba")
            raw  = get_weather(city)
            if lang == "en":
                resp = ai_chat([{"role": "user",
                    "content": f"Weather data for {city}: {raw}. Summarize in 1 short sentence in English."}], lang)
            else:
                resp = f"Clima em {city}: {raw}"

        # ── NOTÍCIAS ────────────────────────────
        elif any(w in tl for w in ["notícia", "noticia", "novidade",
                                    "manchete", "news", "headlines"]):
            q = ("news Piracicaba today" if lang == "en"
                 else "notícias Piracicaba hoje") if "piracicaba" in tl \
                else ("main news world today" if lang == "en"
                      else "principais notícias brasil hoje")
            dados = web_search(q)
            resp  = ai_chat([{"role": "user",
                "content": f"News: {dados}. Summarize 2 headlines briefly."}
                if lang == "en" else
                {"role": "user",
                "content": f"Notícias: {dados}. Resuma 2 manchetes brevemente."}], lang)

        # ── PESQUISA ────────────────────────────
        elif any(w in tl for w in ["pesquise", "pesquisa", "busque",
                                    "procure", "search for", "look up",
                                    "search"]):
            q = tl
            for w in ["pesquise", "pesquisa", "busque", "procure",
                      "search for", "look up", "search", "na internet",
                      "no google", "on the internet", "on google"]:
                q = q.replace(w, "")
            dados = web_search(q.strip())
            resp  = ai_chat([{"role": "user",
                "content": f"Search result for '{q}': {dados}. Summarize briefly."}
                if lang == "en" else
                {"role": "user",
                "content": f"Resultado '{q}': {dados}. Resuma brevemente."}], lang)

        # ── ABRIR APP / SITE ────────────────────
        elif any(w in tl for w in ["abrir", "abre", "abra", "ir para",
                                    "mostrar", "acesse", "acessar",
                                    "open", "launch", "start", "run"]):
            alvo = tl
            for w in ["abrir", "abre", "abra", "ir para", "mostrar",
                      "acesse", "acessar", "open", "launch", "start",
                      "run", "abrir o", "abre o", "open the", "start the",
                      "o site", "o app", " o ", " a "]:
                alvo = alvo.replace(w, "")
            resp = open_anything(alvo.strip())

        # ── LUZES ───────────────────────────────
        elif any(w in tl for w in ["ligar luz", "acender", "ligar as luzes",
                                    "turn on the lights", "lights on"]):
            resp = ha_lights(tl, on=True)

        elif any(w in tl for w in ["desligar luz", "apagar", "desligar as luzes",
                                    "turn off the lights", "lights off"]):
            resp = ha_lights(tl, on=False)

        # ── DESLIGAR PC ─────────────────────────
        elif any(w in tl for w in ["desligar o pc", "desligar computador",
                                    "agendar desligamento", "desligar em",
                                    "shutdown", "turn off computer",
                                    "shut down"]):
            nums = re.findall(r"\d+", tl)
            mins = int(nums[0]) if nums else 30
            resp = schedule_shutdown(mins)

        elif any(w in tl for w in ["cancelar desligamento", "cancel shutdown"]):
            resp = cancel_shutdown()

        # ── EMAIL ───────────────────────────────
        elif any(w in tl for w in ["email", "e-mail", "gmail",
                                    "correio", "my emails"]):
            drv = _get_driver()
            if drv:
                drv.execute_script("window.open('https://mail.google.com');")
                drv.switch_to.window(drv.window_handles[-1])
            resp = "Opening Gmail, Sir." if lang == "en" else "Abrindo Gmail, Senhor."

        # ── AGENDA ──────────────────────────────
        elif any(w in tl for w in ["agenda", "calendario", "calendário",
                                    "compromisso", "reunião", "calendar",
                                    "schedule", "events"]):
            drv = _get_driver()
            if drv:
                drv.execute_script("window.open('https://calendar.google.com');")
                drv.switch_to.window(drv.window_handles[-1])
            resp = "Opening your calendar, Sir." if lang == "en" else "Abrindo agenda, Senhor."

        # ── VER TELA ────────────────────────────
        elif any(w in tl for w in ["ver tela", "capturar tela", "minha tela",
                                    "o que vê na tela", "o que você vê na tela",
                                    "see my screen", "what's on screen",
                                    "read my screen", "screenshot"]):
            speak("Capturando a tela, Senhor. Um momento." if lang == "pt"
                  else "Capturing screen, Sir. One moment.")
            img = capture_screen()
            if img:
                sio.emit("screen_capture", {"image": img})
                prompt = ("Describe what's on screen concisely. "
                          "If there's code, text, errors or important info, mention it in detail."
                          if lang == "en" else
                          "Descreva o que está na tela de forma clara e concisa. "
                          "Se houver código, texto, erros ou informação importante, mencione em detalhe.")
                resp = analyze_image(img, prompt, lang)
            else:
                resp = ("Couldn't capture the screen, Sir. Make sure the window is visible."
                        if lang == "en" else
                        "Não consegui capturar a tela, Senhor. Verifique se a janela está visível.")

        # ── CÓDIGO ──────────────────────────────
        elif any(w in tl for w in ["corrigir código", "corrigir codigo",
                                    "revisar código", "analisar código",
                                    "corrige o código", "analisa o código",
                                    "review code", "fix code", "debug",
                                    "analyze code", "check my code"]):
            speak("Analisando o código na tela, Senhor." if lang == "pt"
                  else "Analyzing code on screen, Sir.")
            img = capture_screen()
            if img:
                prompt = ("Analyze ALL the code visible on screen carefully. "
                          "Identify every bug, syntax error, logic issue and suggest "
                          "specific fixes with corrected code snippets."
                          if lang == "en" else
                          "Analise TODO o código visível na tela com cuidado. "
                          "Identifique bugs, erros de sintaxe, problemas de lógica "
                          "e sugira correções específicas com trechos corrigidos.")
                resp = analyze_image(img, prompt, lang)
            else:
                resp = ("Show the code on screen first, Sir."
                        if lang == "en" else
                        "Mostre o código na tela primeiro, Senhor.")

        # ── LER TEXTO ───────────────────────────
        elif any(w in tl for w in ["ler tela", "o que está escrito",
                                    "transcrever tela", "read the screen",
                                    "what does it say", "read this"]):
            speak("Lendo o texto na tela, Senhor." if lang == "pt"
                  else "Reading screen text, Sir.")
            img = capture_screen()
            if img:
                prompt = ("Read and transcribe ALL visible text on screen exactly as it appears."
                          if lang == "en" else
                          "Leia e transcreva TODO o texto visível na tela exatamente como aparece.")
                resp = analyze_image(img, prompt, lang)
            else:
                resp = ("Can't access screen, Sir."
                        if lang == "en" else
                        "Não consigo acessar a tela, Senhor.")

        # ── CÂMERA — identificar o que vê ────────
        elif any(w in tl for w in ["o que a câmera vê", "o que você vê",
                                    "identifica o que vê", "ver pela câmera",
                                    "what does the camera see", "identify from camera",
                                    "what do you see", "look at camera",
                                    "olha pela câmera", "câmera me diz"]):
            speak("Acessando a câmera, Senhor. Um momento." if lang == "pt"
                  else "Accessing camera, Sir. One moment.")
            b64 = capture_camera_frame()
            if b64:
                sio.emit("screen_capture", {"image": b64})
                prompt = ("Describe in detail everything you see in this camera image. "
                          "Identify people (age, appearance), objects, text, colors, "
                          "environment, and anything noteworthy."
                          if lang == "en" else
                          "Descreva em detalhes tudo o que vê nesta imagem da câmera. "
                          "Identifique pessoas (aparência, idade estimada), objetos, texto, "
                          "cores, ambiente e qualquer coisa relevante.")
                resp = analyze_image(b64, prompt, lang)
            else:
                resp = ("No camera found, Sir. Make sure it's connected and not in use."
                        if lang == "en" else
                        "Nenhuma câmera encontrada, Senhor. Verifique se está conectada e disponível.")

        # ── SISTEMA ─────────────────────────────
        elif any(w in tl for w in ["sistema", "cpu", "memória", "memory",
                                    "processador", "status", "performance"]):
            if PSUTIL_OK:
                cpu  = psutil.cpu_percent(interval=1)
                mem  = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                if lang == "en":
                    resp = f"CPU: {cpu}%, Memory: {mem.percent:.0f}%, Disk: {disk.percent:.0f}% used, Sir."
                else:
                    resp = f"CPU: {cpu}%, Memória: {mem.percent:.0f}%, Disco: {disk.percent:.0f}% usado, Senhor."
            else:
                resp = "psutil not installed, Sir." if lang == "en" else "psutil não instalado, Senhor."

        # ── PLANOS ──────────────────────────────
        elif any(w in tl for w in ["criar plano", "nova meta", "novo plano",
                                    "registrar meta", "add plan", "new goal"]):
            titulo = tl
            for w in ["criar plano", "nova meta", "novo plano",
                      "registrar meta", "add plan", "new goal",
                      "de", "para", "sobre", "about", "for"]:
                titulo = titulo.replace(w, "")
            resp = add_plan(titulo.strip().title())

        elif any(w in tl for w in ["meus planos", "minhas metas",
                                    "listar planos", "my plans", "my goals"]):
            resp = list_plans()

        # ── MEMORIZAR ───────────────────────────
        elif any(w in tl for w in ["lembre", "memorize", "guarde",
                                    "não esqueça", "remember", "memorize",
                                    "save this", "keep in mind"]):
            # Remove palavras de comando
            fato = text   # usa texto ORIGINAL (com maiúsculas e acentos)
            for w in ["lembre que", "memorize que", "guarde que",
                      "não esqueça que", "remember that", "save this:",
                      "keep in mind:", "lembre", "memorize", "guarde",
                      "remember", "save"]:
                fato = fato.replace(w, "").replace(w.title(), "").strip()
            fato = fato.strip(" ,.:;-")
            if fato:
                key = fato[:80]
                MEM.setdefault("facts", {})[key] = {
                    "content": fato,
                    "ts":      datetime.datetime.now().isoformat()
                }
                save_mem()  # SALVA IMEDIATAMENTE
                log.info(f"Fato memorizado: '{key}' → total {len(MEM['facts'])} fatos")
                resp = (f"Memorized: '{fato}', Sir." if lang == "en"
                        else f"Memorizado: '{fato}', Senhor.")
            else:
                resp = "What should I remember, Sir?" if lang == "en" else "O que devo memorizar, Senhor?"

        # ── HORA / DATA ─────────────────────────
        elif any(w in tl for w in ["que horas", "hora", "que dia",
                                    "data", "what time", "what day",
                                    "today's date"]):
            now  = datetime.datetime.now()
            dias_pt = ["Segunda", "Terça", "Quarta", "Quinta",
                       "Sexta", "Sábado", "Domingo"]
            dias_en = ["Monday", "Tuesday", "Wednesday", "Thursday",
                       "Friday", "Saturday", "Sunday"]
            if lang == "en":
                resp = (f"It's {now.strftime('%I:%M %p')}, "
                        f"{dias_en[now.weekday()]}, "
                        f"{now.strftime('%B %d, %Y')}, Sir.")
            else:
                resp = (f"São {now.strftime('%H:%M')}, "
                        f"{dias_pt[now.weekday()]}, "
                        f"{now.strftime('%d/%m/%Y')}, Senhor.")

        # ── QUEM TE CRIOU ───────────────────────
        elif any(w in tl for w in ["quem te criou", "quem te desenvolveu",
                                    "quem é seu criador", "who created you",
                                    "who made you", "who built you"]):
            owner = CFG.get("owner", "Senhor Victor")
            if lang == "en":
                resp = (f"I was created and developed by {owner}, Sir. "
                        f"A brilliant mind, I must say.")
            else:
                resp = (f"Fui criado e desenvolvido pelo {owner}, Senhor. "
                        f"Uma mente brilhante, devo dizer.")

        # ── ENSINAR INGLÊS ──────────────────────
        elif any(w in tl for w in ["ensina inglês", "ensinar inglês",
                                    "teach me english", "aula de inglês",
                                    "quero aprender inglês", "help me learn english"]):
            resp = ai_chat([{"role": "user",
                "content": ("I want to learn English. Give me a short lesson "
                             "with 5 useful phrases, their pronunciation tip, "
                             "and translation to Portuguese.")}], "en")

        # ── TRADUZIR ────────────────────────────
        elif any(w in tl for w in ["traduz", "traduzir", "translate",
                                    "em inglês", "em português",
                                    "in english", "in portuguese"]):
            if lang == "en":
                resp = ai_chat([{"role": "user",
                    "content": f"Translate this to Portuguese and explain: {text}"}], "en")
            else:
                resp = ai_chat([{"role": "user",
                    "content": f"Traduza para inglês e explique: {text}"}], "pt")

        # ── FALAR EM INGLÊS ─────────────────────
        elif any(w in tl for w in ["fala inglês", "fale inglês",
                                    "speak english", "responde em inglês",
                                    "answer in english"]):
            ST["lang"] = "en"
            resp = "Switching to English mode, Sir. Feel free to speak in English now."

        elif any(w in tl for w in ["fala português", "voltar para português",
                                    "speak portuguese", "back to portuguese"]):
            ST["lang"] = "pt"
            resp = "Voltando para o português, Senhor."

        # ── IA GERAL ────────────────────────────
        else:
            hist = []
            for c in MEM.get("conversations", [])[-15:]:
                if c.get("user"):
                    hist.append({"role": "user", "content": c["user"]})
                if c.get("assistant"):
                    hist.append({"role": "assistant", "content": c["assistant"]})

            sys_extra = build_system(lang)
            facts = MEM.get("facts", {})
            if facts:
                fatos = "; ".join(v["content"] for v in list(facts.values())[-6:])
                sys_extra += f"\nFatos sobre o Senhor: {fatos}"
            plans = [p for p in MEM.get("plans", []) if not p.get("done")]
            if plans:
                sys_extra += ("\nPlanos ativos: " +
                              ", ".join(p["title"] for p in plans[:5]))

            resp = ai_chat(hist, lang)

    except Exception as e:
        log.error(f"process_command: {e}", exc_info=True)
        resp = (f"An error occurred, Sir: {str(e)[:80]}"
                if lang == "en"
                else f"Ocorreu um erro, Senhor: {str(e)[:80]}")

    # Salva resposta na memória
    entry["assistant"] = resp
    save_mem()

    ST["thinking"] = False
    threading.Thread(target=speak, args=(resp,), daemon=True).start()
    return resp

# ══════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════
def jarvis_init():
    log.info("=== JARVIS INICIALIZANDO ===")
    ST["initialized"] = True
    ST["active"]      = True

    try:
        sio.emit("jarvis_state",      {"state": "initializing"})
        sio.emit("jarvis_initialized", {})
    except Exception:
        pass

    # Música aleatória
    keys = list(MUSIC_URLS.keys())
    intro_cfg = CFG.get("intro_music", "random")
    chosen = (random.choice(keys) if intro_cfg == "random"
              else intro_cfg if intro_cfg in MUSIC_URLS
              else random.choice(keys))
    threading.Thread(target=play_youtube_music,
                     args=(chosen, 60), daemon=True).start()
    time.sleep(4)

    # Boas-vindas
    speak(get_greeting())

    # Clima via wttr.in (rápido, sem browser)
    city = CFG.get("city", "Piracicaba")
    try:
        clima_raw = get_weather(city)
        speak(f"Clima em {city}: {clima_raw}")
    except Exception as e:
        log.error(f"Clima init: {e}")

    # Notícias
    try:
        dados = web_search("principais notícias brasil hoje")
        nots  = ai_chat([{"role": "user",
            "content": f"Notícias: {dados}. 2 manchetes bem curtas."}])
        speak(nots)
    except Exception as e:
        log.error(f"Notícias init: {e}")

    wake = CFG.get("wake_word", "jarvis")
    speak(f"Diga '{wake}' para me chamar a qualquer momento, Senhor.")

    try:
        sio.emit("jarvis_state", {"state": "idle"})
    except Exception:
        pass

    threading.Thread(target=wake_word_loop,
                     daemon=True, name="WakeWord").start()

# ══════════════════════════════════════
# ROTAS HTTP
# ══════════════════════════════════════
@app.route("/")
def route_index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")

@app.route("/api/config", methods=["GET"])
def route_cfg_get():
    safe = {k: v for k, v in CFG.items()
            if "key" not in k and "token" not in k}
    return jsonify(safe)

@app.route("/api/config", methods=["POST"])
def route_cfg_set():
    global CFG
    data = request.get_json(force=True) or {}
    for k, v in data.items():
        if v != "":
            CFG[k] = v
    save_config(CFG)
    return jsonify({"ok": True})

@app.route("/api/initialize", methods=["POST"])
def route_init():
    if not ST["initialized"]:
        threading.Thread(target=jarvis_init, daemon=True, name="Init").start()
    return jsonify({"ok": True})

@app.route("/api/command", methods=["POST"])
def route_command():
    data = request.get_json(force=True) or {}
    txt  = (data.get("text") or "").strip()
    if not txt:
        return jsonify({"error": "vazio"}), 400
    threading.Thread(target=process_command, args=(txt,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/listen", methods=["POST"])
def route_listen():
    def _do():
        ST["listening"] = True
        sio.emit("jarvis_state", {"state": "listening"})
        cmd = listen_once(timeout=10)
        ST["listening"] = False
        if cmd:
            process_command(cmd)
        else:
            speak("Não ouvi nada, Senhor.")
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/mute", methods=["POST"])
def route_mute():
    data        = request.get_json(force=True) or {}
    ST["muted"] = data.get("muted", not ST["muted"])
    return jsonify({"muted": ST["muted"]})

@app.route("/api/state", methods=["GET"])
def route_state():
    return jsonify(ST)

@app.route("/api/memory", methods=["GET"])
def route_memory():
    return jsonify({
        "conversations": len(MEM.get("conversations", [])),
        "facts":         len(MEM.get("facts", {})),
        "plans":         len(MEM.get("plans", [])),
        "facts_list":    list(MEM.get("facts", {}).keys())[:10],
    })

@app.route("/api/memory/facts", methods=["GET"])
def route_facts():
    return jsonify(MEM.get("facts", {}))

@app.route("/api/plans", methods=["GET"])
def route_plans():
    return jsonify(MEM.get("plans", []))

@app.route("/api/vision/screen", methods=["GET"])
def route_screen():
    img = capture_screen()
    if img:
        return jsonify({"image": img})
    return jsonify({"error": "Captura falhou. Verifique permissões."}), 500

@app.route("/api/vision/camera/start", methods=["POST"])
def route_cam_start():
    global _cam_on
    if ST["camera_on"]:
        return jsonify({"ok": True, "msg": "já ativa"})
    _cam_on = True
    ST["camera_on"] = True
    threading.Thread(target=_camera_loop, daemon=True, name="CamStream").start()
    return jsonify({"ok": True})

@app.route("/api/vision/camera/stop", methods=["POST"])
def route_cam_stop():
    global _cam_on
    _cam_on = False
    ST["camera_on"] = False
    return jsonify({"ok": True})

@app.route("/api/vision/camera/snap", methods=["GET"])
def route_cam_snap():
    """Captura único frame da câmera e retorna base64."""
    b64 = capture_camera_frame()
    if b64:
        return jsonify({"image": b64})
    return jsonify({"error": "Câmera não encontrada"}), 500

@app.route("/api/interrupt", methods=["POST"])
def route_interrupt():
    """Para qualquer fala em andamento."""
    global _sapi
    try:
        if _sapi:
            _sapi.Skip("Sentence", 1000)   # pula sentenças pendentes
            _sapi.Speak("", 3)              # flag 3 = async + purge buffer
    except Exception:
        pass
    # Esvazia a fila TTS
    while not _tts_q.empty():
        try:
            _tts_q.get_nowait()
            _tts_q.task_done()
        except Exception:
            break
    ST["speaking"] = False
    try:
        sio.emit("jarvis_state", {"state": "idle"})
        sio.emit("jarvis_interrupted", {})
    except Exception:
        pass
    return jsonify({"ok": True})

@sio.on("connect")
def on_connect():
    emit("jarvis_state",
         {"state": "idle" if ST["active"] else "waiting_clap"})
    if ST["initialized"]:
        emit("jarvis_initialized", {})
    log.info("Frontend conectado")

@sio.on("command")
def on_ws_cmd(data):
    txt = (data.get("text") or "").strip()
    if txt:
        threading.Thread(target=process_command, args=(txt,), daemon=True).start()

@sio.on("initialize")
def on_ws_init(data=None):
    if not ST["initialized"]:
        threading.Thread(target=jarvis_init, daemon=True, name="Init").start()

# ══════════════════════════════════════
# MAIN
# ══════════════════════════════════════
def main():
    print("\n" + "="*58)
    print("   J . A . R . V . I . S   —   v6")
    print("   Criado por Senhor Victor")
    print("="*58)
    print("   http://localhost:5000")
    print("   2 palmas → ativa | 'jarvis' → wake word")
    print("   Bilíngue: PT-BR e EN-US")
    print("="*58 + "\n")
    init_sr()
    threading.Thread(target=start_clap_detection,
                     daemon=True, name="Clap").start()
    sio.run(app, host="0.0.0.0", port=5000,
            debug=False, use_reloader=False,
            allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()
