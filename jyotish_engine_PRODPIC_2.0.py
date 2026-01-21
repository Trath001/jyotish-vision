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
        curr_date = datetime.date.today()
        run_date = birth_date + datetime.timedelta(days=self.dasha_years[start_lord_idx] * balance * 365.25)
        curr_lord_idx = start_lord_idx
        
        while run_date < curr_date:
            curr_lord_idx = (curr_lord_idx + 1) % 9
            run_date += datetime.timedelta(days=self.dasha_years[curr_lord_idx] * 365.25)
        return self.dasha_lords[curr_lord_idx]

    def calculate_chart(self, year, month, day, hour, minute, lat, lon):
        utc_dec = (hour + minute/60.0) - 5.5
        jd = swe.julday(year, month, day, utc_dec)
        ayanamsa = swe.get_ayanamsa_ut(jd)
        
        planets = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}
        chart = {}
        
        for p, pid in planets.items():
            pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
            chart[p] = {"sign": self.rashi_names[int(pos/30)], "degree": pos%30}
            
        asc_val = (swe.houses(jd, lat, lon)[1][0] - ayanamsa) % 360
        chart["Ascendant"] = {"sign": self.rashi_names[int(asc_val/30)], "degree": asc_val%30}
        
        # Calculate Moon Absolute for Dasha
        moon_abs = (self.rashi_names.index(chart["Moon"]["sign"]) * 30) + chart["Moon"]["degree"]
        chart["Current_Mahadasha"] = self.calculate_current_dasha(moon_abs, datetime.date(year, month, day))
        return chart

    # --- REVERSE SEARCH (FIXED) ---
    def find_date_from_positions(self, positions, start_year=1900, end_year=2000):
        # BUG FIX: If empty positions, return None immediately
        if not positions or len(positions) == 0:
            return None

        candidates = []
        curr = datetime.date(start_year, 1, 1)
        end = datetime.date(end_year, 12, 31)
        step = datetime.timedelta(days=15)
        
        pmap = {"Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}

        while curr <= end:
            jd = swe.julday(curr.year, curr.month, curr.day)
            match = True
            checks = 0
            
            for p, target in positions.items():
                if p in pmap and target:
                    checks += 1
                    pos = swe.calc_ut(jd, pmap[p], swe.FLG_SIDEREAL)[0][0]
                    sign = self.rashi_names[int(pos/30)]
                    if sign.lower() != target.lower():
                        match = False
                        break
            
            if match and checks > 0: candidates.append(curr)
            curr += step
            
        # Fine Search
        for cand in candidates:
            d = cand - datetime.timedelta(days=20)
            limit = cand + datetime.timedelta(days=20)
            while d <= limit:
                jd = swe.julday(d.year, d.month, d.day)
                score = 0
                req = 0
                for p, target in positions.items():
                    if target:
                        req += 1
                        pid = {"Sun": swe.SUN, "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE}.get(p)
                        if pid:
                            pos = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
                            if self.rashi_names[int(pos/30)].lower() == target.lower(): score += 1
                
                if score >= req: return d # Perfect match
                d += datetime.timedelta(days=1)
                
        return None

    def generate_svg(self, data):
        svg = ['<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" style="background:white"><rect width="400" height="400" fill="white" stroke="black"/>']
        # South Indian Layout
        pos_map = {"Pisces": (0,0), "Aries": (0,1), "Taurus": (0,2), "Gemini": (0,3), "Aquarius": (1,0), "Cancer": (1,3), "Capricorn": (2,0), "Leo": (2,3), "Sagittarius": (3,0), "Scorpio": (3,1), "Libra": (3,2), "Virgo": (3,3)}
        
        occ = {s: [] for s in pos_map}
        occ[data['Ascendant']['sign']].append("Asc")
        for p, d in data.items():
            if p not in ["Ascendant", "Current_Mahadasha"]: occ[d['sign']].append(p[:2])

        for s, (r, c) in pos_map.items():
            x, y = c*100, r*100
            svg.append(f'<rect x="{x}" y="{y}" width="100" height="100" fill="none" stroke="#ccc"/>')
            svg.append(f'<text x="{x+50}" y="{y+50}" fill="#eee" font-size="20" text-anchor="middle">{s[:3].upper()}</text>')
            for i, txt in enumerate(occ[s]):
                svg.append(f'<text x="{x+10}" y="{y+20+i*15}" fill="black" font-size="12">{txt}</text>')
        svg.append('</svg>')
        return "".join(svg)

# --- UI ---
def main():
    st.set_page_config(page_title="VedaVision Pro", layout="wide")
    engine = JyotishEngine()
    
    if 'dob' not in st.session_state: st.session_state['dob'] = datetime.date(1990,1,1)
    if 'debug' not in st.session_state: st.session_state['debug'] = ""

    st.sidebar.title("VedaVision Pro")
    mode = st.sidebar.radio("Mode", ["Vision (Auto)", "Manual Planets"])

    if mode == "Vision (Auto)":
        uploaded = st.sidebar.file_uploader("Upload Chart", type=["jpg", "png"])
        if uploaded and st.sidebar.button("Analyze"):
            img = Image.open(uploaded[0])
            st.sidebar.image(img, caption="Input")
            
            prompt = """
            Analyze this Odia Rashi Chakra (Circular Chart).
            Identify the Rashi (Sign) for: Jupiter, Saturn, Rahu, Mars.
            
            *Tip: In Odia charts, Mesha (Aries) is usually top-right or fixed.*
            
            RETURN JSON:
            {
                "Jupiter": "SignName (e.g. Leo)",
                "Saturn": "SignName",
                "Rahu": "SignName",
                "Mars": "SignName"
            }
            If you cannot see a planet, return null.
            """
            try:
                resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, img])
                txt = resp.text
                json_str = txt[txt.find('{'):txt.rfind('}')+1]
                positions = json.loads(json_str)
                
                # Clean None values
                clean_pos = {k: v for k, v in positions.items() if v}
                
                if not clean_pos:
                    st.error("❌ AI could not read any planets. Please switch to 'Manual Planets' mode.")
                else:
                    st.success(f"🔍 Found: {clean_pos}")
                    date = engine.find_date_from_positions(clean_pos)
                    if date:
                        st.session_state['dob'] = date
                        st.success(f"✅ Calculated DOB: {date}")
                    else:
                        st.warning("⚠️ Planets found, but no date match in 1900-2000.")
                        
            except Exception as e:
                st.error(f"Error: {e}")

    elif mode == "Manual Planets":
        st.sidebar.info("Enter planet positions if AI fails.")
        jup = st.sidebar.selectbox("Jupiter", [""] + engine.rashi_names)
        sat = st.sidebar.selectbox("Saturn", [""] + engine.rashi_names)
        rah = st.sidebar.selectbox("Rahu", [""] + engine.rashi_names)
        
        if st.sidebar.button("Calculate Date"):
            pos = {}
            if jup: pos["Jupiter"] = jup
            if sat: pos["Saturn"] = sat
            if rah: pos["Rahu"] = rah
            
            if pos:
                date = engine.find_date_from_positions(pos)
                if date:
                    st.session_state['dob'] = date
                    st.success(f"✅ Calculated DOB: {date}")
                else:
                    st.error("No match found.")
            else:
                st.warning("Select at least one planet.")

    # --- MAIN DISPLAY ---
    st.title("Kundli Output")
    dob = st.date_input("Date of Birth", st.session_state['dob'])
    tob = st.time_input("Time", datetime.time(12,0))
    
    if st.button("Generate Chart"):
        chart = engine.calculate_chart(dob.year, dob.month, dob.day, tob.hour, tob.minute, 21.46, 83.98)
        st.markdown(engine.generate_svg(chart), unsafe_allow_html=True)
        st.info(f"Current Mahadasha: {chart['Current_Mahadasha']}")

if __name__ == "__main__":
    main()
