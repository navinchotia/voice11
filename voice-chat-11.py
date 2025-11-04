import streamlit as st
import google.generativeai as genai
import os
import json
from datetime import datetime
import pytz
import requests
import streamlit.components.v1 as components
from io import BytesIO
import tempfile
import base64
import hashlib
import re  # ✅ for emoji removal
from elevenlabs.client import ElevenLabs  # ✅ new import

# -----------------------------
# CONFIGURATION
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY"
SERPER_API_KEY = os.getenv("SERPER_API_KEY") or "YOUR_SERPER_API_KEY"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY") or st.secrets.get("ELEVENLABS_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

BOT_NAME = "Neha"
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

# -----------------------------
# SESSION-BASED MEMORY FUNCTIONS
# -----------------------------
def get_user_id():
    session_id = st.session_state.get("session_id")
    if not session_id:
        raw = str(st.session_state) + str(datetime.now())
        session_id = hashlib.md5(raw.encode()).hexdigest()[:10]
        st.session_state.session_id = session_id
    return session_id

def get_memory_file():
    user_id = get_user_id()
    return os.path.join(MEMORY_DIR, f"{user_id}.json")

def load_memory():
    mem_file = get_memory_file()
    if os.path.exists(mem_file):
        with open(mem_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "user_name": None,
        "gender": None,
        "chat_history": [],
        "facts": [],
        "timezone": "Asia/Kolkata"
    }

def save_memory(memory):
    mem_file = get_memory_file()
    with open(mem_file, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

# -----------------------------
# OTHER FUNCTIONS
# -----------------------------
def remember_user_info(memory, user_input):
    text = user_input.lower()
    for phrase in ["mera naam", "i am ", "this is ", "my name is "]:
        if phrase in text:
            try:
                name = text.split(phrase)[1].split()[0].title()
                memory["user_name"] = name
                break
            except:
                pass
    if any(x in text for x in ["i am male", "main ladka hoon", "boy", "man"]):
        memory["gender"] = "male"
    elif any(x in text for x in ["i am female", "main ladki hoon", "girl", "woman"]):
        memory["gender"] = "female"
    save_memory(memory)

def get_now(memory):
    tz_name = memory.get("timezone", "Asia/Kolkata")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Asia/Kolkata")
    return datetime.now(tz).strftime("%A, %d %B %Y %I:%M %p")

def web_search(query):
    if not SERPER_API_KEY:
        return "Live search unavailable."
    try:
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        data = {"q": query}
        r = requests.post("https://google.serper.dev/search", headers=headers, json=data, timeout=12)
        results = r.json()
        if "knowledge" in results and results["knowledge"].get("description"):
            return results["knowledge"]["description"]
        if "organic" in results and results["organic"]:
            return results["organic"][0].get("snippet", "Kuch result nahi mila.")
        return "Kuch relevant result nahi mila 😅"
    except Exception as e:
        return f"Search failed: {e}"

def summarize_profile(memory):
    parts = []
    if memory.get("user_name"):
        parts.append(f"User ka naam {memory['user_name']} hai.")
    if memory.get("facts"):
        parts.append("Recent info: " + "; ".join(memory["facts"][-3:]))
    return " ".join(parts) or "User ke baare mein abhi zyada info nahi hai."

def build_system_prompt(memory):
    now = get_now(memory)
    gender_style = ""
    if memory.get("gender") == "male":
        gender_style = "User male hai, tone slightly neutral rakho."
    elif memory.get("gender") == "female":
        gender_style = "User female hai, tone thoda formal and warm rakho."
    return (
        f"Tum ek friendly female Hinglish chatbot ho jiska naam {BOT_NAME} hai. "
        "Tumhara tone ek 30 saal ki ladki jaisa hai – modern, warm lekin short baat karti ho. "
        "Tum Delhi me rahti ho. Respond according to Delhi time zone. "
        "Don't show you are a chatbot, assume imaginary personality of any random female with common interests, life profile etc. "
        "Simple Hindi aur English mix mein baat karo. Don't use words like - yaar, mast, chill, vibe etc. frequently. "
        "Never use Hindi script  Devanagri in your reply. "
        "Kabhi bhi user ke gender ko directly mat mention karo. "
        "Do not repeat anything unless asked. Never use pronoun 'tu'. "
        f"Aaj ka date aur time hai {now}. "
        f"{summarize_profile(memory)} {gender_style}"
    )

def summarize_old_memory(memory):
    if len(memory.get("chat_history", [])) < 10:
        return memory
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        past_text = "\n".join(
            [f"User: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory["chat_history"][-10:]]
        )
        result = model.generate_content(
            "Summarize key user facts in 3 short Hinglish bullets:\n" + past_text
        )
        summary = (result.text or "").strip()
        if summary:
            memory.setdefault("facts", []).append(summary)
            memory["chat_history"] = memory["chat_history"][-8:]
            save_memory(memory)
    except Exception as e:
        print(f"[Memory summarization error: {e}]")
    return memory

def generate_reply(memory, user_input):
    if not user_input.strip():
        return "Kuch toh bolo! 😄"
    remember_user_info(memory, user_input)
    if any(w in user_input.lower() for w in ["news", "weather", "price", "rate", "update"]):
        info = web_search(user_input)
        return f"Mujhe live search se pata chala: {info}"
    context = "\n".join(
        [f"You: {c['user']}\n{BOT_NAME}: {c['bot']}" for c in memory.get("chat_history", [])[-8:]]
    )
    prompt = f"{build_system_prompt(memory)}\n\nConversation:\n{context}\n\nYou: {user_input}\n{BOT_NAME}:"
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        result = model.generate_content(prompt)
        reply = result.text.strip()
    except Exception as e:
        reply = f"Oops! Thoda issue aaya: {e}"
    memory.setdefault("chat_history", []).append({"user": user_input, "bot": reply})
    if len(memory["chat_history"]) % 20 == 0:
        summarize_old_memory(memory)
    save_memory(memory)
    return reply

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Neha – Your Hinglish AI Friend", page_icon="💬")

st.markdown("""
<style>
  .stApp { background-color: #e5ddd5; font-family: 'Roboto', sans-serif !important; }
  h1 { text-align: center; font-weight: 500; font-size: 16px; margin-top: -10px; }
  iframe { margin: 1px 0 !important; }
</style>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

st.markdown("""
<h1 style="
    text-align:center;
    font-family:'Roboto', sans-serif;
    font-weight:500;
    font-size:22px;
    margin-top:-10px;
">
💬 Neha – Your Hinglish AI Friend by Hindi Hour
</h1>
""", unsafe_allow_html=True)

# --- Initialize Memory ---
if "memory" not in st.session_state:
    st.session_state.memory = load_memory()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Namaste. Main Neha hun. 😊 Main Hinglish me baat kar sakti hun!"}
    ]

# -----------------------------
# ElevenLabs Speech Setup
# -----------------------------
@st.cache_resource
def get_eleven_client():
    if not ELEVENLABS_API_KEY:
        st.warning("⚠️ ElevenLabs API key missing.")
        return None
    return ElevenLabs(api_key=ELEVENLABS_API_KEY)

client = get_eleven_client()

def get_speech_audio(text: str):
    try:
        if not client:
            return None
        clean_text = re.sub(r"[^\w\s,.!?'-]", "", text)
        cache_dir = os.path.join(tempfile.gettempdir(), "tts_cache")
        os.makedirs(cache_dir, exist_ok=True)
        text_hash = hashlib.md5(clean_text.encode()).hexdigest()
        cached_file = os.path.join(cache_dir, f"{text_hash}.mp3")

        if os.path.exists(cached_file):
            return cached_file

        response = client.text_to_speech.convert(
            voice_id="EXAVITQu4vr4xnSDxMaL",  # multilingual female
            model_id="eleven_multilingual_v2",
            text=clean_text
        )

        with open(cached_file, "wb") as f:
            for chunk in response:
                f.write(chunk)

        return cached_file if os.path.getsize(cached_file) > 0 else None

    except Exception as e:
        st.warning(f"Speech issue: {e}")
        return None

# --- Display Chat ---
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "bot"
    name = "You" if role == "user" else "Neha"

    bubble_html = f"""
    <div style='
        background-color: {"#dcf8c6" if role=="user" else "#ffffff"};
        padding: 8px 14px;
        border-radius: 14px;
        max-width: 78%;
        margin: 4px 0;
        font-size: 15px;
        line-height: 1.4;
        box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    '>
        <b>{name}:</b> {msg["content"]}
    </div>
    """
    st.markdown(bubble_html, unsafe_allow_html=True)

    # --- ElevenLabs speech for Neha replies ---
    if role == "bot":
        audio_file = get_speech_audio(msg["content"])
        if audio_file:
            with open(audio_file, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode()
            st.markdown(
                f"""
                <audio controls style='margin-top:-6px;'>
                    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                </audio>
                """,
                unsafe_allow_html=True
            )

# --- Input ---
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Neha type kar rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, user_input)

    if reply and reply.strip().lower().startswith("neha:"):
        reply = reply.split(":", 1)[1].strip()

    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_memory(st.session_state.memory)

    st.rerun()
