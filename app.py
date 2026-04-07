"""
Vizodiac Ephemeris Service — Swiss Ephemeris via Kerykeion 4.x
Cusp absolute position = SIGN_START + position_within_sign (0-30°)
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

SIGN_ES = {
    'Ari':'Aries','Tau':'Tauro','Gem':'Géminis','Can':'Cáncer',
    'Leo':'Leo','Vir':'Virgo','Lib':'Libra','Sco':'Escorpio',
    'Sag':'Sagitario','Cap':'Capricornio','Aqu':'Acuario','Pis':'Piscis',
}
SIGN_EN = {
    'Ari':'Aries','Tau':'Taurus','Gem':'Gemini','Can':'Cancer',
    'Leo':'Leo','Vir':'Virgo','Lib':'Libra','Sco':'Scorpio',
    'Sag':'Sagittarius','Cap':'Capricorn','Aqu':'Aquarius','Pis':'Pisces',
}
# Each zodiac sign starts at this ecliptic longitude
SIGN_DEG = {
    'Ari':0,'Tau':30,'Gem':60,'Can':90,'Leo':120,'Vir':150,
    'Lib':180,'Sco':210,'Sag':240,'Cap':270,'Aqu':300,'Pis':330,
}

def true_abs(point):
    """
    Returns the true absolute ecliptic longitude (0-360°) for any kerykeion point.
    Kerykeion 4.x stores abs_pos as position-within-sign (0-30°) for house cusps,
    so we reconstruct from sign_start + position_within_sign.
    """
    if point is None:
        return 0.0
    sign = str(getattr(point, 'sign', ''))
    pos  = float(getattr(point, 'position', 0))
    # Prefer reconstructed value — works for both planets and houses
    if sign in SIGN_DEG:
        return SIGN_DEG[sign] + pos
    # Fallback: use abs_pos directly (planets always have correct abs_pos)
    return float(getattr(point, 'abs_pos', 0))

def house_from_cusps(abs_pos, cusps):
    """Determine house number (1-12) by comparing planet position vs 12 cusp longitudes."""
    p = abs_pos % 360
    for i in range(12):
        s = cusps[i] % 360
        e = cusps[(i + 1) % 12] % 360
        if s < e:
            if s <= p < e:
                return i + 1
        else:  # wraps past 0°/360°
            if p >= s or p < e:
                return i + 1
    return 1

def offset_to_tz(offset_hours):
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
    sign = '-' if o >= 0 else '+'
    return f'Etc/GMT{sign}{int(abs(o))}'

@app.route('/')
def health():
    return jsonify({'status':'ok','service':'Vizodiac Swiss Ephemeris','engine':'kerykeion'})

@app.route('/debug', methods=['POST','OPTIONS'])
def debug_chart():
    """Diagnostic endpoint — shows raw kerykeion output + reconstructed cusps"""
    if request.method == 'OPTIONS':
        return '', 200
    data = request.get_json(force=True) or {}
    try:
        subject = AstrologicalSubject(
            name='Debug', year=int(data.get('year',1990)),
            month=int(data.get('month',3)), day=int(data.get('day',15)),
            hour=int(data.get('hour',12)), minute=int(data.get('minute',0)),
            lat=float(data.get('lat',0)), lng=float(data.get('lon',0)),
            tz_str=data.get('tz','UTC'),
            houses_system_identifier='P', online=False,
        )
        house_attrs = [
            'first_house','second_house','third_house','fourth_house',
            'fifth_house','sixth_house','seventh_house','eighth_house',
            'ninth_house','tenth_house','eleventh_house','twelfth_house',
        ]
        cusps_raw = {}
        cusps_reconstructed = {}
        for i, ha in enumerate(house_attrs):
            h = getattr(subject, ha, None)
            if h:
                cusps_raw[f'H{i+1}'] = {
                    'sign': str(getattr(h,'sign','')),
                    'position': float(getattr(h,'position',0)),
                    'abs_pos_raw': float(getattr(h,'abs_pos',0)),
                    'abs_pos_reconstructed': true_abs(h),
                }
        sun = subject.sun
        moon = subject.moon
        return jsonify({
            'sun':  {'sign':str(getattr(sun,'sign','')), 'position':float(getattr(sun,'position',0)), 'abs_pos':float(getattr(sun,'abs_pos',0))},
            'moon': {'sign':str(getattr(moon,'sign','')), 'position':float(getattr(moon,'position',0)), 'abs_pos':float(getattr(moon,'abs_pos',0))},
            'cusps': cusps_raw,
        })
    except Exception as e:
        import traceback
        return jsonify({'error':str(e), 'trace':traceback.format_exc()[-1200:]}), 500

@app.route('/houses', methods=['POST','OPTIONS'])
def calculate_houses():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data      = request.get_json(force=True) or {}
        date_str  = data.get('date','')
        time_str  = data.get('time','12:00')
        lat       = float(data.get('lat', 0))
        lon       = float(data.get('lon', 0))
        tz_offset = float(data.get('tz_offset', 0))

        if not date_str:
            return jsonify({'error':'Missing date'}), 400

        dt     = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        tz_str = offset_to_tz(tz_offset)

        subject = AstrologicalSubject(
            name   = 'Chart',
            year   = dt.year, month = dt.month, day = dt.day,
            hour   = dt.hour, minute = dt.minute,
            lat    = lat, lng = lon,
            tz_str = tz_str,
            houses_system_identifier = 'P',  # Placidus
            online = False,
        )

        # ── 1. Extract 12 cusp absolute longitudes ──
        # IMPORTANT: use true_abs() which reconstructs from sign+position
        # because kerykeion 4.x stores house abs_pos as within-sign degrees (0-30°)
        house_attrs = [
            'first_house','second_house','third_house','fourth_house',
            'fifth_house','sixth_house','seventh_house','eighth_house',
            'ninth_house','tenth_house','eleventh_house','twelfth_house',
        ]
        cusps = []
        for ha in house_attrs:
            h = getattr(subject, ha, None)
            cusps.append(round(true_abs(h), 4) if h else 0.0)

        # ── 2. Compute house number for each planet ──
        PLANET_ATTRS = {
            'sun':'Sun','moon':'Moon','mercury':'Mercury','venus':'Venus',
            'mars':'Mars','jupiter':'Jupiter','saturn':'Saturn',
            'uranus':'Uranus','neptune':'Neptune','pluto':'Pluto',
            'true_node':'NorthNode',
        }
        planets = {}
        for attr, api_key in PLANET_ATTRS.items():
            p = getattr(subject, attr, None)
            if p is None:
                continue
            abbr    = str(getattr(p,'sign',''))
            abs_pos = true_abs(p)          # planets: reconstructed = raw abs_pos
            pos     = float(getattr(p,'position', abs_pos % 30))
            house_n = house_from_cusps(abs_pos, cusps) if any(c > 0 for c in cusps) else None
            planets[api_key] = {
                'sign':   SIGN_EN.get(abbr, abbr),
                'signEs': SIGN_ES.get(abbr, abbr),
                'deg':    int(pos),
                'min':    int(round((pos % 1) * 60)),
                'lon':    round(abs_pos, 4),
                'house':  house_n,
            }

        # ── 3. Ascendant and MC ──
        asc = getattr(subject,'first_house',None)
        mc  = getattr(subject,'tenth_house', None)

        asc_abbr = str(getattr(asc,'sign','')) if asc else ''
        mc_abbr  = str(getattr(mc, 'sign','')) if mc  else ''
        asc_pos  = float(getattr(asc,'position',0)) if asc else 0
        mc_pos   = float(getattr(mc, 'position',0)) if mc  else 0

        return jsonify({
            'planets':   planets,
            'houses':    cusps,
            'ascendant': {
                'sign':   SIGN_EN.get(asc_abbr, asc_abbr),
                'signEs': SIGN_ES.get(asc_abbr, asc_abbr),
                'deg':    int(asc_pos),
                'min':    int(round((asc_pos % 1) * 60)),
            },
            'midheaven': {
                'sign':   SIGN_EN.get(mc_abbr, mc_abbr),
                'signEs': SIGN_ES.get(mc_abbr, mc_abbr),
                'deg':    int(mc_pos),
            },
            'engine': 'swiss-ephemeris',
        })

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()[-800:]}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
