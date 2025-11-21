from django.shortcuts import render, redirect, get_object_or_404
from .models import Website, BandwidthTest
from django.http import JsonResponse
import requests, hashlib, re, os, ssl, socket
from datetime import datetime, timedelta
from bs4 import BeautifulSoup, Comment
from django.db.models import Avg, Max, Min
from django.utils import timezone
from django.utils.timezone import localtime
import json
from sslyze import (
    Scanner,
    ServerScanRequest,
    ServerNetworkLocation,
    ScanCommand,
    ServerScanStatusEnum,
    ScanCommandAttemptStatusEnum,
)
import speedtest
import telegram
from django.conf import settings
import asyncio # Impor asyncio
from django.template.loader import get_template
from django.http import HttpResponse
from xhtml2pdf import pisa

# --- Fungsi-fungsi Pembantu di Bagian Atas ---

def get_website_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        return f"Error: {e}"

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for script in soup(["script", "style"]):
        script.extract()
    for comment in soup.find_all(string=lambda text:isinstance(text, Comment)):
        comment.extract()
    text = soup.get_text()
    cleaned_text = " ".join(text.split())
    return cleaned_text

def get_ssl_expiry_date(hostname):
    try:
        scanner = Scanner()
        server_loc = ServerNetworkLocation(hostname=hostname, port=443)
        scan_request = ServerScanRequest(
            server_location=server_loc,
            scan_commands={ScanCommand.CERTIFICATE_INFO}
        )
        scanner.queue_scans([scan_request])
        for server_scan_result in scanner.get_results():
            if server_scan_result.scan_status == ServerScanStatusEnum.ERROR_NO_CONNECTIVITY:
                return None, f"Error: no connectivity: {server_scan_result.connectivity_error_trace}"
            if not server_scan_result.scan_result:
                return None, "Error: empty scan_result"
            cert_attempt = server_scan_result.scan_result.certificate_info
            if cert_attempt.status == ScanCommandAttemptStatusEnum.COMPLETED:
                certinfo = cert_attempt.result
                if (
                    certinfo.certificate_deployments
                    and certinfo.certificate_deployments[0].received_certificate_chain
                ):
                    leaf_cert = certinfo.certificate_deployments[0].received_certificate_chain[0]
                    expiry = leaf_cert.not_valid_after
                    return expiry, None
                return None, "Error: certificate chain not found"
            else:
                return None, f"Error: certificate_info failed: {cert_attempt.error_reason}"
        return None, "Error: no results from scanner.get_results()"
    except Exception as e:
        return None, f"Error: {e}"

# Fungsi async untuk mengirim notifikasi
async def _send_telegram_async(message: str):
    """Fungsi async asli untuk kirim pesan ke Telegram"""
    bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=settings.TELEGRAM_CHAT_ID, text=message)
        print("✅ Notifikasi Telegram berhasil dikirim.")
    except Exception as e:
        print(f"❌ Gagal mengirim notifikasi Telegram: {e}")


def send_telegram_notification(message: str):
    """
    Wrapper sinkron agar aman dipakai di Gunicorn atau Cronjob.
    Tidak memakai asyncio.run() supaya event loop tidak crash.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Jika sudah ada loop aktif (misalnya di Gunicorn/ASGI)
            asyncio.ensure_future(_send_telegram_async(message))
        else:
            loop.run_until_complete(_send_telegram_async(message))
    except RuntimeError:
        # Kalau belum ada event loop → buat loop baru
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(_send_telegram_async(message))
        new_loop.close()

def check_and_update_websites():
    websites = Website.objects.all()
    for website in websites:
        old_is_defaced = website.is_defaced
        old_error_message = website.error_message
        old_ssl_error_message = website.ssl_error_message

        # Cek defacement
        try:
            content = get_website_content(website.url)
            
            if content.startswith("Error:"):
                if not old_error_message:
                    message = f"!!! ERROR WEB !!!\nSitus: {website.name} ({website.url})\nDetail: {content}"
                    send_telegram_notification(message)
                website.is_defaced = False
                website.error_message = content
            else:
                if old_error_message:
                    message = f"✅ SITUS KEMBALI NORMAL ✅\nSitus: {website.name} ({website.url})\nSitus kembali online."
                    send_telegram_notification(message)
                
                website.error_message = None
                cleaned_content = clean_html(content)
                current_hash = hashlib.sha256(cleaned_content.encode('utf-8')).hexdigest()

                if website.last_hash and website.last_hash != current_hash:
                    if not old_is_defaced:
                        message = f"!!! PERINGATAN DEFACEMENT !!!\nSitus: {website.name} ({website.url})\nKonten web telah berubah."
                        send_telegram_notification(message)
                    website.is_defaced = True
                else:
                    website.is_defaced = False

                website.last_hash = current_hash

        except Exception as e:
            if not old_error_message:
                message = f"!!! ERROR WEB !!!\nSitus: {website.name} ({website.url})\nDetail: {e}"
                send_telegram_notification(message)
            website.error_message = f"Error: {e}"
            website.is_defaced = False
        
        # Cek SSL
        try:
            hostname_match = re.search(r'//(.*?)(?:/|$)', website.url)
            hostname = hostname_match.group(1) if hostname_match else website.url
            expiry_date, ssl_error = get_ssl_expiry_date(hostname)
            
            if ssl_error:
                if not old_ssl_error_message:
                    message = f"!!! ERROR SSL !!!\nSitus: {website.name} ({website.url})\nDetail: {ssl_error}"
                    send_telegram_notification(message)
                website.ssl_expiry_date = None
                website.ssl_error_message = ssl_error
            else:
                if old_ssl_error_message:
                    message = f"✅ SSL KEMBALI NORMAL ✅\nSitus: {website.name} ({website.url})\nSertifikat SSL kembali valid."
                    send_telegram_notification(message)
                website.ssl_expiry_date = expiry_date
                website.ssl_error_message = None
        except Exception as e:
            if not old_ssl_error_message:
                message = f"!!! ERROR SSL !!!\nSitus: {website.name} ({website.url})\nDetail: {e}"
                send_telegram_notification(message)
            website.ssl_error_message = f"Error: {e}"
        
        website.last_checked = timezone.now()
        website.save()



# --- Fungsi Tampilan Web di Bawahnya ---

def monitor_websites(request):
    websites = Website.objects.all()
    
    query = request.GET.get('q')
    if query:
        websites = websites.filter(name__icontains=query)

    return render(request, 'monitoring/dashboard.html', {'websites': websites})

def add_website(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        url = request.POST.get('url')
        Website.objects.create(name=name, url=url)
        return redirect('monitor_dashboard')
    return render(request, 'monitoring/add_website.html')

def edit_website(request, pk):
    website = get_object_or_404(Website, pk=pk)
    if request.method == 'POST':
        website.name = request.POST.get('name')
        website.url = request.POST.get('url')
        website.save()
        return redirect('monitor_dashboard')
    return render(request, 'monitoring/edit_website.html', {'website': website})

def delete_website(request, pk):
    website = get_object_or_404(Website, pk=pk)
    if request.method == 'POST':
        website.delete()
        return redirect('monitor_dashboard')
    return render(request, 'monitoring/delete_website.html', {'website': website})

def ssl_dashboard(request):
    websites = Website.objects.all().order_by('name')
    return render(request, 'monitoring/ssl_dashboard.html', {'websites': websites})

def bandwidth_dashboard(request):
    results = BandwidthTest.objects.all().order_by("-timestamp")[:10]
    results = list(results)[::-1]  # urut lama → baru

    # Perbaiki logika ini untuk memastikan variabel selalu ada
    labels, download, upload = [], [], []
    summary_stats = None

    # Ambil data mentah untuk tabel
    labels = [localtime(r.timestamp).strftime("%Y-%m-%d %H:%M:%S") for r in results]
    download = [r.download_speed_mbps for r in results]
    upload = [r.upload_speed_mbps for r in results]

    # Buat satu list dict untuk grafik (lebih aman dipakai di Chart.js)
    chart_data = [
        {
            "timestamp": localtime(r.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "download": r.download_speed_mbps,
            "upload": r.upload_speed_mbps,
        }
        for r in results
    ]

    now = timezone.now()
    summary_stats = None
    if results:
        summary_stats = BandwidthTest.objects.aggregate(
            avg_download=Avg('download_speed_mbps'),
            max_download=Max('download_speed_mbps'),
            min_download=Min('download_speed_mbps'),
            avg_upload=Avg('upload_speed_mbps'),
            max_upload=Max('upload_speed_mbps'),
            min_upload=Min('upload_speed_mbps')
        )

    # Harian (24 jam terakhir)
    daily = BandwidthTest.objects.filter(timestamp__date=now.date())
    daily_stats = daily.aggregate(
        avg_download=Avg("download_speed_mbps"),
        avg_upload=Avg("upload_speed_mbps"),
    )

    # Mingguan (7 hari terakhir)
    week_ago = now - timedelta(days=7)
    weekly = BandwidthTest.objects.filter(timestamp__gte=week_ago)
    weekly_stats = weekly.aggregate(
        avg_download=Avg("download_speed_mbps"),
        avg_upload=Avg("upload_speed_mbps"),
    )

    # Bulanan (30 hari terakhir)
    month_ago = now - timedelta(days=30)
    monthly = BandwidthTest.objects.filter(timestamp__gte=month_ago)
    monthly_stats = monthly.aggregate(
        avg_download=Avg("download_speed_mbps"),
        avg_upload=Avg("upload_speed_mbps"),
    )

    context = {
        "results": results,
        "labels": labels,
        "download": download,
        "upload": upload,
        "chart_data": chart_data,   # ✅ tambahan untuk grafik
        "summary_stats": summary_stats,
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats,
        "monthly_stats": monthly_stats,
    }
    return render(request, "monitoring/bandwidth_dashboard.html", context)

def run_speedtest():
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000  # convert ke Mbps
        upload_speed = st.upload() / 1_000_000      # convert ke Mbps

        BandwidthTest.objects.create(
            download_speed_mbps=download_speed,
            upload_speed_mbps=upload_speed
        )
        print(f"[OK] Speedtest berhasil. Download={download_speed:.2f} Mbps, Upload={upload_speed:.2f} Mbps")
    except Exception as e:
        print(f"[ERROR] Gagal speedtest: {e}")

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    response = HttpResponse(content_type='application/pdf')
    pisa_status = pisa.CreatePDF(
            html, dest=response
        )
    if pisa_status.err:
            return HttpResponse('Kami mengalami beberapa kesalahan <pre>' + html + '</pre>')
    return response
    

def generate_bandwidth_report(request, report_type):
    now = timezone.now()
    start_date = None
    title = ""

    if report_type == 'weekly':
        start_date = now - timedelta(weeks=1)
        title = "Laporan Bandwidth Mingguan"
    elif report_type == 'monthly':
        start_date = now - timedelta(days=30)
        title = "Laporan Bandwidth Bulanan"
    else:
        return HttpResponse("Jenis laporan tidak valid.", status=400)

    results = BandwidthTest.objects.filter(timestamp__gte=start_date).order_by('timestamp')

    context = {
        'title': title,
        'results': results,
        'now': now,
       }
    
    if results.exists():
        first_data_point = results.first()
        last_data_point = results.last()
        context['start_date'] = first_data_point.timestamp
        context['end_date'] = last_data_point.timestamp
    else:
        context['start_date'] = start_date
        context['end_date'] = now

    response = render_to_pdf("monitoring/bandwidth_report_pdf.html", context)
    
    #Tambahkan header Content-Disposition untuk memaksa unduhan
    filename = f"laporan_bandwidth_{report_type}_{now.strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


