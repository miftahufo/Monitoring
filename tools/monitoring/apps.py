from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'monitoring'

    def ready(self):
        # Impor dan jalankan tugas saat aplikasi siap
        from .tasks import run_monitor_websites
        run_monitor_websites(repeat=60 * 15) # Jadwalkan untuk berjalan setiap 15 menit

class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'monitoring'

    def ready(self):
        from .tasks import run_monitor_websites, run_speedtest
        run_monitor_websites(repeat=60 * 15)
        run_speedtest(repeat=60 * 60) # Tambahkan baris ini