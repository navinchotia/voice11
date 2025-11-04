import streamlit as st
import google.generativeai as genai
from gtts import gTTS
import tempfile
import base64
import re
import os
from elevenlabs.client import ElevenLabs

# ------------------------------
# CONFIGURATION
# ------------------------------
st.set_page_config(page_title="Neha - Hindi Chatbot", page_icon="💬")

# --- Set your ElevenLabs API key ---
ELEVEN_API_KEY = st.secrets.get("ELEVEN_API_KEY", None)

# --- Google Gemini Configuration ---
genai.configure(api_key=st.secrets.get("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

# ------------------------------
# CHAT MEMORY INITIALIZATION
# ------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# ------------------------------
# STYLING
# ------------------------------
st.markdown("""
<style>
  .stApp { background-color: #e5ddd5; font-family: 'Roboto', sans-serif !important; }
  h1 { text-align: center; font-weight: 500; font-size: 16px; margin-top: -10px; }
  iframe { margin: 1px 0 !important; }
</style>
""", unsafe_allow_html=True)

st.title("💬 Neha - Your Hindi Chat Friend")

# ------------------------------
# FUNCTION: Generate Neha's Reply
# ------------------------------
def generate_reply(memory, user_input):
    try:
        prompt = f"Neha is a friendly Hindi-speaking girl. Reply in Hinglish (Roman Hindi only, no Devanagari). Be casual and natural.\nUser: {user_input}\nNeha:"
        model = genai.GenerativeModel(MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Reply issue: {e}")
        return "Sorry, mujhe thoda issue hua reply karne mein."

# ------------------------------
# FUNCTION: ElevenLabs + gTTS Fallback Speech
# ------------------------------
@st.cache_data(show_spinner=False)
def text_to_speech(text):
    """
    Generate speech using ElevenLabs (preferred) and fallback to gTTS if needed.
    """
    clean_text = re.sub(r'[^\w\s,?.!]', '', text)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

    # --- Try ElevenLabs First ---
    if client:
        try:
            response = client.text_to_speech.convert(
                voice_id="EXAVITQu4vr4xnSDxMaL",  # You can change to any valid voice ID
                model_id="eleven_multilingual_v2",
                text=clean_text
            )

            with open(temp_file.name, "wb") as f:
                for chunk in response:
                    f.write(chunk)

            if os.path.getsize(temp_file.name) == 0:
                raise ValueError("Empty ElevenLabs audio")

            return temp_file.name

        except Exception as e:
            st.warning(f"ElevenLabs issue: {e}. Using gTTS fallback...")

    # --- Fallback to gTTS ---
    try:
        tts = gTTS(text=clean_text, lang="hi", tld='co.in', slow=False)
        tts.save(temp_file.name)
        return temp_file.name
    except Exception as e:
        st.error(f"TTS Fallback issue: {e}")
        return None


# ------------------------------
# CHAT UI
# ------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role):
        st.markdown(msg["content"])

# ------------------------------
# USER INPUT
# ------------------------------
user_input = st.chat_input("Kuch likho...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # --- Neha is typing ---
    with st.spinner("Neha type kar rahi hai... 💭"):
        reply = generate_reply(st.session_state.messages, user_input)

    # Clean reply if model includes "Neha:"
    if reply.strip().lower().startswith("neha:"):
        reply = reply.split(":", 1)[1].strip()

    # --- Display Neha's message ---
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)

        # --- Add voice output ---
        audio_path = text_to_speech(reply)
        if audio_path:
            audio_bytes = open(audio_path, "rb").read()
            audio_base64 = base64.b64encode(audio_bytes).decode()
            st.markdown(
                f"""
                <audio controls style='margin-top:-6px;'>
                    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                </audio>
                """,
                unsafe_allow_html=True
            )
        else:
            st.warning("No audio generated.")



