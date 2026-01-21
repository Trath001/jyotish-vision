import streamlit as st
from google import genai
import swisseph as swe
import datetime
from PIL import Image, ImageOps, ImageEnhance
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
    st.error(f"Error initializing API client: {e}")

class JyotishEngine:
    def __init__(self):
        swe.set_sid_mode(swe.SIDM_LAHIRI) # Vedic Sidereal
        self.rashi_names = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
    
    # --- THE NEW "TIME DETECTIVE" FUNCTION ---
    def find_date_from_positions(self, observed_positions, start_year=1960, end_year=2000):
        """
        Scans history to find a date matching the observed planetary chart.
        observed_positions: {'Jupiter': 'Leo', 'Saturn': 'Virgo', ...}
        """
        best_date = None
        best_score = 0
        
        # We search one day at a time. 
        # Optimization: We check Jupiter/Saturn first (slow movers) to skip huge chunks of time.
        
        start_date = datetime.date(start_year, 1, 1)
        end_date = datetime.date(end_year, 12, 31)
        delta = datetime.timedelta(days=15) # Check every 15 days for broad match first
        
        current_date = start_date
        
        candidates = []

        # Mapping planet names to SwissEph IDs
        planet_map = {
            "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, 
            "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, 
            "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE
        }

        # 1. BROAD SEARCH (Step by 15 days)
        while current_date <= end_date:
            julian_day = swe.julday(current_date.year, current_date.month, current_date.day)
            
            # Check Slow Moving Planets (Jupiter, Saturn, Rahu) first
            match_score = 0
            total_checked = 0
            
            for p_name, p_sign in observed_positions.items():
                if p_name not in ["Jupiter", "Saturn", "Rahu"]: continue
                
                pid = planet_map.get(p_name)
                if pid is None: continue
                
                pos = swe.calc_ut(julian_day, pid, swe.FLG_SIDEREAL)[0][0]
                sign_index = int(pos / 30)
                curr_sign = self.rashi_names[sign_index]
                
                if curr_sign.lower() == p_sign.lower():
                    match_score += 1
                total_checked += 1
            
            # If slow planets match, save this "Era" to check daily
            if total_checked > 0 and match_score == total_checked:
                candidates.append(current_date)
            
            current_date += delta

        # 2. FINE SEARCH (Check daily around candidates)
        final_match = None
        
        for cand in candidates:
            # Search +/- 20 days around the candidate
            search_start = cand - datetime.timedelta(days=20)
            search_end = cand + datetime.timedelta(days=20)
            
            d = search_start
            while d <= search_end:
                jd = swe.julday(d.year, d.month, d.day)
                daily_score = 0
                required_score = len(observed_positions)
                
                for p_name, p_sign in observed_positions.items():
                    pid = planet_map.get(p_name)
                    if pid is None: 
                        required_score -= 1 # Skip unknown planets
                        continue
                        
                    pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                    sign_index = int(pos / 30)
                    curr_sign = self.rashi_names[sign_index]
                    
                    if curr_sign.lower() == p_sign.lower():
                        daily_score += 1
                
                # If we have a very high match (allow 1 planet error for Moon/interpretation)
                if daily_score >= required_score - 1:
                    return d # Found it!
                
                d += datetime.timedelta(days=1)
                
        return None

# --- HELPER: TALAPATRA ENHANCER ---
def enhance_manuscript(image):
    image = ImageOps.grayscale(image)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0) 
    return image

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide")
    engine = JyotishEngine()
    
    st.sidebar.title("VedaVision Pro")
    st.sidebar.caption("Optical & Astronomical Decoder")

    # --- INPUTS ---
    doc_language = st.sidebar.selectbox("Language", ["Odia (ଓଡ଼ିଆ)", "Sanskrit", "Hindi", "Telugu"])
    # ROTATION
    rotation = st.sidebar.select_slider("Rotate Image", options=[0, 90, 180, 270], value=0)

    uploaded_files = st.sidebar.file_uploader("Upload Manuscript", type=["jpg", "png", "jpeg"], accept_multiple_files=True)
    
    # --- SESSION STATE ---
    if 'calc_date' not in st.session_state: st.session_state['calc_date'] = None
    
    if uploaded_files:
        if st.sidebar.button("Decode Chart & Find Date"):
            with st.spinner("Step 1: AI Reading Planetary Chart..."):
                try:
                    img = Image.open(uploaded_files[0])
                    if rotation != 0: img = img.rotate(-rotation, expand=True)
                    img = enhance_manuscript(img)
                    st.sidebar.image(img, caption="Enhanced Input")

                    # --- 1. VISION: EXTRACT POSITIONS ---
                    prompt = f"""
                    You are an expert Vedic Astrologer reading an Ancient {doc_language} Chart (Rashi Chakra).
                    
                    **TASK:** Look at the chart squares/circles. Identify which sign each planet is in.
                    - Signs (Odia): Mesha, Vrisha, Mithuna, Karkata, Simha, Kanya, Tula, Vrischika, Dhanu, Makara, Kumbha, Meena.
                    - Planets: Sun (Surya/Rabi), Moon (Chandra), Mars (Mangala/Kuja), Mercury (Budha), Jupiter (Guru/Brihaspati), Venus (Shukra), Saturn (Shani), Rahu, Ketu.

                    **OUTPUT JSON ONLY:**
                    {{
                        "positions": {{
                            "Sun": "SignName",
                            "Moon": "SignName",
                            "Mars": "SignName",
                            "Jupiter": "SignName",
                            "Saturn": "SignName",
                            "Rahu": "SignName"
                        }},
                        "name": "Extracted Name if visible",
                        "text_date": "Extracted Date if visible (optional)"
                    }}
                    *Use English Sign Names (Aries, Taurus, etc.). If a planet is unclear, omit it.*
                    """
                    
                    response = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                    
                    # Clean JSON
                    txt = response.text
                    json_str = txt[txt.find('{'):txt.rfind('}')+1]
                    data = json.loads(json_str)
                    
                    positions = data.get("positions", {})
                    st.write(f"**🔍 AI Detected Positions:** {positions}")
                    
                    # --- 2. MATH: REVERSE SEARCH DATE ---
                    if positions:
                        with st.spinner("Step 2: Scanning years 1960-2000 for match..."):
                            found_date = engine.find_date_from_positions(positions)
                            
                            if found_date:
                                st.success(f"✅ **MATCH FOUND!** The planets align on: **{found_date}**")
                                st.session_state['calc_date'] = found_date
                            else:
                                st.warning("⚠️ No exact date match found between 1960-2000. Try checking the extracted positions above.")
                    else:
                        st.error("Could not extract planetary positions. Try rotating the image.")

                except Exception as e:
                    st.error(f"Error: {e}")

    # --- DISPLAY RESULTS ---
    if st.session_state.get('calc_date'):
        d = st.session_state['calc_date']
        st.header(f"Calculated DOB: {d}")
        # (You can add the Kundli generation call here using `d`)

if __name__ == "__main__":
    main()
