# monitoring/tasks.py

from background_task import background
from .views import check_and_update_websites
from django.urls import reverse
from django.test import RequestFactory
from .models import Website
from datetime import datetime
import requests
import hashlib
from .models import BandwidthTest
import speedtest

@background(schedule=30 * 1)  # Jadwal: setiap 15 menit
def run_monitor_websites():
    check_and_update_websites()


@background(schedule=60 * 60)  # Jadwalkan untuk berjalan setiap jam
def run_speedtest():
    try:
        st = speedtest.Speedtest()
        download_speed = st.download() / 1_000_000  # Konversi ke Mbps
        upload_speed = st.upload() / 1_000_000      # Konversi ke Mbps

        BandwidthTest.objects.create(
            download_speed_mbps=download_speed,
            upload_speed_mbps=upload_speed,
            timestamp=datetime.now()
        )
        print("Tes kecepatan berhasil dijalankan dan data disimpan.")
    except Exception as e:
        print(f"Error running speedtest: {e}")