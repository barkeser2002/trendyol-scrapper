import json
import os
import threading
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, send_file
import requests

from trendyol_search import export_to_excel, search_trendyol

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1424874950891933726/_hByuiX4mfxuW0hNLUMj_hX8b_hxJY0a1HTS41WL4OB5eKpOc1HRZndWDy1yCcWlU32G",
)
DISCORD_USERNAME = os.getenv("DISCORD_USERNAME", "Trendyol Scraper")

jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()


def update_job(job_id: str, **fields) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.update(fields)


def build_progress_callback(job_id: str):
    def _callback(current: int, total: int, stage: str, message: str) -> None:
        percent = 0
        if total:
            percent = max(0, min(100, int(current * 100 / total)))
        update_job(
            job_id,
            current=current,
            total=total,
            progress=percent,
            stage=stage,
            message=message,
        )

    return _callback


def extract_client_info(req) -> Dict[str, Optional[str]]:
    forwarded_for = req.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = req.headers.get("X-Real-IP") or req.remote_addr

    return {
        "ip": ip_address or "Bilinmiyor",
        "user_agent": req.headers.get("User-Agent", "Bilinmiyor"),
        "referer": req.headers.get("Referer"),
        "accept_language": req.headers.get("Accept-Language"),
    }


def build_product_highlights(rows: List[Dict[str, Any]], limit: int = 5) -> str:
    highlights: List[str] = []
    for row in rows[:limit]:
        name = row.get("Product Name") or row.get("product_name") or row.get("name") or "Ürün adı yok"
        merchant = row.get("Merchant Name") or row.get("merchantName") or row.get("merchant") or "Satıcı bilinmiyor"
        price = row.get("Price Text") or row.get("price_text") or row.get("price") or "Fiyat belirtilmedi"
        highlights.append(f"• {name} | {merchant} | {price}")
    return "\n".join(highlights) if highlights else "Kayıt listesi boş."


def send_discord_notification(
    job_id: str,
    query: str,
    rows: List[Dict[str, Any]],
    file_path: Optional[str],
    status: str,
    message: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    if not DISCORD_WEBHOOK_URL:
        return

    with jobs_lock:
        job_snapshot = dict(jobs.get(job_id, {}))

    client_info = job_snapshot.get("client_info", {}) if isinstance(job_snapshot, dict) else {}
    visitor_name = job_snapshot.get("visitor_name") if isinstance(job_snapshot, dict) else None
    max_pages = job_snapshot.get("max_pages") if isinstance(job_snapshot, dict) else None
    highlights = build_product_highlights(rows)

    embed = {
        "title": "Yeni arama kaydı",
        "color": 0x57F287 if status == "completed" else 0xED4245,
        "fields": [
            {"name": "Arama Terimi", "value": query or "(boş)", "inline": False},
            {"name": "Toplam Satır", "value": str(len(rows)), "inline": True},
            {
                "name": "İstemci IP",
                "value": client_info.get("ip") or "Bilinmiyor",
                "inline": True,
            },
            {
                "name": "Tarayıcı",
                "value": (client_info.get("user_agent") or "Bilinmiyor")[:1024],
                "inline": False,
            },
        ],
        "footer": {"text": f"İş ID: {job_id}"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if visitor_name:
        embed["fields"].insert(1, {"name": "Kullanıcı", "value": visitor_name[:256], "inline": True})
    if max_pages:
        embed["fields"].insert(2, {"name": "Sayfa Limiti", "value": str(max_pages), "inline": True})

    embed["fields"].append({"name": "Durum", "value": status.capitalize(), "inline": True})

    referer = client_info.get("referer")
    if referer:
        embed["fields"].append({"name": "Referer", "value": referer[:1024], "inline": False})

    accept_language = client_info.get("accept_language")
    if accept_language:
        embed["fields"].append(
            {"name": "Accept-Language", "value": accept_language[:1024], "inline": False}
        )

    if status == "completed" and rows:
        embed["fields"].append({"name": "Örnek Kayıtlar", "value": highlights[:1024], "inline": False})

    if message:
        embed["fields"].append({"name": "Mesaj", "value": message[:1024], "inline": False})

    if error:
        embed["fields"].append({"name": "Hata", "value": error[:1024], "inline": False})

    if status == "completed" and rows:
        content = "Trendyol araması başarıyla tamamlandı."
    elif status == "completed":
        content = "Trendyol araması tamamlandı ancak ürün bulunamadı."
    else:
        content = "Trendyol araması sırasında bir sorun oluştu."

    payload = {
        "username": DISCORD_USERNAME,
        "content": content,
        "embeds": [embed],
    }

    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as excel_file:
                files = {
                    "file": (
                        os.path.basename(file_path),
                        excel_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }
                data = {"payload_json": json.dumps(payload, ensure_ascii=False)}
                response = requests.post(
                    DISCORD_WEBHOOK_URL,
                    data=data,
                    files=files,
                    timeout=30,
                )
        else:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=30,
            )

        if response.status_code >= 400:
            app.logger.error("Discord webhook çağrısı başarısız oldu: %s - %s", response.status_code, response.text)
    except Exception:  # pylint: disable=broad-except
        app.logger.exception("Discord webhook gönderilirken hata oluştu")


def run_search_job(job_id: str, query: str, max_pages: int) -> None:
    update_job(job_id, status="running", message="Arama başlatıldı", stage="initializing")
    try:
        rows = search_trendyol(
            query,
            headless=True,
            progress_callback=build_progress_callback(job_id),
            max_pages=max_pages,
        )
        file_path = None
        if rows:
            file_path = os.path.join(OUTPUT_DIR, f"trendyol_products_{job_id}.xlsx")
            export_to_excel(rows, output_path=file_path)
            update_job(
                job_id,
                status="completed",
                progress=100,
                message=f"{len(rows)} satır başarıyla kaydedildi.",
                stage="completed",
                file_path=file_path,
            )
            send_discord_notification(
                job_id,
                query,
                rows,
                file_path,
                status="completed",
                message=f"{len(rows)} satır başarıyla kaydedildi.",
            )
        else:
            update_job(
                job_id,
                status="completed",
                progress=100,
                message="Ürün bulunamadı.",
                stage="completed",
                file_path=file_path,
            )
            send_discord_notification(
                job_id,
                query,
                [],
                None,
                status="completed",
                message="Ürün bulunamadı.",
            )
    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        update_job(
            job_id,
            status="failed",
            progress=100,
            message=str(exc),
            stage="failed",
            error=str(exc),
        )
        send_discord_notification(
            job_id,
            query,
            [],
            None,
            status="failed",
            message="Arama sırasında hata oluştu.",
            error=str(exc),
        )


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def start_search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    visitor_name = (data.get("visitor_name") or "").strip()
    max_pages_raw = data.get("max_pages")
    if not query:
        return jsonify({"error": "Arama terimi gerekli."}), 400
    if not visitor_name:
        return jsonify({"error": "İsim gerekli."}), 400
    if max_pages_raw is None:
        return jsonify({"error": "Sayfa sayısı gerekli."}), 400

    try:
        max_pages = int(max_pages_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Sayfa sayısı sayı olarak gönderilmelidir."}), 400
    if max_pages < 1 or max_pages > 50:
        return jsonify({"error": "Sayfa sayısı 1 ile 50 arasında olmalıdır."}), 400

    job_id = uuid.uuid4().hex
    client_info = extract_client_info(request)
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "query": query,
            "status": "queued",
            "progress": 0,
            "message": "İş kuyruğa alındı.",
            "stage": "queued",
            "current": 0,
            "total": 0,
            "file_path": None,
            "created_at": datetime.utcnow().isoformat(),
            "client_info": client_info,
            "visitor_name": visitor_name,
            "max_pages": max_pages,
        }

    thread = threading.Thread(target=run_search_job, args=(job_id, query, max_pages), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
def get_progress(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "İş bulunamadı."}), 404
        response = {
            "job_id": job_id,
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "message": job.get("message", ""),
            "stage": job.get("stage"),
            "current": job.get("current", 0),
            "total": job.get("total", 0),
            "error": job.get("error"),
        }
        if job.get("status") == "completed" and job.get("file_path"):
            response["download_url"] = f"/download/{job_id}"
        return jsonify(response)


@app.route("/download/<job_id>")
def download_file(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "completed" or not job.get("file_path"):
            return jsonify({"error": "Dosya bulunamadı veya işlem tamamlanmadı."}), 404
        file_path = job.get("file_path")
    if not isinstance(file_path, str) or not os.path.exists(file_path):
        return jsonify({"error": "Dosya artık mevcut değil."}), 404
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=26888, debug=False)
