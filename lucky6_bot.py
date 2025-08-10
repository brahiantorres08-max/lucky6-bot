import os
import requests
import time
from collections import Counter

# ==============================
# CONFIGURACIÓN TELEGRAM DESDE VARIABLES DE ENTORNO
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERROR: Falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en las variables de entorno.")
    exit(1)

# ==============================
# CONFIGURACIÓN DEL BOT DE RULETA
# ==============================
URL = "https://games.pragmaticplaylive.net/api/ui/statisticHistory"
PARAMS = {
    "tableId": "lucky6roulettea3",
    "numberOfGames": "500",
    "ck": "1754793929118",
    "game_mode": "roulette_desktop"
}
COOKIES = {"JSESSIONID": "elCR381vv7odd7MnyZuS9SLaH3RHOlrh2UEnAm3ldgzI4aiaq99q!-2001374018-772c6b4e"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://stake.com.co/"}

POLL_INTERVAL = 5
ANALYSIS_WINDOW = 100
BASE_BET = 1
STRATEGY = "martingale"  # o "dalembert"
MAX_MARTINGALE_STEPS = 6
THRESHOLD_DOCENA_OPCIONAL = 8

# ==============================
# FUNCIONES DE UTILIDAD
# ==============================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        r = requests.post(url, data=data)
        if r.status_code != 200:
            print(f"❌ Error enviando mensaje a Telegram: {r.text}")
    except Exception as e:
        print(f"❌ Excepción enviando mensaje a Telegram: {e}")

def fetch_history():
    try:
        r = requests.get(URL, params=PARAMS, cookies=COOKIES, headers=HEADERS, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("❌ Error al obtener history:", e)
        return None

def number_to_dozen(n):
    if n == 0:
        return None
    if 1 <= n <= 12:
        return 1
    if 13 <= n <= 24:
        return 2
    return 3

def parse_game_result_field(game_result_str):
    try:
        return int(game_result_str.strip().split()[0])
    except:
        return None

def analyze_docenas(history_list, window=ANALYSIS_WINDOW):
    nums = []
    recent = history_list[:window]
    for g in recent:
        n = parse_game_result_field(g.get("gameResult", ""))
        if n is not None:
            nums.append(n)
    docenas = [number_to_dozen(n) for n in nums if number_to_dozen(n) is not None]
    counts = Counter(docenas)
    for k in (1, 2, 3):
        counts.setdefault(k, 0)
    return counts, len(nums)

def choose_docenas(counts):
    sorted_items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    primaria = sorted_items[0][0]
    alternativa = sorted_items[1][0]
    prohibida = sorted_items[2][0]
    return primaria, alternativa, prohibida

def pretty_docena_name(d):
    return {1: "1-12", 2: "13-24", 3: "25-36"}.get(d, "Green/0")

def giros_sin_salir(history_list):
    tiempos = {1: 0, 2: 0, 3: 0}
    for g in history_list:
        n = parse_game_result_field(g.get("gameResult", ""))
        doc = number_to_dozen(n)
        for k in tiempos.keys():
            if tiempos[k] == 0 and doc != k:
                tiempos[k] += 1
            elif tiempos[k] > 0 and doc != k:
                tiempos[k] += 1
            elif doc == k:
                tiempos[k] = 0
    return tiempos

# Estrategias
class MartingaleState:
    def __init__(self, base=BASE_BET, max_steps=MAX_MARTINGALE_STEPS):
        self.base = base
        self.max_steps = max_steps
        self.step = 0

    def on_win(self):
        self.step = 0

    def on_loss(self):
        self.step = min(self.step + 1, self.max_steps)

    def next_bet(self):
        return self.base * (2 ** self.step)

class DAlembertState:
    def __init__(self, base=BASE_BET):
        self.base = base
        self.step = 0

    def on_win(self):
        if self.step > 0:
            self.step -= 1

    def on_loss(self):
        self.step += 1

    def next_bet(self):
        return max(self.base + self.step * self.base, self.base)

# ==============================
# MAIN LOOP
# ==============================
def main_loop():
    send_telegram("✅ Bot Lucky 6 iniciado correctamente en Railway")
    state = MartingaleState(BASE_BET, MAX_MARTINGALE_STEPS) if STRATEGY == "martingale" else DAlembertState(BASE_BET)
    last_seen_top_game_id = None

    while True:
        data = fetch_history()
        if not data:
            time.sleep(POLL_INTERVAL)
            continue

        history = data.get("history", [])
        if not history:
            time.sleep(POLL_INTERVAL)
            continue

        top_game = history[0]
        top_game_id = top_game.get("gameId")

        if top_game_id != last_seen_top_game_id:
            counts, total_numbers = analyze_docenas(history, ANALYSIS_WINDOW)
            primaria, alternativa, prohibida = choose_docenas(counts)
            tiempos_sin = giros_sin_salir(history)

            docena_opcional = None
            if tiempos_sin[prohibida] >= THRESHOLD_DOCENA_OPCIONAL:
                docena_opcional = prohibida

            next_bet_amount = state.next_bet()
            last_num = parse_game_result_field(top_game.get("gameResult", ""))
            last_doc = number_to_dozen(last_num)

            if last_doc == primaria:
                state.on_win()
                resultado = "GANASTE"
            else:
                state.on_loss()
                resultado = "PERDISTE"

            mensaje = (
                f"🎰 Lucky 6 Roulette - Nuevo giro detectado\n"
                f"Último número: {last_num}\n"
                f"Docena primaria: {pretty_docena_name(primaria)}\n"
                f"Docena alternativa: {pretty_docena_name(alternativa)}\n"
                f"Docena prohibida: {pretty_docena_name(prohibida)}\n"
                f"{'⚠️ Docena opcional: ' + pretty_docena_name(docena_opcional) if docena_opcional else ''}\n"
                f"Giros sin salir: {tiempos_sin}\n"
                f"Estrategia: {STRATEGY} | Próxima apuesta: {next_bet_amount}\n"
                f"Resultado anterior: {resultado}"
            )

            send_telegram(mensaje)
            print(mensaje)

            last_seen_top_game_id = top_game_id

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Bot detenido por usuario.")
