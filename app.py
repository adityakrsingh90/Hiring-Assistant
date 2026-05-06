# app.py
import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
import pdfplumber
import docx
import tempfile
from dotenv import load_dotenv
import os
import firebase_admin
from firebase_admin import credentials, firestore
import textwrap
import time


# if not firebase_admin._apps:
#     cred = credentials.Certificate(dict(st.secrets["firebase"]))
#     firebase_admin.initialize_app(cred)

# ----------------------------
#   Configuration & Constants
# ----------------------------
load_dotenv()

# Localhost (.env)
API_KEY = os.getenv("GOOGLE_API_KEY")

# Streamlit Cloud (Secrets)
if not API_KEY:
    API_KEY = st.secrets.get("GOOGLE_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)

GEMINI_MODEL_NAME = "gemini-2.5-flash" 

MAX_RESUME_CHARS = 5000
MAX_JD_CHARS = 2000
MAX_CHAT_HISTORY = 10 

# ----------------------------
#   Helper: Modern UI CSS (Styling Only)
# ----------------------------
def inject_custom_css():
    st.markdown("""
    <style>
        /* Import Font */
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

        /* Global Font Setting */
        html, body, [class*="css"], .stApp {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
        }

        /* --- HEADERS --- */
        .main-title {
            background: linear-gradient(135deg, #4F46E5 0%, #06B6D4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.8rem;
            font-weight: 800;
            text-align: center;
            margin-bottom: 0.5rem;
        }
        .sub-title {
            text-align: center;
            color: #64748B;
            font-size: 1.1rem;
            margin-bottom: 2.5rem;
        }

        /* --- CARDS --- */
        .css-card {
            background-color: #FFFFFF;
            padding: 2rem;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            border: 1px solid #F1F5F9;
            margin-bottom: 1.5rem;
        }

        /* --- INPUT FIELDS STYLING --- */
        /* Making inputs look cleaner */
        .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
            border-radius: 10px !important;
            border: 1px solid #E2E8F0 !important;
            padding: 10px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        
        /* Focus effect */
        .stTextInput input:focus, .stTextArea textarea:focus {
            border-color: #4F46E5 !important;
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1) !important;
        }

        /* --- BUTTONS --- */
        .stButton button {
            background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%) !important;
            color: white !important;
            border: none !important;
            padding: 0.6rem 1.2rem !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 4px 6px rgba(79, 70, 229, 0.2);
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 15px rgba(79, 70, 229, 0.3);
        }

        /* --- CHAT INTERFACE --- */
        .chat-container {
            background-color: #FFFFFF;
            border: 1px solid #F1F5F9;
            border-radius: 16px;
            padding: 20px;
            height: 500px;
            overflow-y: auto;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.02);
        }
                
        /* --- DROPDOWN / SELECTBOX FIX (Important) --- */
        div[data-baseweb="select"] > div {
            background-color: #262730 !important; /* Dark Background */
            color: #FFFFFF !important; /* White Text */
            border: 1px solid #4F46E5 !important;
            border-radius: 10px !important;
        }
        
        /* Dropdown ke andar ka text force White */
        div[data-baseweb="select"] span {
            color: #FFFFFF !important;
        }
        
        /* Dropdown arrow icon color */
        div[data-baseweb="select"] svg {
            fill: #FFFFFF !important;
        }
        
        }

        /* User Message (Right) */
        .user-msg {
            background: linear-gradient(135deg, #4F46E5, #6366F1);
            color: black !important;
            padding: 12px 16px;
            border-radius: 16px 16px 2px 16px;
            max-width: 80%;
            margin-bottom: 12px;
            float: right;
            clear: both;
            box-shadow: 0 4px 6px rgba(79, 70, 229, 0.2);
            font-size: 0.95rem;
        }

        /* Bot Message (Left) */
        .bot-msg {
            background-color: #F8FAFC;
            color: #1E293B !important;
            padding: 12px 16px;
            border-radius: 16px 16px 16px 2px;
            max-width: 80%;
            margin-bottom: 12px;
            float: left;
            clear: both;
            border: 1px solid #E2E8F0;
            font-size: 0.95rem;
        }
        
        .chat-avatar {
            margin-right: 8px;
            font-size: 1.1rem;
        }

    </style>
    """, unsafe_allow_html=True)


# ----------------------------
#   Initialize Firebase & Gemini
# ----------------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            # Streamlit Cloud
            if os.path.exists(".streamlit/secrets.toml"):
                cred = credentials.Certificate(dict(st.secrets["firebase"]))

            # Localhost
            else:
                cred = credentials.Certificate("serviceAccountKey.json")

            firebase_admin.initialize_app(cred)

        except Exception as e:
            st.error(f"Firebase initialization failed: {e}")
            st.stop()

    return firestore.client()

@st.cache_resource
def init_gemini():
    if not API_KEY:
        st.error("GOOGLE_API_KEY missing from .env")
        st.stop()
    return genai.GenerativeModel(GEMINI_MODEL_NAME)

# ----------------------------
#   Utilities
# ----------------------------
def extract_resume_text_from_file(uploaded_file):
    text = ""
    if uploaded_file is None: return ""
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        if uploaded_file.name.endswith(".pdf"):
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    content = page.extract_text()
                    if content: text += content + "\n"
        elif uploaded_file.name.endswith(".docx"):
            doc = docx.Document(tmp_path)
            for para in doc.paragraphs: text += para.text + "\n"
        else:
            with open(tmp_path, "r", errors="ignore") as f: text = f.read()
    except Exception as e:
        st.warning(f"Error extracting text: {e}")
        text = ""
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path): os.remove(tmp_path)
    return text.strip()

def safe_truncate(text, limit):
    return text if len(text) <= limit else text[:limit]

def get_language_code(language_name):
    mapping = {"English": "en", "Hindi": "hi", "Spanish": "es", "French": "fr", "German": "de"}
    return mapping.get(language_name, "en")

def generate_response_in_language(model, prompt, language_code="en"):
    mapping = {"en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French", "de": "German"}
    lang_name = mapping.get(language_code, 'English')
    instruction = f"Respond professionally and only in {lang_name}. Use clear headings/bullets."
    try:
        response = model.generate_content(instruction + "\n" + prompt)
        return getattr(response, "text", "⚠️ Could not generate response.")
    except Exception as e:
        return f"⚠️ Error: {e}"

# ----------------------------
#   Chatbot Logic
# ----------------------------
def setup_interview_chat(model, resume_text, jd, language_code):
    if "chat_history" not in st.session_state or st.session_state.chat_history_id != (resume_text, jd):
        st.session_state.chat_history = []
        st.session_state.chat_history_id = (resume_text, jd)
        
        system_instruction = f"""
        You are an experienced technical interviewer.
        Candidate Resume: {safe_truncate(resume_text, 1500)}
        Job Description: {safe_truncate(jd, 1000)}
        Language: {language_code.upper()} 
        Start by welcoming the candidate and asking an opening question based on their resume. Keep it concise.
        """
        first_question = generate_response_in_language(model, system_instruction, language_code)
        st.session_state.chat_history.append({"role": "assistant", "content": first_question})

def generate_chat_response(model, user_input, resume_text, jd, language_code):
    system_instruction = f"""
    You are a technical interviewer. Maintain persona. Ask relevant questions.
    Candidate Resume: {safe_truncate(resume_text, 1500)}
    Job Description: {safe_truncate(jd, 1000)}
    Language: {language_code.upper()} 
    History: {textwrap.fill(" ".join([f"[{msg['role']}] {msg['content']}" for msg in st.session_state.chat_history]), 2000)}
    """
    full_prompt = system_instruction + f"\n\nCandidate Response: {user_input}"
    return generate_response_in_language(model, full_prompt, language_code)

# ----------------------------
#   AUTH PAGE (Corrected)
# ----------------------------
def auth_page(db):
    inject_custom_css()
    
    # Layout: Centered Column
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 class='main-title'>TalentScout 🤖</h1>", unsafe_allow_html=True)
        st.markdown("<p class='sub-title'>AI-Powered Candidate Vetting & Interview System</p>", unsafe_allow_html=True)
        
        # Tabs directly (No extra div wrapper)
        tab1, tab2 = st.tabs(["🔒 Login", "✍️ Register"])
        
        with tab1:
            with st.form("login_form"):
                st.markdown("### Welcome Back")
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                st.markdown("<br>", unsafe_allow_html=True)
                btn = st.form_submit_button("Sign In")

            if btn:
                user = db.collection("users").document(username).get()
                if user.exists and user.to_dict()["password"] == password:
                    st.success("Login Successful!")
                    st.session_state.logged_in = True
                    st.session_state.user_id = username
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

        with tab2:
            with st.form("register_form"):
                st.markdown("### New Account")
                username = st.text_input("Username", key="reg_username")
                password = st.text_input("Password", type="password", key="reg_password")
                st.markdown("<br>", unsafe_allow_html=True)
                btn = st.form_submit_button("Create Account")

            if btn:
                if username and password:
                    doc_ref = db.collection("users").document(username)
                    if doc_ref.get().exists:
                        st.error("Username taken.")
                    else:
                        doc_ref.set({"password": password, "created_at": firestore.SERVER_TIMESTAMP})
                        st.success("Account created! Please log in.")
                else:
                    st.warning("All fields are required.")

# ----------------------------
#   DASHBOARD
# ----------------------------
def dashboard_app(db, model):
    inject_custom_css()

    # --- Sidebar for User Profile & Actions ---
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=80)
        st.title("User Profile")
        st.markdown(f"👤 **{st.session_state.user_id}**")
        st.markdown("---")
        st.markdown("Use the main panel to upload resumes and analyze candidates.")
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

    # --- Main Header ---
    st.markdown("<h1 class='main-title'>Hiring Assistant</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-title'>Streamline your recruitment process with AI</p>", unsafe_allow_html=True)

    # --- Layout ---
    col_input, col_analysis = st.columns([0.4, 0.6], gap="large")

    if "candidate_data" not in st.session_state:
         st.session_state.candidate_data = {"name": "", "resume": "", "jd": "", "tech_stack": [], "lang": "English"}

    # --- Left Column: Input Form ---
    with col_input:
        st.markdown("### 📝 Candidate Details")
        with st.form("candidate_form"):
            file = st.file_uploader("Upload Resume (PDF/DOCX)", type=["pdf", "docx"])
            
            col_a, col_b = st.columns(2)
            with col_a:
                name = st.text_input("Full Name", value=st.session_state.candidate_data.get("name", ""))
                exp = st.number_input("Exp (Years)", 0, 50, value=st.session_state.candidate_data.get("experience", 0))
            with col_b:
                location = st.text_input("Location", value=st.session_state.candidate_data.get("location", ""))
                qualification = st.selectbox("Qualification", ["Bachelor's", "Master's", "PhD", "Diploma"], index=0)
            
            position = st.text_input("Target Position", value=st.session_state.candidate_data.get("position", ""))
            tech_stack = st.text_area("Tech Stack", value=", ".join(st.session_state.candidate_data.get("tech_stack", [])), help="e.g. Python, SQL")
            jd = st.text_area("Job Description (JD)", value=st.session_state.candidate_data.get("jd", ""), height=150)
            
            lang = st.selectbox("Language", ["English", "Hindi", "Spanish", "French", "German"])
            
            st.markdown("<br>", unsafe_allow_html=True)
            submit_btn = st.form_submit_button("🚀 Analyze Candidate", use_container_width=True)

    resume_text = extract_resume_text_from_file(file) if file else st.session_state.candidate_data.get("resume", "")

    # --- Right Column: Analysis & Chat ---
    with col_analysis:
        # Processing Logic
        if submit_btn:
            if not name or not jd:
                st.error("⚠️ Name and JD are required!")
            else:
                st.session_state.candidate_data.update({
                    "name": name, "experience": exp, "position": position, "location": location,
                    "qualification": qualification, "tech_stack": [t.strip() for t in tech_stack.split(",") if t.strip()],
                    "resume": resume_text, "jd": jd, "lang": lang
                })
                try:
                    db.collection("candidates").document(name).set(st.session_state.candidate_data)
                    st.toast(f"Candidate {name} saved successfully!", icon="✅")
                except Exception as e:
                    st.error(f"Save error: {e}")

        c_data = st.session_state.candidate_data
        
        # Tabs for Analysis vs Chat
        tab_analysis, tab_chat = st.tabs(["📊 Analysis & Match", "💬 AI Interviewer"])

        # --- Tab 1: Analysis ---
        with tab_analysis:
            if c_data.get("jd"):
                lang_code = get_language_code(c_data.get("lang", "English"))
                
                st.info(f"Analyzing for **{c_data['name']}** - {c_data['position']}")
                
                col_x, col_y = st.columns(2)
                with col_x:
                    if st.button("📄 Generate JD Summary", use_container_width=True):
                        with st.spinner("Summarizing..."):
                            prompt = f"Summarize this role in 3 sentences and list 5 key skills.\nJD: {safe_truncate(c_data['jd'], 2000)}"
                            res = generate_response_in_language(model, prompt, lang_code)
                            st.markdown(f"**Summary:**\n{res}")
                
                with col_y:
                    if c_data.get("resume") and st.button("🎯 Calculate Match Score", use_container_width=True):
                        with st.spinner("Matching..."):
                            prompt = f"Compare Resume & JD. Give Match %(0-100), Strengths, Gaps.\nResume: {safe_truncate(c_data['resume'], 3000)}\nJD: {safe_truncate(c_data['jd'], 2000)}"
                            res = generate_response_in_language(model, prompt, lang_code)
                            st.success(res)
                
                st.markdown("### 🧠 Generated Questions")
                for tech in c_data.get("tech_stack", []):
                    with st.expander(f"Questions for {tech}"):
                        if st.button(f"Generate {tech} Qs", key=f"btn_{tech}"):
                            prompt = f"4 Interview questions & answers for {tech}."
                            st.write(generate_response_in_language(model, prompt, lang_code))

        # --- Tab 2: Chat Simulation ---
        with tab_chat:
            if c_data.get("name") and c_data.get("jd"):
                setup_interview_chat(model, c_data["resume"], c_data["jd"], get_language_code(c_data["lang"]))
                
                # --- FIXED CHAT DISPLAY LOGIC ---
                # Hum poora HTML ek variable mein store karenge
                chat_html = '<div class="chat-container">'
                
                for msg in st.session_state.chat_history:
                    if msg["role"] == "assistant":
                        chat_html += f'''
                        <div class="bot-msg">
                            <span class="chat-avatar">🤖</span> {msg["content"]}
                        </div>
                        '''
                    else:
                        chat_html += f'''
                        <div class="user-msg">
                             {msg["content"]} <span class="chat-avatar">👨‍💻</span>
                        </div>
                        '''
                
                chat_html += '</div>'
                
                # Ek hi baar render karenge taaki box na toote
                st.markdown(chat_html, unsafe_allow_html=True)

                # Chat Input Form
                st.write("") # Spacer
                with st.form(key="chat_form", clear_on_submit=True):
                    cols = st.columns([0.85, 0.15])
                    with cols[0]:
                        user_input = st.text_input("Type your answer...", key="chat_input_widget", label_visibility="collapsed")
                    with cols[1]:
                        submit_chat = st.form_submit_button("Send", use_container_width=True)

                if submit_chat and user_input:
                    st.session_state.chat_history.append({"role": "user", "content": user_input})
                    with st.spinner("Interviewer is thinking..."):
                        response = generate_chat_response(model, user_input, c_data["resume"], c_data["jd"], get_language_code(c_data["lang"]))
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                        st.session_state.chat_history = st.session_state.chat_history[-MAX_CHAT_HISTORY:]
                        st.rerun()

                if st.button("🔄 Reset Interview"):
                    del st.session_state.chat_history
                    st.rerun()
            else:
                st.warning("Please submit candidate details in the left panel first.")

# ----------------------------
#   MAIN
# ----------------------------
def main():
    # Streamlit Config set first
    st.set_page_config(page_title="TalentScout AI", layout="wide", page_icon="🤖")
    
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    
    db = init_firebase()
    model = init_gemini()

    if st.session_state.logged_in:
        dashboard_app(db, model)
    else:
        auth_page(db)

if __name__ == "__main__":
    main()