"""
Vizodiac Ephemeris Service — Swiss Ephemeris via Kerykeion 4.x
Endpoint: POST /houses  { date, time, lat, lon, tz_offset }
"""
from flask import Flask, request, jsonify
from kerykeion import AstrologicalSubject
from datetime import datetime
import os

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

# Kerykeion 4.x: planet.house devuelve strings como "First_House"
HOUSE_MAP = {
    'First_House':1,'Second_House':2,'Third_House':3,'Fourth_House':4,
    'Fifth_House':5,'Sixth_House':6,'Seventh_House':7,'Eighth_House':8,
    'Ninth_House':9,'Tenth_House':10,'Eleventh_House':11,'Twelfth_House':12,
}

# Kerykeion 4.x: planet.sign devuelve abreviatura de 3 letras
SIGN_SHORT_ES = {
    'Ari':'Aries','Tau':'Tauro','Gem':'Géminis','Can':'Cáncer',
    'Leo':'Leo','Vir':'Virgo','Lib':'Libra','Sco':'Escorpio',
    'Sag':'Sagitario','Cap':'Capricornio','Aqu':'Acuario','Pis':'Piscis',
}
SIGN_SHORT_EN = {
    'Ari':'Aries','Tau':'Taurus','Gem':'Gemini','Can':'Cancer',
    'Leo':'Leo','Vir':'Virgo','Lib':'Libra','Sco':'Scorpio',
    'Sag':'Sagittarius','Cap':'Capricorn','Aqu':'Aquarius','Pis':'Pisces',
}

def sign_es(abbr):
    return SIGN_SHORT_ES.get(abbr, abbr)

def sign_en(abbr):
    return SIGN_SHORT_EN.get(abbr, abbr)

def get_house_num(planet):
    """Extrae número de casa 1-12 del objeto planeta de kerykeion 4.x"""
    try:
        h = str(getattr(planet, 'house', '') or '')
        if h in HOUSE_MAP:
            return HOUSE_MAP[h]
        # Fallback: buscar número en el string
        h_lower = h.lower()
        for name, num in [('twelfth',12),('eleventh',11),('tenth',10),('ninth',9),
                          ('eighth',8),('seventh',7),('sixth',6),('fifth',5),
                          ('fourth',4),('third',3),('second',2),('first',1)]:
            if name in h_lower:
                return num
    except:
        pass
    return None  # None = no disponible, no inventamos

@app.route('/')
def health():
    return jsonify({'status':'ok','service':'Vizodiac Swiss Ephemeris','engine':'kerykeion-4.x'})

@app.route('/houses', methods=['POST','OPTIONS'])
def calculate_houses():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json(force=True) or {}

        date_str  = data.get('date','')
        time_str  = data.get('time','12:00')
        lat       = float(data.get('lat', 0))
        lon       = float(data.get('lon', 0))
        tz_offset = float(data.get('tz_offset', 0))

        if not date_str or (not lat and not lon):
            return jsonify({'error':'Missing date or coordinates'}), 400

        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        tz_str = _offset_to_tz(tz_offset, lon)

        subject = AstrologicalSubject(
            name     = "Chart",
            year     = dt.year,
            month    = dt.month,
            day      = dt.day,
            hour     = dt.hour,
            minute   = dt.minute,
            lat      = lat,
            lng      = lon,
            tz_str   = tz_str,
            houses_system_identifier = "P",  # Placidus
            online   = False,
        )

        # ── Planetas ──
        PLANET_ATTRS = {
            'Sun':'Sun','Moon':'Moon','Mercury':'Mercury','Venus':'Venus',
            'Mars':'Mars','Jupiter':'Jupiter','Saturn':'Saturn',
            'Uranus':'Uranus','Neptune':'Neptune','Pluto':'Pluto',
            'true_node':'NorthNode',
        }
        planets = {}
        for attr, api_key in PLANET_ATTRS.items():
            p = getattr(subject, attr, None)
            if p is None:
                continue
            abbr    = str(getattr(p,'sign',''))
            deg_abs = float(getattr(p,'abs_pos', 0))
            pos     = float(getattr(p,'position', deg_abs % 30))
            house_n = get_house_num(p)
            planets[api_key] = {
                'sign':   sign_en(abbr),
                'signEs': sign_es(abbr),
                'deg':    int(pos),
                'min':    int((pos % 1) * 60),
                'lon':    round(deg_abs, 4),
                'house':  house_n,
            }

        # ── Casas: 12 cúspides en grados absolutos ──
        house_attrs = [
            'first_house','second_house','third_house','fourth_house',
            'fifth_house','sixth_house','seventh_house','eighth_house',
            'ninth_house','tenth_house','eleventh_house','twelfth_house',
        ]
        house_cusps = []
        for ha in house_attrs:
            h = getattr(subject, ha, None)
            if h is not None:
                house_cusps.append(round(float(getattr(h,'abs_pos', 0)), 4))
            else:
                house_cusps.append(0)

        # ── Ascendente y MC ──
        asc_obj = getattr(subject, 'first_house', None)
        mc_obj  = getattr(subject, 'tenth_house', None)

        asc_abbr = str(getattr(asc_obj,'sign','')) if asc_obj else ''
        mc_abbr  = str(getattr(mc_obj, 'sign','')) if mc_obj  else ''
        asc_pos  = float(getattr(asc_obj,'position', 0)) if asc_obj else 0
        mc_pos   = float(getattr(mc_obj, 'position', 0)) if mc_obj  else 0

        result = {
            'planets':   planets,
            'houses':    house_cusps,
            'ascendant': {
                'sign':   sign_en(asc_abbr),
                'signEs': sign_es(asc_abbr),
                'deg':    int(asc_pos),
                'min':    int((asc_pos % 1) * 60),
            },
            'midheaven': {
                'sign':   sign_en(mc_abbr),
                'signEs': sign_es(mc_abbr),
                'deg':    int(mc_pos),
            },
            'engine': 'swiss-ephemeris-kerykeion',
        }
        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()[-500:]}), 500


def _offset_to_tz(offset_hours, lon=0):
    """Convierte offset UTC a nombre IANA de timezone."""
    o = float(offset_hours)
    table = {
        -12:'Etc/GMT+12',-11:'Pacific/Pago_Pago',-10:'Pacific/Honolulu',
        -9:'America/Anchorage',-8:'America/Los_Angeles',-7:'America/Denver',
        -6:'America/Mexico_City',-5:'America/Lima',-4:'America/Caracas',
        -3:'America/Argentina/Buenos_Aires',-2:'Atlantic/South_Georgia',
        -1:'Atlantic/Azores',0:'UTC',1:'Europe/Madrid',2:'Europe/Athens',
        3:'Europe/Moscow',4:'Asia/Dubai',5:'Asia/Karachi',
        5.5:'Asia/Kolkata',6:'Asia/Dhaka',7:'Asia/Bangkok',
        8:'Asia/Shanghai',9:'Asia/Tokyo',10:'Australia/Sydney',
        11:'Pacific/Noumea',12:'Pacific/Auckland',
    }
    if o in table:
        return table[o]
    # Genérico
    sign = '-' if o >= 0 else '+'
    return f'Etc/GMT{sign}{int(abs(o))}'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

              
