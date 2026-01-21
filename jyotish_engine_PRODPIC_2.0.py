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
    # Safe fallback (User must set this in Streamlit Cloud Secrets)
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE"

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error initializing API client: {e}")

class JyotishEngine:
    """
    Master Class: Handles Forward Calculation (Kundli) AND Reverse Search (Time Detective).
    """
    def __init__(self):
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.rashi_names = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        self.nakshatra_names = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
        self.dasha_lords = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
        self.dasha_years = [7, 20, 6, 10, 7, 18, 16, 19, 17]

    # --- FORWARD CALCULATION ---
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
        local_dt = datetime.datetime(year, month, day, hour, minute)
        utc_decimal_hour = (hour + minute/60.0) - 5.5
        julian_day = swe.julday(year, month, day, utc_decimal_hour)
        ayanamsa = swe.get_ayanamsa_ut(julian_day)
        
        planets = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        chart_data = {}
        
        for name, pid in planets.items():
            pos = swe.calc_ut(julian_day, pid, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)[0][0]
            sign_idx = int(pos / 30)
            nak, pada = self.get_nakshatra(pos)
            chart_data[name] = {"sign": self.rashi_names[sign_idx], "degree": round(pos % 30, 2), "nakshatra": nak}

        houses = swe.houses(julian_day, lat, lon)[1]
        asc_val = (houses[0] - ayanamsa) % 360
        nak, pada = self.get_nakshatra(asc_val)
        chart_data["Ascendant"] = {"sign": self.rashi_names[int(asc_val / 30)], "degree": round(asc_val % 30, 2), "nakshatra": nak}
        
        chart_data["Current_Mahadasha"] = self.calculate_current_dasha(chart_data["Moon"]["degree"] + (self.rashi_names.index(chart_data["Moon"]["sign"])*30), datetime.date(year, month, day))
        return chart_data

    # --- REVERSE SEARCH (ROBUST FIX) ---
    def find_date_from_positions(self, observed_positions, start_year=1900, end_year=2005):
        # FIX: Immediate rejection if positions are empty
        if not observed_positions or len(observed_positions) == 0:
            return None

        start_date = datetime.date(start_year, 1, 1)
        end_date = datetime.date(end_year, 12, 31)
        delta = datetime.timedelta(days=15)
        current_date = start_date
        candidates = []
        planet_map = {"Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}

        # 1. Broad Search (15-day jumps)
        while current_date <= end_date:
            jd = swe.julday(current_date.year, current_date.month, current_date.day)
            match = True
            checked_count = 0
            
            for p_name, p_target in observed_positions.items():
                if p_name not in planet_map or not p_target: continue # Skip if planet is None
                
                checked_count += 1
                pid = planet_map[p_name]
                pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                curr_sign = self.rashi_names[int(pos / 30)]
                
                # Robust Compare
                if curr_sign.lower() != str(p_target).lower():
                    match = False
                    break
            
            if match and checked_count > 0: candidates.append(current_date)
            current_date += delta
        
        # 2. Fine Search (Daily)
        for cand in candidates:
            d = cand - datetime.timedelta(days=20)
            limit = cand + datetime.timedelta(days=20)
            while d <= limit:
                jd = swe.julday(d.year, d.month, d.day)
                daily_match = True
                
                for p_name, p_target in observed_positions.items():
                    if not p_target: continue
                    
                    pid_map = {"Sun": swe.SUN, "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
                    if p_name in pid_map:
                        pid = pid_map[p_name]
                        pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                        curr_sign = self.rashi_names[int(pos / 30)]
                        if curr_sign.lower() != str(p_target).lower():
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
    if "rayagada" in city_name.lower(): return 19.17, 83.41
    geolocator = Nominatim(user_agent="jyotish_mitra_app")
    try:
        location = geolocator.geocode(city_name)
        if location: return location.latitude, location.longitude
        return 21.46, 83.98
    except: return 21.46, 83.98

# --- UI ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide")
    engine = JyotishEngine()
    
    # Init Session State
    if 'form_name' not in st.session_state: st.session_state.update({'form_name': "", 'form_dob': None, 'form_city': "", 'ai_debug': ""})

    st.sidebar.title("VedaVision Pro")
    
    # --- 1. SETTINGS (Restored!) ---
    doc_language = st.sidebar.selectbox("Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "English"])
    manuscript_type = st.sidebar.radio("Manuscript Type", ["Modern Paper", "Palm Leaf (Talapatra)"])
    rotation = st.sidebar.select_slider("Rotate", options=[0, 90, 180, 270])
    
    # --- 2. UPLOAD (Restored!) ---
    uploaded = st.sidebar.file_uploader("Upload Manuscript", type=["jpg","png","jpeg"], accept_multiple_files=True)

    if uploaded and st.sidebar.button("Analyze"):
        with st.spinner("Processing..."):
            try:
                # Fix: Always iterate or grab first valid file safely
                img = Image.open(uploaded[0]) 
                
                # Pre-processing
                if rotation != 0: img = img.rotate(-rotation, expand=True)
                if manuscript_type == "Palm Leaf (Talapatra)":
                    img = ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(2.5)
                
                st.sidebar.image(img, caption="AI Vision Input")

                # --- HYBRID PROMPT ---
                prompt = f"""
                Analyze this {manuscript_type} document in {doc_language}.
                
                TASK 1: Read Text (Name, Date).
                TASK 2: If it's a Chart/Wheel, identify Planet Signs.
                
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
                
                try:
                    txt = resp.text
                    json_str = txt[txt.find('{'):txt.rfind('}')+1]
                    data = json.loads(json_str)
                except:
                    st.error("AI Output was not valid JSON.")
                    st.stop()

                # Update State
                st.session_state['form_name'] = data.get('name', "")
                
                # Date Logic
                if data.get('date'):
                    st.session_state['form_dob'] = datetime.datetime.strptime(data['date'], "%Y-%m-%d").date()
                    st.sidebar.success("✅ Date found in text!")
                else:
                    # Fallback to Detective
                    st.sidebar.warning("Text date missing. Trying Planetary Detective...")
                    positions = data.get('positions', {})
                    clean_pos = {k: v for k, v in positions.items() if v} # Remove Nulls
                    
                    st.session_state['ai_debug'] = f"Planets Found: {clean_pos}"
                    
                    if clean_pos:
                        found_date = engine.find_date_from_positions(clean_pos)
                        if found_date:
                            st.session_state['form_dob'] = found_date
                            st.sidebar.success(f"🧮 Calculated Date: {found_date}")
                        else:
                            st.sidebar.error("Planets found, but no matching date (1900-2005).")
                    else:
                        st.sidebar.error("No planets visible for calculation.")

            except Exception as e:
                st.error(f"System Error: {e}")

    # Debug Info
    if st.session_state['ai_debug']: st.sidebar.info(st.session_state['ai_debug'])
    st.sidebar.markdown("---")

    # --- 3. MANUAL FORM (Restored!) ---
    with st.sidebar.form("details"):
        name = st.text_input("Name", st.session_state['form_name'])
        
        # Safe Date
        safe_dob = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990,1,1)
        dob = st.date_input("DOB", safe_dob)
        tob = st.time_input("Time", datetime.time(12,0))
        
        city = st.text_input("City", "Sambalpur")
        
        if st.form_submit_button("Generate Kundli"):
            lat, lon = get_lat_lon(city)
            chart = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
            
            # Display
            st.markdown(engine.generate_south_indian_svg(chart), unsafe_allow_html=True)
            st.info(f"Current Mahadasha: {chart['Current_Mahadasha']}")

if __name__ == "__main__":
    main()
