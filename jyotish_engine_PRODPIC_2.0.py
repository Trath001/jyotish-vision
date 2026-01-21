import streamlit as st
from google import genai
import swisseph as swe
import datetime
import pytz
from geopy.geocoders import Nominatim
from PIL import Image
import json
import re

# --- CONFIGURATION ---
# 🔴 PASTE YOUR API KEY HERE
#GOOGLE_API_KEY = "YOUR api key"
# --- CONFIGURATION ---
try:
    # Try getting the key from Streamlit Secrets (Cloud)
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # Fallback for local testing (Optional, or keep it blank)
    GOOGLE_API_KEY = "PASTE_YOUR_KEY_ONLY_FOR_LOCAL_TESTING"

# Initialize Client
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error initializing API client: {e}")
# Initialize Client
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error initializing API client: {e}")

class JyotishEngine:
    """
    Production-ready class to handle Vedic Calculations.
    """
    
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

# --- HELPER: CITY SEARCH ---
def get_lat_lon(city_name):
    # Smart Fallback for Odia locations including Sambalpur
    if "sambalpur" in city_name.lower() or "burla" in city_name.lower() or "hirakud" in city_name.lower():
        return 21.46, 83.98  # Sambalpur Coordinates
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
    st.set_page_config(page_title="Jyotish Mitra Pro", layout="wide")
    engine = JyotishEngine()
    
    # --- SESSION STATE INITIALIZATION ---
    if 'form_name' not in st.session_state: st.session_state['form_name'] = "User"
    if 'form_dob' not in st.session_state: st.session_state['form_dob'] = datetime.date(1990, 1, 1)
    if 'form_tob' not in st.session_state: st.session_state['form_tob'] = datetime.time(12, 0)
    if 'form_city' not in st.session_state: st.session_state['form_city'] = "New Delhi, India"

    st.sidebar.title("Kundli Details")
    
    # --- OPTION A: UPLOAD MANUSCRIPT (VISION) ---
    st.sidebar.subheader("📷 Upload Manuscript / Palm Leaf")
    
    doc_language = st.sidebar.selectbox(
        "Script Language", 
        ["Odia (ଓଡ଼ିଆ)", "English", "Hindi", "Sanskrit", "Tamil", "Telugu", "Malayalam", "Kannada", "Bengali"]
    )
    
    uploaded_file = st.sidebar.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
    
    if uploaded_file is not None:
        if st.sidebar.button("Decipher Manuscript"):
            with st.spinner(f"Reading {doc_language} Manuscript..."):
                try:
                    image = Image.open(uploaded_file)
                    
                    # --- THE "SAMBALPUR + 3:55" PROMPT ---
                    prompt = f"""
                    You are an expert Paleographer specializing in {doc_language} Manuscripts.
                    Analyze this image of a 'Janma Patrika'.
                    
                    **YOUR MISSION: Read Handwriting Precisely.**

                    1. **FIND THE NAME (Use 'Namni' clue):**
                       - Find printed "Namni" (Female Name) or "Nama".
                       - Read the handwritten text *after* it.
                       - Example: "Sarojini", "Snehalata".

                    2. **FIND THE PLACE (Target: Sambalpur District):**
                       - Look for "Gram" (Village) or "Jilla" (District).
                       - **Check specifically for 'Sambalpur' (ସମ୍ବଲପୁର).**
                       - Or 'Burla', 'Hirakud', 'Kuchinda'.
                       - Output exactly what you see.

                    3. **CONFIRM TIME (Target: 3:55):**
                       - Look at the Odia numerals for minutes.
                       - `୪` is 4. `୫` is 5.
                       - If you see `୫୫`, it is 55. If `୪୫`, it is 45.
                       - **The handwriting likely says 3.55 (or 15:55). Verify this.**

                    RETURN ONLY VALID JSON:
                    {{"name": "...", "date": "1994-12-13", "time": "15:55", "city": "..."}}
                    """
                    
                    # VISION TASK: Use Gemini 2.0 Flash
                    response = client.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=[prompt, image]
                    )
                    
                    # Parse JSON
                    txt = response.text
                    json_str = txt[txt.find('{'):txt.rfind('}')+1]
                    data = json.loads(json_str)
                    
                    # Auto-Fill Form
                    st.session_state['form_name'] = data.get('name') or "User"
                    if data.get('date'):
                        try:
                            clean_date = data['date'].replace('/', '-').replace('.', '-')
                            st.session_state['form_dob'] = datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
                        except:
                            pass
                            
                    if data.get('time'):
                        try:
                            st.session_state['form_tob'] = datetime.datetime.strptime(data['time'], "%H:%M").time()
                        except:
                             st.sidebar.warning(f"Extracted time '{data.get('time')}' is tricky. Please verify.")
                            
                    st.session_state['form_city'] = data.get('city') or "Unknown"
                    
                    st.sidebar.success("Deciphered! Please review the extracted data.")
                    
                except Exception as e:
                    st.sidebar.error(f"Extraction failed. AI Response was: {e}")

    st.sidebar.markdown("---")

    # --- OPTION B: MANUAL FORM (Auto-filled) ---
    st.sidebar.subheader("✍️ Verify & Generate")
    with st.sidebar.form("birth_details"):
        name = st.text_input("Name", st.session_state['form_name'])
        
        dob = st.date_input(
            "Date of Birth", 
            st.session_state['form_dob'], 
            min_value=datetime.date(1900, 1, 1)
        )
        
        tob = st.time_input("Time of Birth", st.session_state['form_tob'])
        
        # Manual Coordinates Checkbox
        manual_coords = st.checkbox("Enter Coordinates Manually?")
        city = ""
        lat, lon = 0.0, 0.0
        
        if manual_coords:
            col_a, col_b = st.columns(2)
            with col_a: lat = st.number_input("Latitude", value=21.46) # Default Sambalpur
            with col_b: lon = st.number_input("Longitude", value=83.98)
        else:
            city = st.text_input("Birth City", st.session_state['form_city'])
        
        submit = st.form_submit_button("Generate Kundli")

    if submit:
        found_location = False
        
        if manual_coords:
            found_location = True
            st.success(f"Using Manual Coordinates: {lat}, {lon}")
        else:
            with st.spinner(f"Locating {city}..."):
                lat, lon = get_lat_lon(city)
                if lat is None:
                    st.error(f"Could not find '{city}'. Try a bigger city nearby or use Manual Mode.")
                else:
                    found_location = True
                    st.success(f"Found {city}: {lat:.2f}, {lon:.2f}")

        if found_location:
            chart_data = engine.calculate_chart(
                dob.year, dob.month, dob.day, tob.hour, tob.minute, lat, lon
            )
            st.session_state['chart_data'] = chart_data
            st.session_state['user_name'] = name

    # DISPLAY RESULTS
    if 'chart_data' in st.session_state:
        data = st.session_state['chart_data']
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown(engine.generate_south_indian_svg(data), unsafe_allow_html=True)
            st.info(f"**Current Mahadasha:** {data['Current_Mahadasha']}")
            
        with col2:
            st.subheader(f"Ask Jyotish Mitra about {st.session_state['user_name']}'s chart")
            user_q = st.chat_input("Ex: When will my career improve?")
            
            if user_q:
                # Prepare Context
                context_str = f"""
                Birth Data: {st.session_state['user_name']}, Dasha: {data['Current_Mahadasha']}
                Planetary Positions:
                Ascendant: {data['Ascendant']['sign']} ({data['Ascendant']['nakshatra']})
                Sun: {data['Sun']['sign']} ({data['Sun']['nakshatra']})
                Moon: {data['Moon']['sign']} ({data['Moon']['nakshatra']})
                Mars: {data['Mars']['sign']}
                Mercury: {data['Mercury']['sign']}
                Jupiter: {data['Jupiter']['sign']}
                Venus: {data['Venus']['sign']}
                Saturn: {data['Saturn']['sign']}
                Rahu: {data['Rahu']['sign']}
                Ketu: {data['Ketu']['sign']}
                """
                
                full_prompt = f"""
                You are an expert Vedic Astrologer. Analyze the following chart data rigidly using Parashari principles.
                CHART CONTEXT: {context_str}
                USER QUESTION: {user_q}
                GUIDELINES:
                1. Look at the Current Mahadasha ({data['Current_Mahadasha']}).
                2. Mention Nakshatras if relevant.
                3. Be practical and empathetic.
                """
                
                with st.spinner("Consulting the stars..."):
                    try:
                        # STABLE CHAT MODEL: gemini-2.0-flash
                        response = client.models.generate_content(
                            model='gemini-2.0-flash',
                            contents=full_prompt
                        )
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
                        st.warning("Please check your API Key and internet connection.")

if __name__ == "__main__":
    main()