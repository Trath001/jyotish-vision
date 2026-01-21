import streamlit as st
from google import genai
import swisseph as swe
import datetime
from geopy.geocoders import Nominatim
from PIL import Image, ImageEnhance, ImageOps
import json

# --- CONFIGURATION ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # User must set this in Streamlit Cloud Secrets
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    pass

# --- THEME: "MIDAS TOUCH" (PREMIUM GOLD & DARK) ---
def inject_midas_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Inter:wght@300;400;600&display=swap');

        /* 1. MAIN BACKGROUND - Deep Cosmic Navy */
        .stApp {
            background-color: #050b14;
            background-image: 
                radial-gradient(at 50% 0%, rgba(212, 175, 55, 0.1) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(15, 23, 42, 0.5) 0px, transparent 50%);
            font-family: 'Inter', sans-serif;
        }

        /* 2. TYPOGRAPHY - High Contrast White & Gold */
        h1, h2, h3 {
            font-family: 'Cinzel', serif !important;
            background: linear-gradient(to right, #ffd700, #ffecb3, #d4af37);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0px 2px 10px rgba(212, 175, 55, 0.3);
            font-weight: 700 !important;
        }
        p, label, span, div {
            color: #e2e8f0 !important; /* Soft White */
        }

        /* 3. INPUT FIELDS - Fix Visibility Defects */
        /* Force dark background and white text for ALL inputs */
        input, .stTextInput > div > div > input {
            color: #ffffff !important;
            background-color: #1e293b !important;
            border-color: #475569 !important;
        }
        /* Dropdowns/Selectboxes */
        .stSelectbox > div > div {
            background-color: #1e293b !important;
            color: #ffffff !important;
            border: 1px solid #475569 !important;
        }
        /* Date Picker specific fix */
        input[type="text"] {
            color: #ffffff !important; 
        }

        /* 4. GLASSMORPHISM CARDS */
        .glass-card {
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid rgba(212, 175, 55, 0.3); /* Gold border */
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        /* 5. BUTTONS - Liquid Gold */
        div.stButton > button {
            background: linear-gradient(135deg, #d4af37 0%, #b8860b 100%);
            color: #000000 !important; /* Black text on gold is readable */
            border: none;
            font-weight: 700;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.3s ease;
            width: 100%;
        }
        div.stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 0 20px rgba(212, 175, 55, 0.6);
            color: #fff !important;
        }

        /* 6. SIDEBAR - Clean & Dark */
        [data-testid="stSidebar"] {
            background-color: #02040a;
            border-right: 1px solid #334155;
        }
        
        /* 7. TABS - Gold Highlights */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            gap: 1px;
            padding-top: 10px;
            padding-bottom: 10px;
            color: #94a3b8;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(212, 175, 55, 0.1);
            color: #fbbf24 !important; /* Gold Text */
            border-bottom: 2px solid #fbbf24;
        }
        </style>
    """, unsafe_allow_html=True)

class JyotishEngine:
    def __init__(self):
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.rashi_names = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        self.dasha_lords = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
        self.dasha_years = [7, 20, 6, 10, 7, 18, 16, 19, 17]
        self.nakshatra_names = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]

    def get_nakshatra(self, longitude):
        idx = int(longitude / 13.33333333)
        return self.nakshatra_names[idx % 27], int((longitude % 13.33333333) / 3.33333333) + 1

    def calculate_current_dasha(self, moon_long, birth_date):
        nak_idx = int(moon_long / 13.33333333)
        balance = 1 - ((moon_long % 13.33333333) / 13.33333333)
        start_lord_idx = nak_idx % 9
        current_date = datetime.date.today()
        running_date = birth_date + datetime.timedelta(days=self.dasha_years[start_lord_idx] * balance * 365.25)
        current_lord_idx = start_lord_idx
        while running_date < current_date:
            current_lord_idx = (current_lord_idx + 1) % 9
            running_date += datetime.timedelta(days=self.dasha_years[current_lord_idx] * 365.25)
        return self.dasha_lords[current_lord_idx]

    def calculate_chart(self, year, month, day, hour, minute, lat, lon):
        utc_dec = (hour + minute/60.0) - 5.5
        jd = swe.julday(year, month, day, utc_dec)
        ayanamsa = swe.get_ayanamsa_ut(jd)
        planets = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        chart_data = {}
        for name, pid in planets.items():
            pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)[0][0]
            sign_idx = int(pos / 30)
            nak, pada = self.get_nakshatra(pos)
            chart_data[name] = {"sign": self.rashi_names[sign_idx], "degree": round(pos % 30, 2), "nakshatra": nak}
        houses = swe.houses(jd, lat, lon)[1]
        asc_val = (houses[0] - ayanamsa) % 360
        nak, pada = self.get_nakshatra(asc_val)
        chart_data["Ascendant"] = {"sign": self.rashi_names[int(asc_val / 30)], "degree": round(asc_val % 30, 2), "nakshatra": nak}
        moon_abs = (self.rashi_names.index(chart_data["Moon"]["sign"]) * 30) + chart_data["Moon"]["degree"]
        chart_data["Current_Mahadasha"] = self.calculate_current_dasha(moon_abs, datetime.date(year, month, day))
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
                curr_sign = self.rashi_names[int(pos / 30)]
                if curr_sign.lower() != p_target.lower():
                    match = False
                    break
            if match: candidates.append(current_date)
            current_date += delta
        for cand in candidates:
            d = cand - datetime.timedelta(days=20)
            limit = cand + datetime.timedelta(days=20)
            while d <= limit:
                jd = swe.julday(d.year, d.month, d.day)
                daily_match = True
                for p_name, p_target in valid_targets.items():
                    pid_map = {"Sun": swe.SUN, "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
                    if p_name in pid_map:
                        pid = pid_map[p_name]
                        pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                        curr_sign = self.rashi_names[int(pos / 30)]
                        if curr_sign.lower() != p_target.lower():
                            daily_match = False
                            break
                if daily_match: return d
                d += datetime.timedelta(days=1)
        return None

    def generate_south_indian_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        occupants = {k: [] for k in layout}
        if chart_data:
            occupants[chart_data['Ascendant']['sign']].append("Asc")
            for p, data in chart_data.items():
                if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}°")

        # PREMIUM GOLD THEME
        bg_color = "#0f172a"      
        line_color = "#d4af37"    # Metallic Gold
        text_color = "#f8fafc"    # White
        asc_color = "#ef4444"     # Red

        svg = [f'<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: {bg_color}; border-radius: 8px;">']
        svg.append(f'<rect x="2" y="2" width="396" height="396" fill="none" stroke="{line_color}" stroke-width="2"/>')
        
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="{line_color}" stroke-width="1" stroke-opacity="0.4"/>')
            svg.append(f'<text x="{x+50}" y="{y+55}" text-anchor="middle" fill="{line_color}" font-size="14" font-weight="bold" opacity="0.15">{sign[:3].upper()}</text>')
            if chart_data:
                y_offset = 20
                for item in occupants[sign]:
                    is_asc = "Asc" in item
                    fill = asc_color if is_asc else text_color
                    weight = "bold" if is_asc else "normal"
                    svg.append(f'<text x="{x+5}" y="{y+y_offset}" fill="{fill}" font-weight="{weight}" font-size="11" font-family="sans-serif">{item}</text>')
                    y_offset += 15

        svg.append(f'<text x="200" y="195" text-anchor="middle" font-size="16" fill="{line_color}" font-weight="bold" font-family="serif">RASHI CHAKRA</text>')
        svg.append('</svg>')
        return "".join(svg)

# --- HELPER FUNCTIONS ---
def get_lat_lon(city_name):
    if not city_name: return 21.46, 83.98
    if "sambalpur" in city_name.lower(): return 21.46, 83.98
    geolocator = Nominatim(user_agent="jyotish_mitra_app")
    try:
        location = geolocator.geocode(city_name)
        if location: return location.latitude, location.longitude
        return 21.46, 83.98
    except: return 21.46, 83.98

# --- MAIN UI ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide", page_icon="🕉️")
    inject_midas_css()
    engine = JyotishEngine()
    
    # Init Session State
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'ai_planets' not in st.session_state: 
        st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}
    if 'chart_data' not in st.session_state:
        # Placeholder Chart (Default)
        now = datetime.datetime.now()
        st.session_state['chart_data'] = engine.calculate_chart(now.year, now.month, now.day, 12, 0, 21.46, 83.98)

    # --- TOP BAR ---
    st.markdown("## 🕉️ VedaVision Pro")
    
    # --- TABS FOR CLEANER UI (SOLVES CONGESTION) ---
    tab_dashboard, tab_settings = st.tabs(["📊 Main Dashboard", "⚙️ Configuration"])

    # === TAB 1: DASHBOARD (MAIN WORKSPACE) ===
    with tab_dashboard:
        col_left, col_right = st.columns([1, 1.3], gap="large")

        # LEFT COLUMN: INPUTS & VERIFICATION
        with col_left:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown("### 📜 1. Manuscript Decoder")
            st.caption("Upload your Talapatra or Paper Chart to auto-detect planets.")
            
            uploaded = st.file_uploader("Upload Image", type=["jpg","png","jpeg"], label_visibility="collapsed")
            
            if uploaded and st.button("👁️ Analyze Image"):
                with st.spinner("Decoding Ancient Script..."):
                    try:
                        img = Image.open(uploaded) 
                        st.image(img, caption="Scanning...", use_column_width=True)
                        
                        # AI Prompt
                        prompt = """
                        Expert Astrologer Task. Read Odia/Sanskrit Chart.
                        Look for: Gu(Jup), Sha(Sat), Ra(Rahu), Ma(Mars).
                        RETURN JSON: {"positions": { "Jupiter": "Sign", "Saturn": "Sign", "Rahu": "Sign", "Mars": "Sign" }}
                        """
                        resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                        data = json.loads(resp.text[resp.text.find('{'):resp.text.rfind('}')+1])
                        
                        for p, s in data.get('positions', {}).items():
                            if s in engine.rashi_names: st.session_state['ai_planets'][p] = s
                        st.success("Scan Complete! Please verify below.")
                    except:
                        st.error("Could not read image. Please enter planets manually.")

            st.markdown("---")
            st.markdown("#### 🕵️ 2. Verification & Date Finder")
            st.caption("If the date is unknown, select planets seen in the chart.")
            
            rashi_opts = ["Unknown"] + engine.rashi_names
            c1, c2 = st.columns(2)
            with c1:
                p_jup = st.selectbox("Jupiter (Gu)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Jupiter", "Unknown")))
                p_rah = st.selectbox("Rahu (Ra)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Rahu", "Unknown")))
            with c2:
                p_sat = st.selectbox("Saturn (Sha)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Saturn", "Unknown")))
                p_mar = st.selectbox("Mars (Ma)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Mars", "Unknown")))

            if st.button("📅 Find Lost Date"):
                found = engine.find_date_from_positions({"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar})
                if found:
                    st.session_state['form_dob'] = found
                    st.success(f"Date Recovered: {found}")
                else:
                    st.error("No exact match found in 1900-2005.")
            st.markdown('</div>', unsafe_allow_html=True)

        # RIGHT COLUMN: KUNDLI OUTPUT
        with col_right:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown("### ✨ Janma Kundli")
            
            # --- DEFECT FIX: YEAR RANGE ---
            # Explicitly setting min_value to 1800 to fix the "1980 limit" bug
            min_date = datetime.date(1800, 1, 1)
            default_date = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990, 1, 1)
            
            with st.form("chart_gen"):
                c_a, c_b = st.columns(2)
                with c_a:
                    name = st.text_input("Name", value="Unknown")
                    dob = st.date_input("Date of Birth", value=default_date, min_value=min_date)
                with c_b:
                    city = st.text_input("Place", value="Sambalpur")
                    tob = st.time_input("Time", datetime.time(12,0))
                
                if st.form_submit_button("GENERATE CHART"):
                    lat, lon = get_lat_lon(city)
                    st.session_state['chart_data'] = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
                    st.rerun()

            # Render Chart
            st.markdown(engine.generate_south_indian_svg(st.session_state['chart_data']), unsafe_allow_html=True)
            
            # Data Cards
            dasha = st.session_state['chart_data'].get('Current_Mahadasha', 'Unknown')
            asc = st.session_state['chart_data'].get('Ascendant', {}).get('sign', 'Unknown')
            
            k1, k2 = st.columns(2)
            k1.info(f"**Ascendant:** {asc}")
            k2.success(f"**Mahadasha:** {dasha}")
            st.markdown('</div>', unsafe_allow_html=True)

    # === TAB 2: SETTINGS (MOVED HERE TO FIX CONGESTION) ===
    with tab_settings:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### ⚙️ Global Settings")
        doc_language = st.selectbox("Manuscript Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi"])
        manuscript_type = st.radio("Document Type", ["Palm Leaf (Talapatra)", "Paper"])
        rotation = st.select_slider("Image Rotation Correction", options=[0, 90, 180, 270], value=0)
        st.info("ℹ️ Settings are applied automatically to the next scan.")
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
