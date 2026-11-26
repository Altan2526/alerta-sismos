import html
import os
import re
import sys
from pathlib import Path
import requests

API_URL = "https://api.boostr.cl/earthquakes/recent.json"
STATE_FILE = Path("sismos_enviados.txt")
MAX_HISTORY = 50


def parse_magnitud(valor) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", str(valor))
    return float(match.group(1)) if match else 0.0


def cargar_enviados() -> list[str]:
    if not STATE_FILE.exists():
        return []
    return [
        line.strip()
        for line in STATE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def guardar_enviados(ids: list[str]) -> None:
    recientes = ids[-MAX_HISTORY:]
    STATE_FILE.write_text("\n".join(recientes) + "\n", encoding="utf-8")


def enviar_telegram(token: str, chat_id: str, mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "desconocido"
        raise RuntimeError(f"Error HTTP {status} al enviar mensaje a Telegram.") from None
    except requests.RequestException:
        raise RuntimeError("Error de conexión al comunicarse con Telegram.") from None


def formatear_mapa(lat, lon) -> str:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return ""
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return ""
    return (
        f'\n<b>Mapa:</b> <a href="https://maps.google.com/?q={lat_f:.5f},{lon_f:.5f}">'
        f"Ver epicentro</a>"
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    umbral = float(os.environ.get("MAGNITUD_MINIMA", "4.5"))

    if not token or not chat_id:
        print("Error: Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.", file=sys.stderr)
        sys.exit(1)

    resp = requests.get(API_URL, headers={"Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    datos = resp.json()

    sismos = datos.get("data", [])
    if not isinstance(sismos, list):
        print("Formato de respuesta inesperado.")
        return

    enviados = cargar_enviados()
    enviados_set = set(enviados)
    hubo_cambios = False

    for sismo in reversed(sismos):
        fecha = str(sismo.get("date", "")).strip()
        hora = str(sismo.get("hour", "")).strip()
        lugar = str(sismo.get("place", "Ubicación desconocida")).strip()
        magnitud = parse_magnitud(sismo.get("magnitude", 0))
        escala = str(sismo.get("scale", "")).strip()
        profundidad = str(sismo.get("depth", "N/A")).strip()
        lat = sismo.get("latitude")
        lon = sismo.get("longitude")

        if magnitud < umbral:
            continue

        sismo_id = f"{fecha}_{hora}_{lugar}"
        if sismo_id in enviados_set:
            continue

        escala_txt = f" {html.escape(escala)}" if escala else ""
        prof_txt = (
            profundidad
            if profundidad.lower().endswith("km") or profundidad == "N/A"
            else f"{profundidad} km"
        )
        maps_link = formatear_mapa(lat, lon)

        mensaje = (
            f"<b>Alerta de Sismo ({magnitud}{escala_txt})</b>\n"
            f"<b>Lugar:</b> {html.escape(lugar)}\n"
            f"<b>Fecha/Hora:</b> {html.escape(fecha)} {html.escape(hora)}\n"
            f"<b>Profundidad:</b> {html.escape(prof_txt)}"
            f"{maps_link}"
        )

        enviar_telegram(token, chat_id, mensaje)
        print(f"Notificado: {sismo_id} (Mag {magnitud})")

        enviados.append(sismo_id)
        enviados_set.add(sismo_id)
        hubo_cambios = True

    if hubo_cambios:
        guardar_enviados(enviados)
    else:
        print(f"Sin sismos nuevos >= {umbral}.")


if __name__ == "__main__":
    main()
