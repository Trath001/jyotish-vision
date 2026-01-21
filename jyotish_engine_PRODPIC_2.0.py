import streamlit as st
from google import genai
import swisseph as swe
import datetime
from geopy.geocoders import Nominatim
from PIL import Image, ImageEnhance, ImageOps
import json
import time

# --- CONFIGURATION ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    pass # UI handles error gracefully

# --- THEME: ENTERPRISE DARK DASHBOARD ---
def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Inter:wght@300;400;600&display=swap');

        /* APP BACKGROUND */
        .stApp {
            background-color: #020617;
            background-image: 
                radial-gradient(at 0% 0%, rgba(251, 191, 36, 0.03) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(15, 23, 42, 0.5) 0px, transparent 50%);
            color: #e2e8f0;
            font-family: 'Inter', sans-serif;
        }

        /* SIDEBAR STYLING */
        [data-testid="stSidebar"] {
            background-color: #0b1121;
            border-right: 1px solid #1e293b;
        }

        /* HEADERS */
        h1, h2, h3, h4 {
            font-family: 'Cinzel', serif !important;
            color: #fbbf24 !important; /* Amber Gold */
            letter-spacing: 0.5px;
        }

        /* CARDS (GLASSMORPHISM) */
        .dashboard-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            backdrop-filter: blur(12px);
            transition: transform 0.2s;
        }
        .dashboard-card:hover {
            border-color: #fbbf24;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }

        /* BUTTONS */
        .stButton > button {
            background: linear-gradient(135deg, #d97706 0%, #92400e 100%);
            color: white !important;
            border: none;
            font-weight: 600;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            width: 100%;
        }
        .stButton > button:hover {
            opacity: 0.9;
            transform: scale(1.02);
        }

        /* INPUT FIELDS */
        div[data-baseweb="input"], div[data-baseweb="select"] > div {
            background-color: #1e293b !important;
            border: 1px solid #475569 !important;
            color: white !important;
            border-radius: 6px;
        }
        
        /* CHAT BUBBLES */
        .chat-user {
            background-color: #334155;
            padding: 10px;
            border-radius: 10px 10px 0 10px;
            margin: 5px 0;
            text-align: right;
        }
        .chat-ai {
            background-color: #1e293b;
            border: 1px solid #fbbf24;
            padding: 10px;
            border-radius: 10px 10px 10px 0;
            margin: 5px 0;
            color: #e2e8f0;
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
        occupants[chart_data['Ascendant']['sign']].append("Asc")
        for p, data in chart_data.items():
            if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}°")

        bg_color = "#0f172a"      
        line_color = "#fbbf24"    # Gold
        text_color = "#f8fafc"    # White
        asc_color = "#ef4444"     # Red

        svg = [f'<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: {bg_color}; border-radius: 8px;">']
        svg.append(f'<rect x="2" y="2" width="396" height="396" fill="none" stroke="{line_color}" stroke-width="2"/>')
        
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="{line_color}" stroke-width="1" stroke-opacity="0.3"/>')
            svg.append(f'<text x="{x+50}" y="{y+55}" text-anchor="middle" fill="{line_color}" font-size="14" font-weight="bold" opacity="0.15">{sign[:3].upper()}</text>')
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
    st.set_page_config(page_title="VedaVision Enterprise", layout="wide", page_icon="🕉️")
    inject_custom_css()
    engine = JyotishEngine()
    
    # Init State
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'ai_planets' not in st.session_state: 
        st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}
    if 'chat_history' not in st.session_state: st.session_state['chat_history'] = []

    # --- SIDEBAR (COMMAND CENTER) ---
    with st.sidebar:
        st.markdown("## 🕉️ VedaVision")
        st.caption("Enterprise Manuscript Decoder")
        st.markdown("---")
        
        # DEMO BUTTON
        if st.button("⚡ Load Demo Data"):
            st.session_state['ai_planets'] = {"Jupiter": "Leo", "Saturn": "Leo", "Rahu": "Leo", "Mars": "Leo"}
            st.session_state['form_name'] = "Demo User"
            st.session_state['chat_history'].append({"role": "ai", "content": "I've loaded a sample Talapatra scan. I detected 4 planets in Leo. Please use the 'Find Date' button to calculate the exact birth year."})
            st.rerun()

        st.markdown("### ⚙️ Configuration")
        doc_language = st.selectbox("Script", ["Odia (ଓଡ଼ିଆ)", "Sanskrit"])
        manuscript_type = st.radio("Format", ["Palm Leaf", "Paper"])
        rotation = st.select_slider("Rotate", options=[0, 90, 180, 270])
        uploaded = st.file_uploader("Upload Scan", type=["jpg","png"])

        if uploaded and st.button("👁️ Scan Image"):
            with st.spinner("Analyzing..."):
                try:
                    img = Image.open(uploaded[0]) 
                    if rotation != 0: img = img.rotate(-rotation, expand=True)
                    if manuscript_type == "Palm Leaf":
                        img = ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(2.0)
                    st.image(img, caption="Enhanced Scan")

                    prompt = f"""
                    Expert Astrologer Task. Read {doc_language} Chart.
                    Look for single letters: Gu(Jup), Sha(Sat), Ra(Rahu), Ma(Mars).
                    RETURN JSON:
                    {{
                        "name": "Name or null",
                        "date": "YYYY-MM-DD or null",
                        "positions": {{ "Jupiter": "Sign", "Saturn": "Sign", "Rahu": "Sign", "Mars": "Sign" }}
                    }}
                    """
                    resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                    data = json.loads(resp.text[resp.text.find('{'):resp.text.rfind('}')+1])

                    st.session_state['form_name'] = data.get('name', "")
                    if data.get('date'):
                        try: st.session_state['form_dob'] = datetime.datetime.strptime(data['date'], "%Y-%m-%d").date()
                        except: pass
                    
                    for p, s in data.get('positions', {}).items():
                        if s in engine.rashi_names: st.session_state['ai_planets'][p] = s
                    
                    st.session_state['chat_history'].append({"role": "ai", "content": f"Scan complete! I found: {st.session_state['ai_planets']}. Please verify these on the dashboard."})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    # --- MAIN DASHBOARD LAYOUT ---
    
    # Header
    st.markdown("### 🪐 Planetary Dashboard")

    col_center, col_right = st.columns([2, 1])

    # CENTER PANEL: WORKSPACE
    with col_center:
        # Verification Card
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.markdown("#### 🕵️ 1. Verification & Date Recovery")
        
        rashi_opts = ["Unknown"] + engine.rashi_names
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            p_jup = st.selectbox("Jupiter", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Jupiter", "Unknown")))
        with c2:
            p_sat = st.selectbox("Saturn", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Saturn", "Unknown")))
        with c3:
            p_rah = st.selectbox("Rahu", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Rahu", "Unknown")))
        with c4:
            p_mar = st.selectbox("Mars", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Mars", "Unknown")))

        if st.button("📅 Calculate Date from Planets"):
            found = engine.find_date_from_positions({"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar})
            if found:
                st.session_state['form_dob'] = found
                st.session_state['chat_history'].append({"role": "ai", "content": f"Success! Based on the planetary alignment (Jupiter/Saturn/Rahu/Mars), the calculated birth date is **{found}**."})
                st.rerun()
            else:
                st.error("No astronomical match found. Try adjusting Mars.")
        st.markdown('</div>', unsafe_allow_html=True)

        # Output Card
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.markdown("#### 📜 2. Kundli Generation")
        
        with st.form("chart_form"):
            c_a, c_b = st.columns(2)
            with c_a:
                name = st.text_input("Name", st.session_state['form_name'])
                dob = st.date_input("Date", st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1))
            with c_b:
                city = st.text_input("City", "Sambalpur")
                tob = st.time_input("Time", datetime.time(12,0))
            
            if st.form_submit_button("Generate & Analyze"):
                lat, lon = get_lat_lon(city)
                chart = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
                
                # Render Chart Side-by-Side with Stats
                cc1, cc2 = st.columns([1, 1])
                with cc1:
                    st.markdown(engine.generate_south_indian_svg(chart), unsafe_allow_html=True)
                with cc2:
                    st.info(f"**Mahadasha:** {chart['Current_Mahadasha']}")
                    st.success(f"**Ascendant:** {chart['Ascendant']['sign']}")
                    st.caption("Planetary positions calculated using Lahiri Ayanamsa.")
                    
                st.session_state['chat_history'].append({"role": "ai", "content": f"Chart generated for {name}. The Ascendant is {chart['Ascendant']['sign']}. You are currently running the {chart['Current_Mahadasha']} Mahadasha."})
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # RIGHT PANEL: CHAT & INSIGHTS
    with col_right:
        st.markdown('<div class="dashboard-card" style="height: 600px; overflow-y: auto;">', unsafe_allow_html=True)
        st.markdown("#### 🤖 Jyotish Mitra")
        st.caption("AI Assistant")
        
        # Chat History Display
        for msg in st.session_state['chat_history']:
            if msg['role'] == 'ai':
                st.markdown(f'<div class="chat-ai"><b>Mitra:</b> {msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        
        # Chat Input
        user_input = st.text_input("Ask about the chart...", key="chat_in")
        if user_input:
            st.session_state['chat_history'].append({"role": "user", "content": user_input})
            # Simulate AI Response (Placeholder for now)
            st.session_state['chat_history'].append({"role": "ai", "content": "I am analyzing the planetary strength (Shadbala) based on your question..."})
            st.rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
