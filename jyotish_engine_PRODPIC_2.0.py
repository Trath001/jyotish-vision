import streamlit as st
from google import genai
import swisseph as swe
import datetime
import time
from PIL import Image, ImageEnhance, ImageOps
import json
import re

# --- CONFIGURATION ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

# --- 1. ROBUST API HANDLER (With Retry) ---
def call_gemini_with_retry(client, prompt, image, retries=3):
    for i in range(retries):
        try:
            resp = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=[prompt, image]
            )
            return resp.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(3)
                continue
            return f"ERROR: {str(e)}"
    return "ERROR_QUOTA"

# --- 2. THEME: "DARK MATTER" (Final CSS Fix) ---
def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Inter:wght@300;400;600&display=swap');

        /* MAIN APP CONTAINER */
        .stApp {
            background-color: #020617; /* Slate-950 */
            color: #f8fafc; /* Slate-50 */
            font-family: 'Inter', sans-serif;
        }

        /* HEADERS (Gold) */
        h1, h2, h3 {
            font-family: 'Cinzel', serif !important;
            background: linear-gradient(to right, #fbbf24, #d97706);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700 !important;
        }

        /* --- CRITICAL UI FIXES (NO MORE WHITE BOXES) --- */
        
        /* 1. Inputs & Select Boxes (The Container) */
        div[data-baseweb="select"] > div, 
        div[data-baseweb="input"] > div {
            background-color: #1e293b !important; /* Slate-800 */
            border-color: #475569 !important;     /* Slate-600 */
            color: white !important;
        }
        
        /* 2. The Text Inside Inputs */
        input {
            color: #ffffff !important;
        }

        /* 3. The Dropdown Popup Menu (The "Invisible" Box) */
        div[data-baseweb="popover"], div[data-baseweb="menu"] {
            background-color: #0f172a !important; /* Dark Navy */
            border: 1px solid #d97706 !important; /* Gold Border */
        }
        
        /* 4. Dropdown Options */
        li[data-baseweb="menu-item"] {
            color: #e2e8f0 !important; /* Light Grey Text */
        }
        li[data-baseweb="menu-item"]:hover {
            background-color: #334155 !important; /* Highlight Color */
        }
        
        /* 5. Selected Option Text */
        div[data-baseweb="select"] span {
            color: #ffffff !important;
        }

        /* 6. File Uploader */
        div[data-testid="stFileUploader"] section {
            background-color: #1e293b !important;
            border: 1px dashed #fbbf24 !important;
        }
        div[data-testid="stFileUploader"] button {
            background-color: #334155 !important;
            color: white !important;
            border: none !important;
        }

        /* 7. Buttons (Gold Gradient) */
        div.stButton > button {
            background: linear-gradient(135deg, #d97706 0%, #92400e 100%);
            color: white !important;
            border: none;
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            transition: all 0.2s;
        }
        div.stButton > button:hover {
            transform: scale(1.02);
            box-shadow: 0 0 15px rgba(217, 119, 6, 0.4);
        }

        /* LAYOUT CARDS */
        .glass-panel {
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. ASTRO LOGIC ENGINE ---
class JyotishEngine:
    def __init__(self):
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.rashi_names = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        self.dasha_lords = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
        self.dasha_years = [7, 20, 6, 10, 7, 18, 16, 19, 17]

    def calculate_chart(self, year, month, day, hour, minute, lat, lon):
        utc_dec = (hour + minute/60.0) - 5.5
        jd = swe.julday(year, month, day, utc_dec)
        ayanamsa = swe.get_ayanamsa_ut(jd)
        planets = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        chart_data = {}
        for name, pid in planets.items():
            pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)[0][0]
            chart_data[name] = {"sign": self.rashi_names[int(pos/30)], "degree": round(pos%30, 2)}
        asc_val = (swe.houses(jd, lat, lon)[1][0] - ayanamsa) % 360
        chart_data["Ascendant"] = {"sign": self.rashi_names[int(asc_val/30)], "degree": round(asc_val%30, 2)}
        moon_abs = (self.rashi_names.index(chart_data["Moon"]["sign"]) * 30) + chart_data["Moon"]["degree"]
        nak_idx = int(moon_abs / 13.33333333)
        balance = 1 - ((moon_abs % 13.33333333) / 13.33333333)
        start_lord = nak_idx % 9
        chart_data["Current_Mahadasha"] = f"{self.dasha_lords[start_lord]} (Balance: {int(balance * self.dasha_years[start_lord])} yrs)"
        return chart_data

    def find_date_from_positions(self, observed_positions):
        valid_targets = {k: v for k, v in observed_positions.items() if v and v != "Unknown"}
        if not valid_targets: return None
        # Search window: 1900-2000
        start_date, end_date = datetime.date(1900, 1, 1), datetime.date(2000, 12, 31)
        curr, delta = start_date, datetime.timedelta(days=15)
        candidates = []
        pmap = {"Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        
        while curr <= end_date:
            jd = swe.julday(curr.year, curr.month, curr.day)
            match = True
            for p, target in valid_targets.items():
                if p in pmap:
                    pos = swe.calc_ut(jd, pmap[p], swe.FLG_SIDEREAL)[0][0]
                    if self.rashi_names[int(pos/30)].lower() != target.lower():
                        match = False; break
            if match: candidates.append(curr)
            curr += delta
            
        for cand in candidates: # Daily refinement
            d = cand - datetime.timedelta(days=20)
            limit = cand + datetime.timedelta(days=20)
            while d <= limit:
                jd = swe.julday(d.year, d.month, d.day)
                full_match = True
                for p, target in valid_targets.items():
                    pid = {"Sun":swe.SUN, "Mars":swe.MARS, "Jupiter":swe.JUPITER, "Saturn":swe.SATURN, "Rahu":swe.MEAN_NODE}.get(p)
                    if pid:
                        pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                        if self.rashi_names[int(pos/30)].lower() != target.lower():
                            full_match = False; break
                if full_match: return d
                d += datetime.timedelta(days=1)
        return None

    def generate_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        occupants = {k: [] for k in layout}
        if chart_data:
            occupants[chart_data['Ascendant']['sign']].append("Asc")
            for p, data in chart_data.items():
                if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}°")
        
        svg = [f'<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: #0f172a; border-radius: 8px;">']
        svg.append(f'<rect x="2" y="2" width="396" height="396" fill="none" stroke="#fbbf24" stroke-width="2"/>')
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="#fbbf24" stroke-width="1" stroke-opacity="0.3"/>')
            svg.append(f'<text x="{x+50}" y="{y+55}" text-anchor="middle" fill="#fbbf24" font-size="14" font-weight="bold" opacity="0.1">{sign[:3].upper()}</text>')
            if chart_data:
                for i, item in enumerate(occupants[sign]):
                    color = "#ef4444" if "Asc" in item else "#f8fafc"
                    weight = "bold" if "Asc" in item else "normal"
                    svg.append(f'<text x="{x+5}" y="{y+20+(i*15)}" fill="{color}" font-weight="{weight}" font-size="11" font-family="sans-serif">{item}</text>')
        svg.append('</svg>')
        return "".join(svg)

# --- 4. MAIN UI ---
def main():
    st.set_page_config(page_title="VedaVision Ultimate", layout="wide", page_icon="🔮")
    inject_custom_css()
    engine = JyotishEngine()
    
    # Init Session State
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'form_tob' not in st.session_state: st.session_state['form_tob'] = datetime.time(12,0)
    if 'ai_planets' not in st.session_state: st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}
    if 'chart_data' not in st.session_state: st.session_state['chart_data'] = engine.calculate_chart(1990, 1, 1, 12, 0, 21.46, 83.98)
    if 'chat_history' not in st.session_state: 
        st.session_state['chat_history'] = [{"role": "assistant", "content": "Namaste! I am your Vedic Astrology assistant. Upload a chart or enter details, and I can help you interpret it."}]

    # --- TOP BAR ---
    st.markdown("## 🔮 VedaVision Ultimate")
    st.markdown("---")

    # --- 3-COLUMN LAYOUT ---
    col1, col2, col3 = st.columns([1, 1, 1], gap="medium")

    # === COLUMN 1: THE SCANNER (INPUT) ===
    with col1:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.subheader("1. Manuscript Input")
        
        # Mode Toggle (Visible)
        mode = st.radio("Mode:", ["Paper (Text/OCR)", "Palm Leaf (Symbols)"], horizontal=True)
        uploaded = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
        
        if uploaded and st.button("👁️ SCAN DOCUMENT"):
            try:
                client = genai.Client(api_key=GOOGLE_API_KEY)
                img = Image.open(uploaded)
                st.image(img, caption="Scanning...", use_column_width=True)
                
                with st.spinner("AI Decoding..."):
                    if "Paper" in mode:
                        prompt = """
                        Analyze Paper Horoscope. Extract:
                        1. Name (Name/Namni). 2. DOB (Date/Tarikh/Odia Numerals). 3. Time (TOB/Samaya).
                        4. Rashi positions (Gu, Sha, Ra, Ma).
                        RETURN JSON: {"name": "Tx", "date": "YYYY-MM-DD", "time": "HH:MM", "positions": {"Jupiter": "Sign"}}
                        """
                    else:
                        prompt = """
                        Analyze Palm Leaf. Identify Symbols: Gu(Jup), Sha(Sat), Ra(Rahu), Ma(Mars).
                        RETURN JSON: {"positions": {"Jupiter": "Sign", "Saturn": "Sign", "Rahu": "Sign", "Mars": "Sign"}}
                        """
                    
                    resp = call_gemini_with_retry(client, prompt, img)
                    
                    if "ERROR" in resp:
                        st.error(resp)
                    else:
                        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group())
                            if data.get('name'): st.session_state['form_name'] = data['name']
                            # Fuzzy Date/Time Parsing
                            if data.get('date'):
                                try: st.session_state['form_dob'] = datetime.datetime.strptime(data['date'][:10], "%Y-%m-%d").date()
                                except: pass
                            if data.get('time'):
                                try: st.session_state['form_tob'] = datetime.datetime.strptime(data['time'], "%H:%M").time()
                                except: pass
                            
                            for p, s in data.get('positions', {}).items():
                                if s in engine.rashi_names: st.session_state['ai_planets'][p] = s
                            
                            st.success("Scan Complete!")
                            st.rerun()
            except Exception as e:
                st.error(f"System Error: {e}")

        st.markdown("---")
        st.subheader("🕵️ Date Detective")
        st.caption("If text is illegible, use planets to find the date.")
        
        ropts = ["Unknown"] + engine.rashi_names
        c_a, c_b = st.columns(2)
        with c_a:
            p_jup = st.selectbox("Jupiter", ropts, index=ropts.index(st.session_state['ai_planets'].get("Jupiter", "Unknown")))
            p_rah = st.selectbox("Rahu", ropts, index=ropts.index(st.session_state['ai_planets'].get("Rahu", "Unknown")))
        with c_b:
            p_sat = st.selectbox("Saturn", ropts, index=ropts.index(st.session_state['ai_planets'].get("Saturn", "Unknown")))
            p_mar = st.selectbox("Mars", ropts, index=ropts.index(st.session_state['ai_planets'].get("Mars", "Unknown")))
            
        if st.button("📅 CALCULATE LOST DATE"):
            found = engine.find_date_from_positions({"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar})
            if found:
                st.session_state['form_dob'] = found
                st.success(f"Found: {found}")
                st.rerun()
            else:
                st.error("No match.")
        st.markdown('</div>', unsafe_allow_html=True)

    # === COLUMN 2: THE KUNDLI (OUTPUT) ===
    with col2:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.subheader("✨ Janma Kundli")
        
        # Manual Override Form (Live Updating)
        name = st.text_input("Name", value=st.session_state['form_name'])
        
        # Date & Time (Fixed Visibility)
        d_val = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1)
        dob = st.date_input("Date of Birth", value=d_val, min_value=datetime.date(1800,1,1))
        
        t_val = st.session_state['form_tob']
        tob = st.time_input("Time of Birth", value=t_val, step=60) # Exact minutes enabled
        
        city = st.text_input("Place of Birth", value="Sambalpur")
        
        if st.button("GENERATE CHART", type="primary"):
            # Update State
            st.session_state['form_name'] = name
            st.session_state['form_dob'] = dob
            st.session_state['form_tob'] = tob
            
            # Calc
            lat, lon = (21.46, 83.98) # Geocoding placeholder
            st.session_state['chart_data'] = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
            
            # Add to chat context
            asc = st.session_state['chart_data']['Ascendant']['sign']
            st.session_state['chat_history'].append({"role": "assistant", "content": f"I have generated the chart for {name}. The Ascendant is {asc}. Ask me anything about it!"})
            st.rerun()

        # Render Chart
        st.markdown(engine.generate_svg(st.session_state['chart_data']), unsafe_allow_html=True)
        
        # Stats
        asc = st.session_state['chart_data'].get('Ascendant', {}).get('sign', '-')
        dasha = st.session_state['chart_data'].get('Current_Mahadasha', '-')
        st.info(f"**Lagna:** {asc} | **Dasha:** {dasha}")
        st.markdown('</div>', unsafe_allow_html=True)

    # === COLUMN 3: THE ASTROLOGER (CHAT) ===
    with col3:
        st.markdown('<div class="glass-panel" style="height: 800px; display: flex; flex-direction: column;">', unsafe_allow_html=True)
        st.subheader("🤖 Jyotish Mitra")
        st.caption("Ask questions about the chart...")
        
        # Chat History Container
        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state['chat_history']:
                st.chat_message(msg["role"]).write(msg["content"])
        
        # Chat Input
        if prompt := st.chat_input("Ask about career, health, etc..."):
            st.session_state['chat_history'].append({"role": "user", "content": prompt})
            
            # AI Logic (Simulated for Demo, connect to Gemini here for real)
            # You can wrap this in call_gemini_with_retry if you want real answers
            response = "I am analyzing the planetary positions for your question... (Connect Gemini here for full text response)"
            
            st.session_state['chat_history'].append({"role": "assistant", "content": response})
            st.rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
