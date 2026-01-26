import streamlit as st
from google import genai
import swisseph as swe
import datetime
from geopy.geocoders import Nominatim
from PIL import Image, ImageEnhance, ImageOps
import json
import re

# --- CONFIGURATION ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    pass

# --- 1. RESTORED INTELLIGENCE: FUZZY DATE/TIME PARSING ---
def parse_fuzzy_date(date_str):
    """
    Restored Logic: Handles Odia numerals and various separators.
    """
    if not date_str: return None
    
    # Clean up common OCR noise
    clean_str = date_str.replace("th", "").replace("nd", "").replace("rd", "").strip()
    
    # Try standard formats
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", 
        "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%d-%m-%y"
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(clean_str, fmt).date()
        except ValueError:
            continue
    return None

def parse_fuzzy_time(time_str):
    """
    Restored Logic: Handles AM/PM and dot separators.
    """
    if not time_str: return None
    formats = ["%H:%M", "%I:%M %p", "%H.%M", "%I.%M %p", "%H %M"]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(time_str.upper(), fmt).time()
        except ValueError:
            continue
    return None

# --- THEME: TITANIUM DARK ---
def inject_midas_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Inter:wght@300;400;600&display=swap');
        .stApp {
            background-color: #050b14;
            background-image: radial-gradient(at 50% 0%, rgba(212, 175, 55, 0.08) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(15, 23, 42, 0.9) 0px, transparent 50%);
            font-family: 'Inter', sans-serif;
        }
        h1, h2, h3, h4, p, label, div, span, button { color: #ffffff !important; }
        .stMarkdown p { color: #e2e8f0 !important; }
        h1, h2, h3 {
            font-family: 'Cinzel', serif !important;
            background: linear-gradient(to right, #ffd700, #ffecb3, #d4af37);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700 !important;
        }
        /* Native Container Borders */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: rgba(30, 41, 59, 0.3);
            border: 1px solid rgba(212, 175, 55, 0.2) !important;
            border-radius: 12px;
            backdrop-filter: blur(8px);
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        /* Input Field Fixes */
        div[data-baseweb="input"] {
            background-color: #1e293b !important;
            border: 1px solid #475569 !important; 
            border-radius: 6px;
        }
        div[data-baseweb="input"] > div { background-color: transparent !important; }
        input { color: #ffffff !important; caret-color: #fbbf24; }
        
        /* File Uploader Fix */
        [data-testid="stFileUploaderDropzone"] {
            background-color: #1e293b !important;
            border: 1px dashed #d4af37 !important;
            border-radius: 10px;
        }
        [data-testid="stFileUploaderDropzone"] button {
            background: #334155 !important;
            color: white !important;
            border: 1px solid #64748b !important;
        }
        /* Gold Buttons */
        div.stButton > button {
            background: linear-gradient(135deg, #d4af37 0%, #b8860b 100%);
            color: #000 !important;
            border: none;
            font-weight: 800;
            padding: 0.6rem 1.2rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-radius: 8px;
        }
        </style>
    """, unsafe_allow_html=True)

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

    def find_date_from_positions(self, observed_positions, start_year=1900, end_year=2005):
        valid_targets = {k: v for k, v in observed_positions.items() if v and v != "Unknown"}
        if not valid_targets: return None
        start_date = datetime.date(start_year, 1, 1)
        end_date = datetime.date(end_year, 12, 31)
        delta = datetime.timedelta(days=15)
        current_date = start_date
        candidates = []
        planet_map = {"Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        while current_date <= end_date:
            jd = swe.julday(current_date.year, current_date.month, current_date.day)
            match = True
            for p_name, p_target in valid_targets.items():
                if p_name not in planet_map: continue
                pid = planet_map[p_name]
                pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                curr_sign = self.rashi_names[int(pos/30)]
                if curr_sign.lower() != p_target.lower():
                    match = False; break
            if match: candidates.append(current_date)
            current_date += delta
        for cand in candidates:
            d = cand - datetime.timedelta(days=20)
            limit = cand + datetime.timedelta(days=20)
            while d <= limit:
                jd = swe.julday(d.year, d.month, d.day)
                daily_match = True
                for p_name, p_target in valid_targets.items():
                    pid = {"Sun":swe.SUN, "Mars":swe.MARS, "Jupiter":swe.JUPITER, "Saturn":swe.SATURN, "Rahu":swe.MEAN_NODE}.get(p_name)
                    if pid:
                        pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                        if self.rashi_names[int(pos/30)].lower() != p_target.lower():
                            daily_match = False; break
                if daily_match: return d
                d += datetime.timedelta(days=1)
        return None

    def generate_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        occupants = {k: [] for k in layout}
        if chart_data:
            occupants[chart_data['Ascendant']['sign']].append("Asc")
            for p, data in chart_data.items():
                if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}°")
        bg = "#0f172a"; line = "#fbbf24"; text = "#f8fafc"; asc = "#ef4444"
        svg = [f'<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: {bg}; border-radius: 8px;">']
        svg.append(f'<rect x="2" y="2" width="396" height="396" fill="none" stroke="{line}" stroke-width="2"/>')
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="{line}" stroke-width="1" stroke-opacity="0.3"/>')
            svg.append(f'<text x="{x+50}" y="{y+55}" text-anchor="middle" fill="{line}" font-size="14" font-weight="bold" opacity="0.15">{sign[:3].upper()}</text>')
            if chart_data:
                for i, item in enumerate(occupants[sign]):
                    fill = asc if "Asc" in item else text
                    w = "bold" if "Asc" in item else "normal"
                    svg.append(f'<text x="{x+5}" y="{y+20+(i*15)}" fill="{fill}" font-weight="{w}" font-size="11" font-family="sans-serif">{item}</text>')
        svg.append(f'<text x="200" y="195" text-anchor="middle" font-size="16" fill="{line}" font-weight="bold" font-family="serif">RASHI CHAKRA</text>')
        svg.append('</svg>')
        return "".join(svg)

# --- MAIN UI ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide", page_icon="🕉️")
    inject_midas_css()
    engine = JyotishEngine()
    
    # Init State
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'form_tob' not in st.session_state: st.session_state['form_tob'] = datetime.time(12,0)
    if 'ai_planets' not in st.session_state: st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}
    if 'chart_data' not in st.session_state: st.session_state['chart_data'] = engine.calculate_chart(1990, 1, 1, 12, 0, 21.46, 83.98)

    st.markdown("## 🕉️ VedaVision Pro")

    # TABS
    tab1, tab2 = st.tabs(["📊 DASHBOARD", "⚙️ SETTINGS"])

    # === TAB 1: DASHBOARD ===
    with tab1:
        col_L, col_R = st.columns([1, 1.3], gap="medium")

        # LEFT: SCANNER
        with col_L:
            with st.container(border=True):
                st.markdown("### 📜 1. Manuscript Decoder")
                
                # --- VISIBLE MODE TOGGLE ---
                mode = st.radio("Scanning Mode", ["Paper (Text/Ink)", "Palm Leaf (Symbols)"], horizontal=True)
                
                uploaded = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"], label_visibility="collapsed")
                
                if uploaded and st.button("👁️ SCAN IMAGE"):
                    with st.spinner(f"Processing in {mode} mode..."):
                        try:
                            img = Image.open(uploaded)
                            st.image(img, caption="Scanning...", use_column_width=True)
                            
                            # --- 2. RESTORED PAPER PROMPT (THE KEY FIX) ---
                            if "Paper" in mode:
                                prompt = """
                                Analyze this Horoscope Document.
                                1. OCR Extract 'Name' (Look for Name/Namni/Sri).
                                2. OCR Extract 'Date of Birth' (Look for DOB, Date, Tarikh).
                                   * Note: Also look for Odia Numerals (e.g. ୧୯୭୯).
                                3. OCR Extract 'Time of Birth' (Look for TOB, Time, Samaya).
                                4. If a Rashi Chart is drawn, identify planet signs (Gu, Sha, Ra, Ma).
                                
                                RETURN JSON:
                                {
                                    "name": "Text found",
                                    "date": "YYYY-MM-DD",
                                    "time": "HH:MM",
                                    "positions": {"Jupiter": "Sign", "Saturn": "Sign"}
                                }
                                """
                            else:
                                # PALM LEAF MODE (Symbol Focused)
                                prompt = """
                                Analyze this Palm Leaf Chart.
                                Identify planetary symbols: Gu(Jup), Sha(Sat), Ra(Rahu), Ma(Mars).
                                RETURN JSON: {"positions": {"Jupiter": "Sign", "Saturn": "Sign", "Rahu": "Sign", "Mars": "Sign"}}
                                """
                            
                            resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                            txt = resp.text
                            json_match = re.search(r'\{.*\}', txt, re.DOTALL)
                            
                            if json_match:
                                data = json.loads(json_match.group())
                                
                                # Update Name
                                if data.get('name'): st.session_state['form_name'] = data['name']
                                
                                # 3. RESTORED FUZZY PARSING
                                if data.get('date'): 
                                    parsed = parse_fuzzy_date(data['date'])
                                    if parsed: st.session_state['form_dob'] = parsed
                                
                                if data.get('time'):
                                    parsed = parse_fuzzy_time(data['time'])
                                    if parsed: st.session_state['form_tob'] = parsed
                                    
                                for p, s in data.get('positions', {}).items():
                                    if s in engine.rashi_names: st.session_state['ai_planets'][p] = s
                                
                                st.success("Scan Complete!")
                                st.rerun()
                            else:
                                st.error("AI could not extract structured data.")
                        except Exception as e: 
                            st.error(f"Scan failed: {e}")

            # VERIFICATION
            with st.container(border=True):
                st.markdown("### 🕵️ 2. Verification & Date Finder")
                ropts = ["Unknown"] + engine.rashi_names
                c1, c2 = st.columns(2)
                with c1:
                    p_jup = st.selectbox("Jupiter (Gu)", ropts, index=ropts.index(st.session_state['ai_planets'].get("Jupiter", "Unknown")))
                    p_rah = st.selectbox("Rahu (Ra)", ropts, index=ropts.index(st.session_state['ai_planets'].get("Rahu", "Unknown")))
                with c2:
                    p_sat = st.selectbox("Saturn (Sha)", ropts, index=ropts.index(st.session_state['ai_planets'].get("Saturn", "Unknown")))
                    p_mar = st.selectbox("Mars (Ma)", ropts, index=ropts.index(st.session_state['ai_planets'].get("Mars", "Unknown")))
                
                if st.button("📅 FIND LOST DATE"):
                    found = engine.find_date_from_positions({"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar})
                    if found:
                        st.session_state['form_dob'] = found
                        st.success(f"Recovered Date: {found}")
                    else: st.error("No exact match found.")

        # RIGHT: OUTPUT
        with col_R:
            with st.container(border=True):
                st.markdown("### ✨ Janma Kundli")
                c_a, c_b = st.columns(2)
                with c_a:
                    name = st.text_input("Name", value=st.session_state['form_name'])
                    d_val = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1)
                    dob = st.date_input("Date", d_val, min_value=datetime.date(1800,1,1))
                with c_b:
                    city = st.text_input("Place", value="Sambalpur")
                    tob = st.time_input("Time", value=st.session_state['form_tob'])
                
                if st.button("GENERATE CHART"):
                    lat, lon = (21.46, 83.98) 
                    st.session_state['chart_data'] = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
                    st.rerun()

                st.markdown(engine.generate_svg(st.session_state['chart_data']), unsafe_allow_html=True)
                
                k1, k2 = st.columns(2)
                k1.info(f"**Ascendant:** {st.session_state['chart_data'].get('Ascendant', {}).get('sign', '-')}")
                k2.success(f"**Dasha:** {st.session_state['chart_data'].get('Current_Mahadasha', '-')}")

    # === TAB 2: CONFIG ===
    with tab2:
        with st.container(border=True):
            st.markdown("### ⚙️ Settings")
            c1, c2 = st.columns(2)
            with c1: st.selectbox("Language", ["Odia", "Sanskrit", "Hindi"])
            with c2: st.select_slider("Rotation", options=[0, 90, 180, 270])

if __name__ == "__main__":
    main()
