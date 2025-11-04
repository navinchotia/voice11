import streamlit as st
import google.generativeai as genai
import os
import json
from datetime import datetime
import pytz
import requests
import streamlit.components.v1 as components
from gtts import gTTS
from io import BytesIO
import tempfile
import base64
import hashlib
import re  # ✅ added for emoji removal

# -----------------------------
# CONFIGURATION
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY"
SERPER_API_KEY = os.getenv("SERPER_API_KEY") or "YOUR_SERPER_API_KEY"
genai.configure(api_key=GEMINI_API_KEY)

BOT_NAME = "Neha"
MEMORY_DIR = "user_memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

# -----------------------------
# SESSION-BASED MEMORY FUNCTIONS
# -----------------------------
def get_user_id():
    """Create a unique ID for each user/session."""
    session_id = st.session_state.get("session_id")
    if not session_id:
        raw = str(st.session_state) + str(datetime.now())
        session_id = hashlib.md5(raw.encode()).hexdigest()[:10]
        st.session_state.session_id = session_id
    return session_id

def get_memory_file():
    """Each user has their own JSON memory file."""
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

# ---------------------
# Elevenlabs Setp
# ---------------------
def elevenlabs_tts(text):
    """Generate natural speech from text using ElevenLabs."""
    import requests, base64, os

    api_key = os.getenv("ELEVEN_API_KEY") or "YOUR_ELEVEN_API_KEY"
    voice_id = "mfMM3ijQgz8QtMeKifko"  # e.g., "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    # Clean up emojis & smileys before sending
    import re
    clean_text = re.sub(r"[^\w\s,.'!?-]", "", text)

    payload = {
        "text": clean_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.85}
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            audio_base64 = base64.b64encode(response.content).decode()
            return f"""
            <audio controls style='margin-top:-6px;'>
                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            </audio>
            """
        else:
            return f"<p style='color:red;'>Speech error: {response.text}</p>"
    except Exception as e:
        return f"<p style='color:red;'>Speech generation failed: {e}</p>"


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

st.title("💬 Neha – Your Hinglish AI Friend by Hindi Hour")

# --- Memory initialization per user ---
if "memory" not in st.session_state:
    st.session_state.memory = load_memory()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! Main Neha hoon. 😊 Main Hinglish me baat kar sakti hun!"}
    ]

# --- Display Chat with Text + Audio ---
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

 # --- Add Hindi speech for Neha’s replies (using ElevenLabs with caching) ---
if role == "bot":
    try:
        from elevenlabs import generate, set_api_key
        import base64
        import hashlib

        ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY") or "YOUR_ELEVEN_API_KEY"
        set_api_key(ELEVEN_API_KEY)

        # Clean text for TTS
        clean_text = re.sub(r'[^\w\s,.!?-]', '', msg["content"]).strip()

        # Create cache folder
        CACHE_DIR = "tts_cache"
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Unique filename hash based on the clean text
        hash_id = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{hash_id}.mp3")

        # If cached audio exists, reuse it
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as f:
                audio_bytes = f.read()
        else:
            # Generate new audio and save to cache
            audio_bytes = generate(
                text=clean_text,
                voice="Bella",  # 🔄 can replace with any Hindi+English friendly voice
                model="eleven_multilingual_v2"
            )
            with open(cache_file, "wb") as f:
                f.write(audio_bytes)

        # Convert to base64 for inline playback
        audio_base64 = base64.b64encode(audio_bytes).decode()

        st.markdown(
            f"""
            <audio controls style='margin-top:-6px;'>
                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            </audio>
            """,
            unsafe_allow_html=True
        )

    except Exception as e:
        st.warning(f"Speech issue: {e}")


# --- Input ---
user_input = st.chat_input("Type your message here...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Neha type kar rahi hai... 💭"):
        reply = generate_reply(st.session_state.memory, user_input)

    # Clean reply if model includes "Neha:" itself
    if reply and reply.strip().lower().startswith("neha:"):
        reply = reply.split(":", 1)[1].strip()

    st.session_state.messages.append({"role": "assistant", "content": reply})
    save_memory(st.session_state.memory)

    st.rerun()








