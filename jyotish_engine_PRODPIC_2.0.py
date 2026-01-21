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
