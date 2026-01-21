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
    # User must set this in Streamlit Cloud Secrets
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error initializing API client: {e}")

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

    def generate_south_indian_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        occupants = {k: [] for k in layout}
        occupants[chart_data['Ascendant']['sign']].append("Asc")
        for p, data in chart_data.items():
            if p not in ["Ascendant", "Current_Mahadasha"]: occupants[data['sign']].append(f"{p[:2]} {int(data['degree'])}")

        svg = ['<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background:white"><rect width="400" height="400" fill="white" stroke="#333" stroke-width="2"/>']
        for sign, (r, c) in layout.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="#ccc"/>')
            svg.append(f'<text x="{x+50}" y="{y+50}" text-anchor="middle" fill="#eee" font-size="14" font-weight="bold">{sign[:3].upper()}</text>')
            for i, txt in enumerate(occupants[sign]):
                svg.append(f'<text x="{x+5}" y="{y+20+(i*15)}" font-size="10" fill="black">{txt}</text>')
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
    st.set_page_config(page_title="VedaVision Pro", layout="wide")
    engine = JyotishEngine()
    
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'ai_planets' not in st.session_state: 
        st.session_state['ai_planets'] = {"Jupiter": "Unknown", "Saturn": "Unknown", "Rahu": "Unknown", "Mars": "Unknown"}

    st.sidebar.title("VedaVision Pro")
    
    doc_language = st.sidebar.selectbox("Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "English"])
    manuscript_type = st.sidebar.radio("Manuscript Type", ["Modern Paper", "Palm Leaf (Talapatra)"])
    rotation = st.sidebar.select_slider("Rotate", options=[0, 90, 180, 270])
    
    uploaded = st.sidebar.file_uploader("Upload Manuscript", type=["jpg","png","jpeg"], accept_multiple_files=True)

    # --- STEP 1: AI SCAN ---
    if uploaded and st.sidebar.button("Scan Manuscript"):
        with st.spinner("AI Reading..."):
            try:
                img = Image.open(uploaded[0]) 
                if rotation != 0: img = img.rotate(-rotation, expand=True)
                if manuscript_type == "Palm Leaf (Talapatra)":
                    img = ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(2.0)
                st.sidebar.image(img, caption="AI Vision Input")

                prompt = f"""
                You are an expert reading {doc_language} Astrology Charts.
                
                IF PALM LEAF: Look for abbreviations inside the Rashi Chakra (Wheel).
                * 'ଗୁ'/'ବୃ' = Jupiter
                * 'ଶ'/'ଶନି' = Saturn
                * 'ରା'/'ର' = Rahu
                * 'ମ'/'ମଂ' = Mars
                
                RETURN JSON ONLY:
                {{
                    "name": "Visible Name or null",
                    "date": "YYYY-MM-DD or null",
                    "positions": {{
                        "Jupiter": "SignName (e.g. Aries) or null",
                        "Saturn": "SignName or null",
                        "Rahu": "SignName or null",
                        "Mars": "SignName or null"
                    }}
                }}
                """
                
                resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                txt = resp.text
                json_str = txt[txt.find('{'):txt.rfind('}')+1]
                data = json.loads(json_str)

                st.session_state['form_name'] = data.get('name', "")
                if data.get('date'):
                    try: st.session_state['form_dob'] = datetime.datetime.strptime(data['date'], "%Y-%m-%d").date()
                    except: pass
                
                ai_pos = data.get('positions', {})
                for p, s in ai_pos.items():
                    if s and s in engine.rashi_names:
                        st.session_state['ai_planets'][p] = s
                
                st.sidebar.success("Scan Complete! Verify Planets below.")

            except Exception as e:
                st.sidebar.error(f"Scan Error: {e}")

    st.sidebar.markdown("---")

    # --- NEW: CHEAT SHEET (VERIFICATION TOOL) ---
    with st.sidebar.expander("🕵️ How to Verify (Cheat Sheet)", expanded=True):
        st.markdown("""
        **Don't read Odia? Just match these shapes!**
        
        | Planet | Odia Symbol | Shape Hint |
        | :--- | :--- | :--- |
        | **Jupiter** | **ଗୁ** or **ବୃ** | Look for **Gu** or **Bri** |
        | **Saturn** | **ଶ** or **ଶନି** | Look for **Sha** (Looped top) |
        | **Rahu** | **ରା** or **ର** | Look for **Ra** |
        | **Mars** | **ମ** or **ମଂ** | Look for **Ma** (Swan shape) |
        
        **Chart Layout (Standard Odia):**
        The Signs are fixed. Aries is usually Top-Right or Top.
        1. Mesh (Aries)
        2. Vrish (Taurus) ...
        """)

    # --- STEP 2: VERIFY & CALCULATE ---
    st.sidebar.subheader("🪐 Verify & Detect Date")
    
    rashi_options = ["Unknown"] + engine.rashi_names
    def get_index(p_name):
        val = st.session_state['ai_planets'].get(p_name, "Unknown")
        return rashi_options.index(val) if val in rashi_options else 0

    col1, col2 = st.sidebar.columns(2)
    with col1:
        p_jup = st.selectbox("Jupiter (ଗୁ)", rashi_options, index=get_index("Jupiter"))
        p_rah = st.selectbox("Rahu (ରା)", rashi_options, index=get_index("Rahu"))
    with col2:
        p_sat = st.selectbox("Saturn (ଶ)", rashi_options, index=get_index("Saturn"))
        p_mar = st.selectbox("Mars (ମ)", rashi_options, index=get_index("Mars"))

    if st.sidebar.button("🕵️ Find Date"):
        current_map = {"Jupiter": p_jup, "Saturn": p_sat, "Rahu": p_rah, "Mars": p_mar}
        with st.spinner("Searching 1900-2005..."):
            found_date = engine.find_date_from_positions(current_map)
            if found_date:
                st.session_state['form_dob'] = found_date
                st.sidebar.success(f"✅ MATCH: {found_date}")
            else:
                st.sidebar.error("No match. Try adjusting one planet.")

    st.sidebar.markdown("---")

    # --- STEP 3: FINAL OUTPUT ---
    with st.sidebar.form("details"):
        name = st.text_input("Name", st.session_state['form_name'])
        safe_dob = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1)
        dob = st.date_input("DOB", safe_dob)
        tob = st.time_input("Time", datetime.time(12,0))
        city = st.text_input("City", "Sambalpur")
        
        if st.form_submit_button("Generate Kundli"):
            lat, lon = get_lat_lon(city)
            chart = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
            st.markdown(engine.generate_south_indian_svg(chart), unsafe_allow_html=True)
            st.info(f"Current Mahadasha: {chart['Current_Mahadasha']}")

if __name__ == "__main__":
    main()
