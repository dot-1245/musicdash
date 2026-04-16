from flask import Flask, render_template, jsonify, request
import subprocess
import urllib.parse
import requests
import os
import colorsys
from PIL import Image
from io import BytesIO

app = Flask(__name__)
current_player = ""

def get_dominant_color(url):
    try:
        if not url: return "#888888"
        img = None
        if url.startswith('file://'):
            path = urllib.parse.unquote(url.replace('file://', ''))
            if os.path.exists(path): img = Image.open(path)
        elif url.startswith('http'):
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=2)
            img = Image.open(BytesIO(response.content))
        
        if img:
            img = img.convert('RGB')
            w, h = img.size
            img = img.crop((w*0.2, h*0.2, w*0.8, h*0.8))
            img = img.resize((16, 16), resample=Image.Resampling.LANCZOS)
            
            pixels = []
            for y in range(img.height):
                for x in range(img.width):
                    pixels.append(img.getpixel((x, y)))

            def score_color(c):
                r, g, b = [v/255.0 for v in c]
                h, l, s = colorsys.rgb_to_hls(r, g, b)
                if l < 0.1 or l > 0.9: return -1 
                return s + (l * 0.5)

            best = max(pixels, key=score_color)
            r, g, b = [v/255.0 for v in best]
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            
            # AMOLED/Darkでも沈まないよう輝度を補正
            if l < 0.5: l = 0.6 
            if s < 0.3: s = 0.5 
            
            nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
            return '#{:02x}{:02x}{:02x}'.format(int(nr*255), int(ng*255), int(nb*255))
    except: pass
    return "#888888"

@app.route('/')
def index(): return render_template('index.html')

@app.route('/test_color')
def test_color():
    global current_player
    p = current_player
    art_url = run_playerctl(["metadata", "mpris:artUrl"], p)
    accent = get_dominant_color(art_url)
    return f"""
    <body style="background:{accent};margin:0;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
        <div style="background:white;padding:30px;border-radius:20px;text-align:center;">
            <h1>Color Debugger</h1>
            <p>HEX: <b>{accent}</b></p>
            <img src="{art_url.replace('file://','')}" style="width:200px;border-radius:10px;border:3px solid #ccc;">
            <br><br><button onclick="location.reload()">REFRESH</button>
            <p><a href="/">Back to Home</a></p>
        </div>
    </body>
    """

@app.route('/api/metadata')
def get_metadata():
    global current_player
    p = current_player
    players = [x for x in run_playerctl(["-l"]).split('\n') if x]
    try:
        art_url = run_playerctl(["metadata", "mpris:artUrl"], p)
        accent = get_dominant_color(art_url)
        vol_raw = run_playerctl(["volume"], p)
        volume = float(vol_raw) if vol_raw else 0.0
        pos = float(run_playerctl(["position"], p) or 0)
        length = float(run_playerctl(["metadata", "mpris:length"], p) or 0) / 1000000
    except: accent, volume, pos, length = "#888888", 0.0, 0, 0
    return jsonify({
        "title": run_playerctl(["metadata", "xesam:title"], p) or "No Media",
        "artist": run_playerctl(["metadata", "xesam:artist"], p) or "-",
        "art_url": art_url, "accent_color": accent,
        "status": run_playerctl(["status"], p), "position": pos, "length": length,
        "volume": volume, "shuffle": run_playerctl(["shuffle"], p) == "On",
        "loop": run_playerctl(["loop"], p), "players": players, "active_player": p or "Auto Select"
    })

def run_playerctl(command, target_player=None):
    try:
        prefix = ["playerctl"]
        if target_player: prefix += ["--player", target_player]
        return subprocess.check_output(prefix + command).decode('utf-8').strip()
    except: return ""

@app.route('/api/control/<action>')
def control(action):
    global current_player
    p = current_player
    if not p:
        all_p = [x for x in run_playerctl(["-l"]).split('\n') if x]; p = all_p[0] if all_p else ""
    if action == "vol_up" or action == "vol_down":
        try:
            curr = float(run_playerctl(["volume"], p) or 0)
            new_v = max(0.0, min(1.0, curr + 0.05 if action == "vol_up" else curr - 0.05))
            subprocess.run(["playerctl", "-p", p, "volume", f"{new_v:.2f}"])
        except: pass
    elif action == "seek":
        val = request.args.get('offset')
        subprocess.run(["playerctl", "-p", p, "position", str(val)])
    elif action == "shuffle":
        curr = run_playerctl(["shuffle"], p); subprocess.run(["playerctl", "-p", p, "shuffle", "Off" if curr == "On" else "On"])
    elif action == "loop":
        curr = run_playerctl(["loop"], p); subprocess.run(["playerctl", "-p", p, "loop", "Track" if curr == "None" else "None"])
    else: subprocess.run(["playerctl", "-p", p, action])
    return jsonify({"status": "success"})

@app.route('/api/select_player/<path:name>')
def select_player(name):
    global current_player
    current_player = "" if urllib.parse.unquote(name) == "auto" else urllib.parse.unquote(name)
    return jsonify({"status": "selected"})

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)
