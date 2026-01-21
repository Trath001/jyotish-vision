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
    # Safe fallback for local testing
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

    # --- FORWARD CALCULATION (Generate Kundli) ---
    def get_nakshatra(self, longitude):
        nakshatra_span = 13.33333333
        nakshatra_idx = int(longitude / nakshatra_span)
        if nakshatra_idx >= 27: nakshatra_idx = 0
        remainder = longitude % nakshatra_span
        pada = int(remainder / 3.33333333) + 1
        return self.nakshatra_names[nakshatra_idx], pada

    def calculate_current_dasha(self, moon_long, birth_date):
        nakshatra_span = 13.33333333
        nakshatra_idx = int(moon_long / nakshatra_span)
        position_in_nak = moon_long % nakshatra_span
        percentage_remaining = 1 - (position_in_nak / nakshatra_span)
        start_lord_idx = nakshatra_idx % 9
        balance_years = self.dasha_years[start_lord_idx] * percentage_remaining
        current_date = datetime.date.today()
        dasha_start_date = birth_date
        running_date = dasha_start_date + datetime.timedelta(days=balance_years * 365.25)
        current_lord_idx = start_lord_idx
        while running_date < current_date:
            current_lord_idx = (current_lord_idx + 1) % 9
            years = self.dasha_years[current_lord_idx]
            running_date += datetime.timedelta(days=years * 365.25)
        return self.dasha_lords[current_lord_idx]

    def calculate_chart(self, year, month, day, hour, minute, lat, lon, tz_offset=5.5):
        local_dt = datetime.datetime(year, month, day, hour, minute)
        utc_decimal_hour = (hour + minute/60.0) - tz_offset
        julian_day = swe.julday(year, month, day, utc_decimal_hour)
        ayanamsa = swe.get_ayanamsa_ut(julian_day)
        planets = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        chart_data = {}
        for name, pid in planets.items():
            pos = swe.calc_ut(julian_day, pid, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)[0][0]
            sign_idx = int(pos / 30)
            degree_in_sign = pos % 30
            nakshatra, pada = self.get_nakshatra(pos)
            chart_data[name] = {"sign": self.rashi_names[sign_idx], "degree": round(degree_in_sign, 2), "absolute_degree": pos, "nakshatra": nakshatra, "pada": pada}
        ketu_long = (chart_data["Rahu"]["absolute_degree"] + 180) % 360
        chart_data["Ketu"] = {"sign": self.rashi_names[int(ketu_long / 30)], "degree": round(ketu_long % 30, 2), "nakshatra": self.get_nakshatra(ketu_long)[0], "pada": self.get_nakshatra(ketu_long)[1]}
        houses_info = swe.houses(julian_day, lat, lon)[1]
        tropical_asc = houses_info[0]
        vedic_asc = (tropical_asc - ayanamsa) % 360
        chart_data["Ascendant"] = {"sign": self.rashi_names[int(vedic_asc / 30)], "degree": round(vedic_asc % 30, 2), "nakshatra": self.get_nakshatra(vedic_asc)[0], "pada": self.get_nakshatra(vedic_asc)[1]}
        birth_date_obj = datetime.date(year, month, day)
        chart_data["Current_Mahadasha"] = self.calculate_current_dasha(chart_data["Moon"]["absolute_degree"], birth_date_obj)
        return chart_data

    # --- REVERSE SEARCH (Planetary Detective) ---
    def find_date_from_positions(self, observed_positions, start_year=1950, end_year=2005):
        start_date = datetime.date(start_year, 1, 1)
        end_date = datetime.date(end_year, 12, 31)
        delta = datetime.timedelta(days=15)
        current_date = start_date
        candidates = []
        planet_map = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}

        while current_date <= end_date:
            jd = swe.julday(current_date.year, current_date.month, current_date.day)
            match_score, total_checked = 0, 0
            for p_name, p_sign in observed_positions.items():
                if p_name not in ["Jupiter", "Saturn", "Rahu"]: continue
                pid = planet_map.get(p_name)
                if pid:
                    pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                    curr_sign = self.rashi_names[int(pos / 30)]
                    if curr_sign.lower() == p_sign.lower(): match_score += 1
                    total_checked += 1
            if total_checked > 0 and match_score == total_checked: candidates.append(current_date)
            current_date += delta
        
        for cand in candidates:
            search_start, search_end = cand - datetime.timedelta(days=20), cand + datetime.timedelta(days=20)
            d = search_start
            while d <= search_end:
                jd = swe.julday(d.year, d.month, d.day)
                daily_score = 0
                required = 0
                for p_name, p_sign in observed_positions.items():
                    pid = planet_map.get(p_name)
                    if pid:
                        required += 1
                        pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                        if self.rashi_names[int(pos / 30)].lower() == p_sign.lower(): daily_score += 1
                if daily_score >= required - 1: return d
                d += datetime.timedelta(days=1)
        return None

    def generate_south_indian_svg(self, chart_data):
        layout = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        sign_occupants = {sign: [] for sign in layout.keys()}
        sign_occupants[chart_data['Ascendant']['sign']].append("Asc")
        for planet in chart_data:
            if planet not in ["Ascendant", "Current_Mahadasha"]:
                p_sign = chart_data[planet]['sign']
                sign_occupants[p_sign].append(f"{planet[:2]} {int(chart_data[planet]['degree'])}°")
        svg = ['<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: #fff;">', '<rect x="2" y="2" width="396" height="396" fill="none" stroke="#333" stroke-width="2"/>']
        box_w, box_h = 100, 100
        for sign, (row, col) in layout.items():
            x = col * box_w
            y = row * box_h
            svg.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="none" stroke="#ddd" stroke-width="1"/>')
            svg.append(f'<text x="{x+50}" y="{y+50}" text-anchor="middle" fill="#f0f0f0" font-size="14" font-weight="bold">{sign[:3].upper()}</text>')
            y_offset = 20
            for item in sign_occupants[sign]:
                color = "red" if item == "Asc" else "black"
                weight = "bold" if item == "Asc" else "normal"
                svg.append(f'<text x="{x+5}" y="{y+y_offset}" fill="{color}" font-weight="{weight}" font-size="12" font-family="Arial">{item}</text>')
                y_offset += 15
        svg.append(f'<text x="200" y="190" text-anchor="middle" font-size="16" fill="#333" font-weight="bold">RASHI CHART</text>')
        svg.append(f'<text x="200" y="215" text-anchor="middle" font-size="12" fill="#666">Running Dasha: {chart_data["Current_Mahadasha"]}</text>')
        svg.append('</svg>')
        return "".join(svg)

# --- HELPER FUNCTIONS ---
def enhance_manuscript(image):
    image = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.5) 
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(3.0)
    return image

def get_lat_lon(city_name):
    if "sambalpur" in city_name.lower() or "burla" in city_name.lower(): return 21.46, 83.98
    if "jaykaypur" in city_name.lower() or "jk paper" in city_name.lower(): return 19.25, 83.42 
    if "rayagada" in city_name.lower(): return 19.17, 83.41
    geolocator = Nominatim(user_agent="jyotish_mitra_app")
    try:
        location = geolocator.geocode(city_name)
        if location: return location.latitude, location.longitude
        return None, None
    except: return None, None

# --- MAIN APP UI ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide")
    engine = JyotishEngine()
    
    # Initialize Session State
    if 'form_name' not in st.session_state: st.session_state['form_name'] = ""
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = None
    if 'form_tob' not in st.session_state: st.session_state['form_tob'] = datetime.time(12, 0)
    if 'form_city' not in st.session_state: st.session_state['form_city'] = ""
    if 'ai_debug' not in st.session_state: st.session_state['ai_debug'] = ""

    st.sidebar.title("VedaVision Pro")
    
    # --- UI 1: OPTIONS ---
    doc_language = st.sidebar.selectbox("Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "English"])
    manuscript_type = st.sidebar.radio("Manuscript Type", ["Modern Paper (Blue Ink)", "Palm Leaf (Talapatra)"])
    
    st.sidebar.markdown("### 🛠 Tools")
    rotation = st.sidebar.select_slider("Rotate Image", options=[0, 90, 180, 270], value=0)

    # --- UI 2: UPLOAD ---
    uploaded_files = st.sidebar.file_uploader("Upload Image(s)", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    if uploaded_files:
        if st.sidebar.button("Analyze & Decode"):
            with st.spinner("AI analyzing manuscript..."):
                try:
                    img = Image.open(uploaded_files[0])
                    if rotation != 0: img = img.rotate(-rotation, expand=True)
                    
                    if manuscript_type == "Palm Leaf (Talapatra)":
                        img = enhance_manuscript(img)
                        st.sidebar.image(img, caption="Enhanced View", use_column_width=True)
                    else:
                        st.sidebar.image(img, caption="Standard View", use_column_width=True)

                    # --- PROMPT LOGIC ---
                    if manuscript_type == "Modern Paper (Blue Ink)":
                        # OCR PROMPT
                        prompt = f"""
                        You are an expert Paleographer. Read this {doc_language} Paper Manuscript.
                        1. Find Name (after Namni/Nama).
                        2. Find Place (after Gram/Jilla).
                        3. Find Date/Time (Odia numerals).
                        RETURN JSON: {{"name": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "city": "..."}}
                        """
                    else:
                        # TALAPATRA + PLANETARY DETECTIVE PROMPT
                        prompt = f"""
                        You are an expert reading an Ancient {doc_language} Rashi Chakra (Chart).
                        
                        **TASK 1: Extract Positions from the Wheel Diagram.**
                        - Identify signs: Mesha (Aries) to Meena (Pisces).
                        - Identify planets: Surya, Chandra, Mangala, Budha, Guru (Jupiter), Shukra, Shani (Saturn), Rahu.
                        
                        **TASK 2: Extract Text.**
                        - Name near 'Sriman'.
                        - Date text if visible.

                        RETURN JSON: 
                        {{
                            "positions": {{ "Jupiter": "Sign", "Saturn": "Sign", "Rahu": "Sign", "Mars": "Sign" }},
                            "name": "...", 
                            "date": null, 
                            "time": null,
                            "city": null
                        }}
                        *Return 'date': null if not written as text. We will calculate it from positions.*
                        """
                    
                    response = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                    txt = response.text
                    json_str = txt[txt.find('{'):txt.rfind('}')+1]
                    data = json.loads(json_str)

                    # --- SAVE RESULTS ---
                    st.session_state['form_name'] = data.get('name') or ""
                    st.session_state['form_city'] = data.get('city') or ""
                    
                    # Date Handling
                    date_found = False
                    if data.get('date'):
                        try:
                            clean_date = data['date'].replace('/', '-').replace('.', '-')
                            st.session_state['form_dob'] = datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
                            date_found = True
                        except: pass
                    
                    if data.get('time'):
                        try:
                            st.session_state['form_tob'] = datetime.datetime.strptime(data['time'], "%H:%M").time()
                        except: pass

                    # --- TRIGGER DETECTIVE IF DATE MISSING ---
                    if not date_found and manuscript_type == "Palm Leaf (Talapatra)":
                        positions = data.get('positions', {})
                        st.session_state['ai_debug'] = f"📅 Calculating date from planets: {positions}"
                        if positions:
                            found_date = engine.find_date_from_positions(positions)
                            if found_date:
                                st.session_state['form_dob'] = found_date
                                st.sidebar.success(f"🧮 Calculated Date from Planets: {found_date}")
                            else:
                                st.sidebar.warning("Could not calculate date from chart. Please enter manually.")

                    st.sidebar.success("Done!")

                except Exception as e:
                    st.sidebar.error(f"Error: {e}")

    # --- UI 3: DEBUG INFO ---
    if st.session_state['ai_debug']:
        st.sidebar.info(st.session_state['ai_debug'])

    st.sidebar.markdown("---")

    # --- UI 4: MANUAL FORM (RESTORED!) ---
    with st.sidebar.form("birth_details"):
        name = st.text_input("Name", st.session_state['form_name'])
        
        default_date = st.session_state['form_dob'] if st.session_state['form_dob'] else datetime.date(1990, 1, 1)
        dob = st.date_input("Date of Birth", default_date, min_value=datetime.date(1800, 1, 1))
        
        default_time = st.session_state['form_tob'] if st.session_state['form_tob'] else datetime.time(12, 0)
        tob = st.time_input("Time of Birth", default_time)
        
        manual_coords = st.checkbox("Enter Coordinates Manually?")
        if manual_coords:
            col_a, col_b = st.columns(2)
            with col_a: lat = st.number_input("Latitude", value=21.46)
            with col_b: lon = st.number_input("Longitude", value=83.98)
        else:
            city = st.text_input("Birth City", st.session_state['form_city'])
            lat, lon = 0.0, 0.0
        
        submit = st.form_submit_button("Generate Kundli")

    # --- UI 5: OUTPUT ---
    if submit:
        if not manual_coords:
            with st.spinner(f"Locating {city}..."):
                lat, lon = get_lat_lon(city)
                if lat is None: st.error(f"City '{city}' not found.")
        
        if lat:
            chart_data = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon)
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(engine.generate_south_indian_svg(chart_data), unsafe_allow_html=True)
                st.info(f"**Mahadasha:** {chart_data['Current_Mahadasha']}")
            with col2:
                st.subheader(f"Ask about {name}'s chart")
                user_q = st.chat_input("Ex: Health prediction?")
                if user_q:
                    with st.spinner("Consulting..."):
                        context = f"Chart: {chart_data}"
                        res = client.models.generate_content(model='gemini-2.0-flash', contents=f"Role: Vedic Astrologer. Context: {context}. Question: {user_q}")
                        st.markdown(res.text)

if __name__ == "__main__":
    main()
