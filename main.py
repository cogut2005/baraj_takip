import os
import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import tweepy
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import gradio as gr

load_dotenv()
MD_FILE = "AI_Analysis.md"

def _read_md() -> str:
    p = Path(MD_FILE)
    return p.read_text(encoding="utf-8") if p.exists() else "# Henüz analiz yok"

def build_demo() -> gr.Blocks:
    with gr.Blocks() as demo:
        gr.Markdown(_read_md(), elem_id="md_output")
    return demo

def create_share_link() -> Optional[str]:
    demo = build_demo()
    app = demo.launch(share=True, prevent_thread_lock=True)
    return getattr(app, "share_url", None)

def parse_percentage(text: str, default: float = 0.0) -> float:
    try:
        cleaned = text.replace("%", "").replace(",", ".").strip()
        return float(cleaned)
    except (AttributeError, ValueError):
        return default

def _sum_row(row) -> float:
    if not row:
        return 0.0
    parent = row.find_parent("tr")
    if parent is None:
        return 0.0
    total = 0.0
    for cell in parent.find_all("td", class_="damtotaltd"):
        value = cell.get_text(strip=True)
        if not value:
            continue
        try:
            total += float(value.replace(".", "").replace(",", "."))
        except ValueError:
            continue
    return total

def _new_headless_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

def scrape_levels() -> Dict[str, float]:
    urls = {
        "İstanbul": "https://iski.istanbul/baraj-doluluk/",
        "Bursa": "https://www.buski.gov.tr/baraj-detay",
        "Ankara": "https://www.aski.gov.tr/tr/baraj.aspx",
        "İzmir": "https://www.izsu.gov.tr/tr/BarajlarinSuDurumu/1",
    }

    drv_ist = _new_headless_driver()
    drv_bur = _new_headless_driver()
    drv_ank = _new_headless_driver()
    drv_izm = _new_headless_driver()

    try:
        drv_ist.get(urls["İstanbul"])
        drv_bur.get(urls["Bursa"])
        drv_ank.get(urls["Ankara"])
        drv_izm.get(urls["İzmir"])
        time.sleep(2)

        soup1 = BeautifulSoup(drv_ist.page_source, "html.parser")
        r1 = soup1.find("div", class_="text-4xl font-bold absolute")
        ist = parse_percentage(r1.get_text(strip=True) if r1 else "", 0.0)
        print(f"İstanbul okundu: %{ist:.2f}")

        soup2 = BeautifulSoup(drv_bur.page_source, "html.parser")
        r2 = soup2.find("span", {"id": "baraj-doluluk-1-info"})
        bur = parse_percentage(r2.get_text(strip=True) if r2 else "", 0.0)
        print(f"Bursa okundu: %{bur:.2f}")

        soup3 = BeautifulSoup(drv_izm.page_source, "html.parser")
        toplam_row = soup3.find("span", string=lambda x: x and "Kullanılabilir göl su hacmi" in x)
        kullanilabilir_row = soup3.find("span", string=lambda x: x and "Kullanılabilir su hacmi" in x)
        toplam_sum = _sum_row(toplam_row)
        kullanilabilir_sum = _sum_row(kullanilabilir_row)
        izm = round(kullanilabilir_sum / toplam_sum * 100, 2) if toplam_sum else 0.0
        print(f"İzmir okundu: %{izm:.2f}")

        soup4 = BeautifulSoup(drv_ank.page_source, "html.parser")
        r4 = soup4.find("label", {"id": "LabelBarajOrani"})
        ank = parse_percentage(r4.get_text(strip=True) if r4 else "", 0.0)
        print(f"Ankara okundu: %{ank:.2f}")

        return {"İstanbul": ist, "Bursa": bur, "İzmir": izm, "Ankara": ank}
    finally:
        for d in (drv_ist, drv_bur, drv_ank, drv_izm):
            if d:
                d.quit()

def create_bar_chart(ist: float, bur: float, izm: float, ank: float) -> str:
    data = [("İstanbul", float(ist)), ("Bursa", float(bur)), ("İzmir", float(izm)), ("Ankara", float(ank))]
    data.sort(key=lambda x: x[1], reverse=True)
    cities = [c for c, _ in data]
    values = [v for _, v in data]

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    filename = f"baraj_doluluk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    fig, ax = plt.subplots(figsize=(10, 6), dpi=130)
    fig.patch.set_facecolor("#f7f8fa")
    ax.set_facecolor("#fcfdff")
    ax.grid(False)

    import matplotlib.colors as mcolors
    norm = mcolors.Normalize(vmin=0, vmax=100)
    cmap = plt.colormaps["RdYlGn"]
    colors = [cmap(norm(v)) for v in values]

    bars = ax.bar(cities, values, color=colors, edgecolor="#1b1e23", linewidth=0.6, zorder=3)

    ax.set_ylim(0, 100)
    ax.set_ylabel("Doluluk Oranı (%)", labelpad=8)
    ax.set_title("Baraj Doluluk Oranları", fontsize=16, weight="bold")
    ax.text(0.99, 1.02, f"Güncel: {ts}", ha="right", va="bottom", transform=ax.transAxes, fontsize=9, color="#5a6270")

    ax.text(0.5, 0.5, "@baraj_doluluk", transform=ax.transAxes, fontsize=60, color="#2b2b2b",
            alpha=0.06, ha="center", va="center", rotation=30, zorder=0)

    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2, f"{value:.2f}%",
                ha="center", va="bottom", fontsize=11, weight="bold", color="#1b1e23")

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#bfc7d5")
    ax.spines["bottom"].set_color("#bfc7d5")
    ax.tick_params(colors="#3b4150")

    fig.tight_layout(pad=1.5)
    fig.savefig(filename)
    plt.close(fig)
    print(f"Grafik kaydedildi: {filename}")
    return filename

def _accu_url_defaults() -> Dict[str, str]:
    return {
        "İstanbul": os.getenv("ACCU_IST_URL", "https://www.accuweather.com/tr/tr/istanbul/318251/daily-weather-forecast/318251"),
        "Bursa": os.getenv("ACCU_BURSA_URL", "https://www.accuweather.com/tr/tr/bursa/316938/daily-weather-forecast/316938"),
        "İzmir": os.getenv("ACCU_IZMIR_URL", "https://www.accuweather.com/tr/tr/izmir/318316/daily-weather-forecast/318316"),
        "Ankara": os.getenv("ACCU_ANKARA_URL", "https://www.accuweather.com/tr/tr/ankara/316938/daily-weather-forecast/316938"),
    }

def _parse_accu_15day(html: str) -> List[Dict[str, Any]]:
    bs = BeautifulSoup(html, "html.parser")
    cards = []
    for sel in [
        'a.daily-forecast-card', 'div.daily-forecast-card', 'li.daily-forecast-card',
        '[data-qa="daily-card"]', 'a[data-qa="daily-card"]', 'li[data-qa="daily-card"]',
        'div.forecast-list a', 'li.daily-card', 'div.daily-list a'
    ]:
        cards = bs.select(sel)
        if len(cards) >= 7:
            break
    out = []
    for i, c in enumerate(cards[:15]):
        text = c.get_text(" ", strip=True)
        highs = re.findall(r"(-?\d{1,2})°", text)
        h = int(highs[0]) if len(highs) >= 1 else None
        l = int(highs[1]) if len(highs) >= 2 else None
        m_prec = re.search(r"(\d{1,2})%", text)
        precip = int(m_prec.group(1)) if m_prec else None
        out.append({"day_index": i + 1, "text": text[:200], "high_c": h, "low_c": l, "precip_pct": precip})
    return out

def fetch_accuweather_15day(city: str, url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return []
    return _parse_accu_15day(resp.text)

def fetch_all_accuweather() -> Dict[str, Any]:
    urls = _accu_url_defaults()
    out = {}
    for city, url in urls.items():
        out[city] = fetch_accuweather_15day(city, url)
    print("AccuWeather 15 günlük veriler alındı")
    return out

def save_weather_json(weather_by_city: Dict[str, Any], filename: Optional[str] = None) -> str:
    if filename is None:
        filename = f"accuweather_15day_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(weather_by_city, f, ensure_ascii=False, indent=2)
    print(f"Hava durumu JSON kaydedildi: {filename}")
    return filename

def deepseek_summary_week(current_levels: Dict[str, float], weather_by_city: Dict[str, Any]) -> Optional[str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sen bir baraj su seviyesi tahmin asistanısın. "
                    "Istanbul, Bursa, İzmir, Ankara için mevcut su seviyeleri ve 15 günlük hava durumu (özellikle yağış) "
                    "göz önünde bulundurarak tam 2 hafta sonraki gün için baraj doluluk tahmininde bulun. "
                    "Aralık verme; net bir yüzde ver. Cevabını Türkçe ve Markdown formatında ver. "
                    "Yağmurun etkisini düşük; karın etkisini yüksek değerlendir. "
                    "Kar erimesi dönemlerinde artış bekle. "
                    "Her şehir için yeni satırda tahmin ver."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"current_levels_pct": current_levels, "weather_15day": weather_by_city, "window_days": 7},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=25,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    msg = data.get("choices", [{}])[0].get("message", {}).get("content")
    return " ".join(msg.strip().split()) if msg else None

def post_image_to_x(image_path: str, text: str) -> None:
    enabled = os.getenv("X_POST_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    text_only = os.getenv("X_TEXT_ONLY", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        print("X paylaşımı devre dışı")
        return
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
    if not all([api_key, api_secret, access_token, access_secret]):
        print("X kimlik bilgileri eksik")
        return
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api = tweepy.API(auth)
    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
    except Exception:
        client = None
    prepared_text = (text or "").strip()[:270] or "Baraj doluluk oranları"
    if text_only:
        if client:
            client.create_tweet(text=prepared_text)
            print("X metin v2 paylaşıldı")
            return
        api.update_status(status=prepared_text)
        print("X metin v1.1 paylaşıldı")
        return
    media = api.media_upload(image_path)
    api.update_status(status=prepared_text, media_ids=[media.media_id])
    print("X görsel v1.1 paylaşıldı")

def main() -> None:
    print("Baraj verileri çekiliyor...")
    levels = scrape_levels()
    print("Grafik oluşturuluyor...")
    png_path = create_bar_chart(levels["İstanbul"], levels["Bursa"], levels["İzmir"], levels["Ankara"])
    print("Hava durumu alınıyor...")
    weather_by_city = fetch_all_accuweather()
    weather_json_path = save_weather_json(weather_by_city)
    with open(weather_json_path, "r", encoding="utf-8") as f:
        weather_for_ai = json.load(f)
    print("AI tahmini üretiliyor...")
    ai_note = deepseek_summary_week(levels, weather_for_ai)
    share_url = None
    if ai_note:
        ts_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        Path(MD_FILE).write_text(f"# Yapay Zeka Tahmini ({ts_display})\n\n{ai_note}\n", encoding="utf-8")
        print("AI_Analysis.md güncellendi")
        print("Gradio linki oluşturuluyor...")
        share_url = create_share_link()
        if share_url:
            print(f"Gradio link: {share_url}")
    base_text = (
        f"İstanbul %{levels['İstanbul']:.2f} • "
        f"Bursa %{levels['Bursa']:.2f} • "
        f"İzmir %{levels['İzmir']:.2f} • "
        f"Ankara %{levels['Ankara']:.2f}"
    )
    tmpl = os.getenv("X_TWEET_TEXT")
    tweet_text = (
        tmpl.replace("{{IST}}", f"{levels['İstanbul']:.2f}")
            .replace("{{BURSA}}", f"{levels['Bursa']:.2f}")
            .replace("{{IZMIR}}", f"{levels['İzmir']:.2f}")
            .replace("{{ANKARA}}", f"{levels['Ankara']:.2f}")
    ) if tmpl else base_text
    if share_url:
        tweet_text = f"{tweet_text}\n{share_url}"
    print("X paylaşımı yapılıyor...")
    post_image_to_x(png_path, tweet_text)
    print("Tamamlandı")

if __name__ == "__main__":
    main()