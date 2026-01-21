import streamlit as st
from google import genai
import swisseph as swe
import datetime
import pytz
from geopy.geocoders import Nominatim
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import json
import re

# --- CONFIGURATION ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    GOOGLE_API_KEY = "PASTE_YOUR_API_KEY_HERE_FOR_LOCAL_TESTING"

# Initialize Client
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error initializing API client: {e}")

class JyotishEngine:
    # ... (Keep the __init__, get_nakshatra, calculate_current_dasha, calculate_chart, generate_south_indian_svg, get_lat_lon methods EXACTLY the same as before) ...
    
    def __init__(self):
        # Set Lahiri Ayanamsa (Critical for Vedic accuracy)
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.rashi_names = [
            "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", 
            "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
        ]
        self.nakshatra_names = [
            "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", 
            "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", 
            "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", 
            "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", 
            "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
        ]
        self.dasha_lords = [
            "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
        ]
        self.dasha_years = [7, 20, 6, 10, 7, 18, 16, 19, 17]

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
        
        # Calculate Ayanamsa for Ascendant Correction
        ayanamsa = swe.get_ayanamsa_ut(julian_day)
        
        planets = {
            "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
            "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, 
            "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE
        }

        chart_data = {}

        for name, pid in planets.items():
            pos = swe.calc_ut(julian_day, pid, swe.FLG_SIDEREAL | swe.FLG_SWIEPH)[0][0]
            sign_idx = int(pos / 30)
            degree_in_sign = pos % 30
            nakshatra, pada = self.get_nakshatra(pos)
            
            chart_data[name] = {
                "sign": self.rashi_names[sign_idx],
                "degree": round(degree_in_sign, 2),
                "absolute_degree": pos,
                "nakshatra": nakshatra,
                "pada": pada
            }
            
        ketu_long = (chart_data["Rahu"]["absolute_degree"] + 180) % 360
        chart_data["Ketu"] = {
            "sign": self.rashi_names[int(ketu_long / 30)],
            "degree": round(ketu_long % 30, 2),
            "nakshatra": self.get_nakshatra(ketu_long)[0],
            "pada": self.get_nakshatra(ketu_long)[1]
        }

        houses_info = swe.houses(julian_day, lat, lon)[1]
        tropical_asc = houses_info[0]
        vedic_asc = (tropical_asc - ayanamsa) % 360
        
        chart_data["Ascendant"] = {
            "sign": self.rashi_names[int(vedic_asc / 30)],
            "degree": round(vedic_asc % 30, 2),
            "nakshatra": self.get_nakshatra(vedic_asc)[0],
            "pada": self.get_nakshatra(vedic_asc)[1]
        }
        
        birth_date_obj = datetime.date(year, month, day)
        chart_data["Current_Mahadasha"] = self.calculate_current_dasha(
            chart_data["Moon"]["absolute_degree"], birth_date_obj
        )

        return chart_data

    def generate_south_indian_svg(self, chart_data):
        layout = {
            "Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3),
            "Aquarius": (1,0),                                "Cancer": (1,3),
            "Capricorn": (2,0),                               "Leo": (2,3),
            "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)
        }
        
        sign_occupants = {sign: [] for sign in layout.keys()}
        sign_occupants[chart_data['Ascendant']['sign']].append("Asc")
        
        for planet in chart_data:
            if planet not in ["Ascendant", "Current_Mahadasha"]:
                p_sign = chart_data[planet]['sign']
                sign_occupants[p_sign].append(f"{planet[:2]} {int(chart_data[planet]['degree'])}°")

        svg = ['<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background-color: #fff;">']
        svg.append('<rect x="2" y="2" width="396" height="396" fill="none" stroke="#333" stroke-width="2"/>')
        
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
    
# --- HELPER: ADVANCED TALAPATRA ENHANCER ---
def enhance_manuscript(image):
    # 1. Convert to Grayscale (Removes the pink/red color distraction)
    image = ImageOps.grayscale(image)
    
    # 2. Increase Contrast dramatically to make etchings stand out
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.5) 
    
    # 3. Sharpen edges to define the Karani script
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(3.0)
    
    return image

# --- HELPER: CITY SEARCH ---
def get_lat_lon(city_name):
    if "sambalpur" in city_name.lower() or "burla" in city_name.lower() or "hirakud" in city_name.lower():
        return 21.46, 83.98
    if "jaykaypur" in city_name.lower() or "jk paper" in city_name.lower():
        return 19.25, 83.42 
    if "rayagada" in city_name.lower():
        return 19.17, 83.41
        
    geolocator = Nominatim(user_agent="jyotish_mitra_app")
    try:
        location = geolocator.geocode(city_name)
        if location:
            return location.latitude, location.longitude
        return None, None
    except:
        return None, None

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="VedaVision AI", layout="wide")
    engine = JyotishEngine()
    
    if 'form_name' not in st.session_state: st.session_state['form_name'] = "User"
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = datetime.date(1990, 1, 1)
    if 'form_tob' not in st.session_state: st.session_state['form_tob'] = datetime.time(12, 0)
    if 'form_city' not in st.session_state: st.session_state['form_city'] = "New Delhi, India"

    st.sidebar.title("Kundli Decoder")
    
    # --- RESTORED: LANGUAGE SELECTOR ---
    doc_language = st.sidebar.selectbox(
        "Script Language", 
        ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "English", "Telugu"]
    )

    # --- MANUSCRIPT TYPE SELECTOR ---
    manuscript_type = st.sidebar.radio(
        "Select Manuscript Type",
        ["Modern Paper (Blue Ink)", "Palm Leaf (Talapatra)"]
    )
    
    # --- NEW: ROTATION CONTROL ---
    if manuscript_type == "Palm Leaf (Talapatra)":
        rotation = st.sidebar.select_slider("Rotate Image (If vertical)", options=[0, 90, 180, 270], value=0)
    else:
        rotation = 0

    uploaded_files = st.sidebar.file_uploader(
        "Upload Images (Front/Back)", 
        type=["jpg", "png", "jpeg"], 
        accept_multiple_files=True
    )
    
    if uploaded_files:
        if st.sidebar.button("Decipher Manuscript"):
            with st.spinner(f"Analyzing {manuscript_type} in {doc_language}..."):
                try:
                    # Process the first image
                    image = Image.open(uploaded_files[0])
                    
                    # APPLY ROTATION
                    if rotation != 0:
                        image = image.rotate(-rotation, expand=True) # Negative for Clockwise feel

                    # Apply enhancement ONLY for Talapatra
                    if manuscript_type == "Palm Leaf (Talapatra)":
                        image = enhance_manuscript(image)
                        st.sidebar.image(image, caption=f"AI Input (Enhanced + Rotated {rotation}°)", use_column_width=True)

                    # --- DYNAMIC PROMPT SELECTION ---
                    if manuscript_type == "Modern Paper (Blue Ink)":
                        prompt = f"""
                        You are an expert Paleographer specializing in {doc_language} Paper Manuscripts.
                        Analyze this image of a 'Janma Patrika'.
                        
                        **YOUR MISSION: Read Handwriting (Blue Ink) Precisely.**
                        1. **FIND THE NAME:** Look for 'Namni' (Female) or 'Nama'. Read text after it.
                        2. **FIND THE PLACE:** Look for 'Gram' or 'Jilla'. Check for 'Sambalpur', 'Rayagada', 'Jaykaypur'.
                        3. **CONFIRM TIME:** Look at Odia numerals. `୫`=5, `୪`=4. (e.g. `୫୫`=55).
                        
                        RETURN JSON: {{"name": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "city": "..."}}
                        """
                    else:
                        # --- STRONGER TALAPATRA PROMPT ---
                        prompt = f"""
                        You are an expert Paleographer specializing in Ancient {doc_language} Palm Leaf (Talapatra) Manuscripts.
                        The image has been converted to Grayscale and High Contrast to show the etchings.
                        
                        **YOUR MISSION: Decode the Incised Karani Script.**
                        1. **ORIENTATION CHECK:** Ensure you are reading the lines horizontally.
                        2. **FIND THE CHART:** Look for the Rashi Chakra (Circular Chart).
                        3. **FIND NUMERALS:** Look for Odia numerals embedded in the text.
                        4. **DETECT KEYWORDS:** Look for "Saka", "San", "Masa" (Month), "Dina" (Day).
                        
                        RETURN JSON: {{"name": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "city": "Unknown"}}
                        """
                    
                    response = client.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=[prompt, image]
                    )
                    
                    # Parse JSON safely
                    txt = response.text
                    json_str = txt[txt.find('{'):txt.rfind('}')+1]
                    data = json.loads(json_str)
                    
                    # Auto-Fill
                    st.session_state['form_name'] = data.get('name') or "User"
                    if data.get('date'):
                        try:
                            clean_date = data['date'].replace('/', '-').replace('.', '-')
                            st.session_state['form_dob'] = datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
                        except: pass
                    if data.get('time'):
                        try:
                            st.session_state['form_tob'] = datetime.datetime.strptime(data['time'], "%H:%M").time()
                        except: pass
                    st.session_state['form_city'] = data.get('city') or "Unknown"
                    
                    st.sidebar.success("Deciphered! Please review fields below.")
                    
                except Exception as e:
                    st.sidebar.error(f"Extraction failed. AI Response: {e}")

    st.sidebar.markdown("---")

    # --- MANUAL FORM ---
    with st.sidebar.form("birth_details"):
        name = st.text_input("Name", st.session_state['form_name'])
        dob = st.date_input("Date of Birth", st.session_state['form_dob'], min_value=datetime.date(1900, 1, 1))
        tob = st.time_input("Time of Birth", st.session_state['form_tob'])
        
        manual_coords = st.checkbox("Enter Coordinates Manually?")
        if manual_coords:
            col_a, col_b = st.columns(2)
            with col_a: lat = st.number_input("Latitude", value=21.46)
            with col_b: lon = st.number_input("Longitude", value=83.98)
        else:
            city = st.text_input("Birth City", st.session_state['form_city'])
            lat, lon = 0.0, 0.0
        
        submit = st.form_submit_button("Generate Kundli")

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
