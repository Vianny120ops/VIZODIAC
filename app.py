"""
Vizodiac Ephemeris Service
Swiss Ephemeris real via Kerykeion — desplegado en Render.com (gratis)
Endpoint: POST /houses  { date, time, lat, lon, tz_offset }
"""
from flask import Flask, request, jsonify
from kerykeion import AstrologicalSubject
from datetime import datetime
import os

app = Flask(__name__)

# CORS — permite llamadas desde vizodiac.com y localhost
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

@app.route('/')
def health():
    return jsonify({'status': 'ok', 'service': 'Vizodiac Swiss Ephemeris', 'engine': 'kerykeion'})

@app.route('/houses', methods=['POST', 'OPTIONS'])
def calculate_houses():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json(force=True) or {}

        # Validar campos obligatorios
        required = ['date', 'lat', 'lon']
        for f in required:
            if f not in data:
                return jsonify({'error': f'Missing field: {f}'}), 400

        date_str  = data['date']          # "1990-05-15"
        time_str  = data.get('time', '12:00')  # "14:30"
        lat       = float(data['lat'])
        lon       = float(data['lon'])
        tz_offset = float(data.get('tz_offset', 0))  # offset en horas, ej: -3

        # Parsear fecha y hora
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        # Kerykeion — Swiss Ephemeris real
        subject = AstrologicalSubject(
            name        = "Chart",
            year        = dt.year,
            month       = dt.month,
            day         = dt.day,
            hour        = dt.hour,
            minute      = dt.minute,
            lat         = lat,
            lng         = lon,
            tz_str      = _offset_to_tz(tz_offset),
            houses_system_identifier = "P",   # Placidus (mismo sistema que el frontend)
            online      = False,
        )

        # Planetas con signos y casas
        planets = {}
        planet_keys = [
            'sun','moon','mercury','venus','mars',
            'jupiter','saturn','uranus','neptune','pluto','true_node'
        ]
        name_map = {
            'true_node': 'NorthNode',
            'sun': 'Sun', 'moon': 'Moon', 'mercury': 'Mercury',
            'venus': 'Venus', 'mars': 'Mars', 'jupiter': 'Jupiter',
            'saturn': 'Saturn', 'uranus': 'Uranus', 'neptune': 'Neptune',
            'pluto': 'Pluto',
        }
        signs_es = {
            'Ari':'Aries','Tau':'Tauro','Gem':'Géminis','Can':'Cáncer',
            'Leo':'Leo','Vir':'Virgo','Lib':'Libra','Sco':'Escorpio',
            'Sag':'Sagitario','Cap':'Capricornio','Aqu':'Acuario','Pis':'Piscis',
        }
        sign_full_es = {
            'Aries':'Aries','Taurus':'Tauro','Gemini':'Géminis','Cancer':'Cáncer',
            'Leo':'Leo','Virgo':'Virgo','Libra':'Libra','Scorpio':'Escorpio',
            'Sagittarius':'Sagitario','Capricorn':'Capricornio','Aquarius':'Acuario','Pisces':'Piscis',
        }

        for key in planet_keys:
            p = getattr(subject, key, None)
            if p is None:
                continue
            api_key = name_map.get(key, key.capitalize())
            sign_en = p.sign if hasattr(p, 'sign') else ''
            sign_es = sign_full_es.get(sign_en, signs_es.get(sign_en[:3], sign_en))
            planets[api_key] = {
                'sign':   sign_en,
                'signEs': sign_es,
                'deg':    int(p.position) if hasattr(p, 'position') else 0,
                'min':    int((p.position % 1) * 60) if hasattr(p, 'position') else 0,
                'house':  int(p.house_name[1]) if hasattr(p, 'house_name') and len(p.house_name) > 1 and p.house_name[1].isdigit() else _get_house_num(p),
                'lon':    round(float(p.abs_pos), 4) if hasattr(p, 'abs_pos') else 0,
            }

        # Casas — 12 cúspides en grados absolutos
        house_cusps = []
        for i in range(1, 13):
            h = getattr(subject, f'first_house' if i == 1 else f'house_{i}', None)
            # fallback directo al atributo houses
            if h is None:
                house_cusps.append(0)
            else:
                house_cusps.append(round(float(h.position) if hasattr(h, 'position') else float(h), 4))

        # Ascendente y MC
        asc = subject.first_house
        mc  = subject.tenth_house

        asc_sign_en = asc.sign if hasattr(asc, 'sign') else ''
        mc_sign_en  = mc.sign  if hasattr(mc,  'sign') else ''

        result = {
            'planets':    planets,
            'houses':     house_cusps,
            'ascendant': {
                'sign':   asc_sign_en,
                'signEs': sign_full_es.get(asc_sign_en, asc_sign_en),
                'deg':    int(asc.position) if hasattr(asc, 'position') else 0,
                'min':    int((asc.position % 1) * 60) if hasattr(asc, 'position') else 0,
            },
            'midheaven': {
                'sign':   mc_sign_en,
                'signEs': sign_full_es.get(mc_sign_en, mc_sign_en),
                'deg':    int(mc.position) if hasattr(mc, 'position') else 0,
            },
            'engine': 'swiss-ephemeris-kerykeion',
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _offset_to_tz(offset_hours):
    """Convierte offset numérico a nombre de timezone compatible con kerykeion."""
    offset = float(offset_hours)
    if offset == 0:   return 'UTC'
    if offset == -3:  return 'America/Argentina/Buenos_Aires'
    if offset == -4:  return 'America/Santiago'
    if offset == -5:  return 'America/Lima'
    if offset == -6:  return 'America/Mexico_City'
    if offset == -7:  return 'America/Denver'
    if offset == -8:  return 'America/Los_Angeles'
    if offset == -5:  return 'America/New_York'
    if offset == 1:   return 'Europe/Madrid'
    if offset == 2:   return 'Europe/Athens'
    if offset == 3:   return 'Europe/Moscow'
    if offset == 5.5: return 'Asia/Kolkata'
    if offset == 8:   return 'Asia/Shanghai'
    if offset == 9:   return 'Asia/Tokyo'
    # Genérico basado en offset
    sign = '+' if offset >= 0 else '-'
    h = int(abs(offset))
    m = int((abs(offset) % 1) * 60)
    return f'Etc/GMT{"-" if offset >= 0 else "+"}{h}'


def _get_house_num(planet):
    """Extrae número de casa de distintos formatos de kerykeion."""
    try:
        if hasattr(planet, 'house_name'):
            hn = str(planet.house_name)
            for i in range(12, 0, -1):
                if str(i) in hn:
                    return i
        if hasattr(planet, 'house'):
            return int(planet.house)
    except:
        pass
    return 1


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
