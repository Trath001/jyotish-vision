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
    st.error(f"Error initializing API client: {e}")

# --- CUSTOM CSS FOR "PREMIUM" LOOK ---
def inject_custom_css():
    st.markdown("""
        <style>
        /* Main Background */
        .stApp {
            background-color: #fcfbf9; /* Very light parchment */
        }
        
        /* Headers */
        h1, h2, h3 {
            font-family: 'Cinzel', serif; /* Mystical font vibe */
            color: #4a2c2a;
        }
        
        /* Buttons */
        div.stButton > button {
            background: linear-gradient(to right, #ff9966, #ff5e62);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            padding: 10px 24px;
            transition: all 0.3s ease;
        }
        div.stButton > button:hover {
            transform: scale(1.02);
            box-shadow: 0 4px 15px rgba(255, 94, 98, 0.4);
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #f7f3e8;
            border-right: 1px solid #e6dfc8;
        }
        
        /* Verification Box Styling */
        .verify-box {
            background-color: #ffffff;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #e0e0e0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin-bottom: 20px;
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

    # --- CALCULATIONS ---
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

    # --- REVERSE SEARCH ---
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

    # --- BEAUTIFUL CHART GENERATION ---
    def generate_south_indian_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        occupants = {k: [] for k in layout}
        occupants[chart_data['Ascendant']['sign']].append("Asc")
        for p, data in chart_data.items():
            if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}°")

        # Parchment Style Colors
        bg_color = "#fffbf0" # Warm parchment
        line_color = "#8b4513" # Saddle brown
        text_color = "#5c3a21" # Dark brown
        header_color = "#cd5c5c" # Indian Red for Rashi names

        svg = [f'<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: {bg_color}; border-radius: 8px;">']
        
        # Outer Border
        svg.append(f'<rect x="2" y="2" width="396" height="396" fill="none" stroke="{line_color}" stroke-width="4"/>')
        
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            # Cell Borders
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="{line_color}" stroke-width="1"/>')
            # Rashi Name (Background Header)
            svg.append(f'<text x="{x+50}" y="{y+55}" text-anchor="middle" fill="{header_color}" font-size="14" font-weight="bold" opacity="0.2">{sign[:3].upper()}</text>')
            
            # Planet List
            y_offset = 20
            for item in occupants[sign]:
                is_asc = "Asc" in item
                color = "#d32f2f" if is_asc else text_color
                weight = "bold" if is_asc else "normal"
                svg.append(f'<text x="{x+5}" y="{y+y_offset}" fill="{color}" font-weight="{weight}" font-size="11" font-family="Verdana">{item}</text>')
                y_offset += 15

        svg.append(f'<text x="200" y="195" text-anchor="middle" font-size="16" fill="{line_color}" font-weight="bold" font-family="serif">RASHI CHAKRA</text>')
        svg.append(f'<text x="200" y="215" text-anchor="middle" font-size="10" fill="{text_color}">Dasha: {chart_data["Current_Mahadasha"]}</text>')
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
    inject_custom_css() # Apply Theme
    engine = JyotishEngine()
    
    # State Init
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'ai_planets' not in st.session_state: 
        st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}

    # --- SIDEBAR (Controls) ---
    st.sidebar.title("🕉️ VedaVision Pro")
    st.sidebar.markdown("*AI-Powered Manuscript Decoder*")
    
    with st.sidebar.expander("⚙️ Settings", expanded=False):
        doc_language = st.selectbox("Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "English"])
        manuscript_type = st.radio("Type", ["Modern Paper", "Palm Leaf (Talapatra)"])
        rotation = st.select_slider("Rotate", options=[0, 90, 180, 270])
    
    uploaded = st.sidebar.file_uploader("Upload Manuscript", type=["jpg","png","jpeg"], accept_multiple_files=True)

    if uploaded and st.sidebar.button("🔍 Scan & Decode"):
        with st.spinner("Analyzing ancient script..."):
            try:
                img = Image.open(uploaded[0]) 
                if rotation != 0: img = img.rotate(-rotation, expand=True)
                if manuscript_type == "Palm Leaf (Talapatra)":
                    img = ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(2.0)
                st.sidebar.image(img, caption="Processed Image", use_column_width=True)

                prompt = f"""
                You are an expert reading {doc_language} Astrology Charts.
                IF PALM LEAF: Look for abbreviations (Gu=Jupiter, Sha=Saturn, Ra=Rahu).
                RETURN JSON ONLY:
                {{
                    "name": "Name or null",
                    "date": "YYYY-MM-DD or null",
                    "positions": {{ "Jupiter": "Sign or null", "Saturn": "Sign or null", "Rahu": "Sign or null", "Mars": "Sign or null" }}
                }}
                """
                resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                txt = resp.text
                data = json.loads(txt[txt.find('{'):txt.rfind('}')+1])

                st.session_state['form_name'] = data.get('name', "")
                if data.get('date'):
                    try: st.session_state['form_dob'] = datetime.datetime.strptime(data['date'], "%Y-%m-%d").date()
                    except: pass
                
                # Auto-fill dropdowns
                for p, s in data.get('positions', {}).items():
                    if s in engine.rashi_names: st.session_state['ai_planets'][p] = s
                
                st.toast("Scan Complete!", icon="✅")

            except Exception as e:
                st.error(f"Scan Error: {e}")

    # --- MAIN CONTENT AREA ---
    col_left, col_right = st.columns([1, 1.5])

    # LEFT: Verification Panel
    with col_left:
        st.markdown("### 🕵️ Verification")
        st.markdown('<div class="verify-box">', unsafe_allow_html=True)
        st.caption("Verify the AI's planetary detection below to find the birth date.")
        
        rashi_opts = ["Unknown"] + engine.rashi_names
        
        c1, c2 = st.columns(2)
        with c1:
            p_jup = st.selectbox("Jupiter (ଗୁ)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Jupiter", "Unknown")))
            p_rah = st.selectbox("Rahu (ରା)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Rahu", "Unknown")))
        with c2:
            p_sat = st.selectbox("Saturn (ଶ)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Saturn", "Unknown")))
            p_mar = st.selectbox("Mars (ମ)", rashi_opts, index=rashi_opts.index(st.session_state['ai_planets'].get("Mars", "Unknown")))

        if st.button("📅 Calculate Date"):
            current_map = {"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar}
            found = engine.find_date_from_positions(current_map)
            if found:
                st.session_state['form_dob'] = found
                st.success(f"Found: {found}")
            else:
                st.warning("No match found.")
        st.markdown('</div>', unsafe_allow_html=True)

    # RIGHT: Kundli Output
    with col_right:
        st.markdown("### 📜 Janma Kundli")
        
        # Form
        with st.form("kundli_form"):
            c_a, c_b = st.columns(2)
            with c_a:
                name = st.text_input("Name", st.session_state['form_name'])
                dob = st.date_input("Date", st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1))
            with c_b:
                city = st.text_input("City", "Sambalpur")
                tob = st.time_input("Time", datetime.time(12,0))
            
            gen_btn = st.form_submit_button("✨ Generate Chart")

        if gen_btn:
            lat, lon = get_lat_lon(city)
            chart = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
            
            # Show Chart
            st.markdown(engine.generate_south_indian_svg(chart), unsafe_allow_html=True)
            
            # Dasha Info Card
            st.info(f"**Current Mahadasha:** {chart['Current_Mahadasha']}")

if __name__ == "__main__":
    main()
