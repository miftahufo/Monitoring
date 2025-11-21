from django.db import models

class Website(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    last_hash = models.CharField(max_length=256, blank=True, null=True)
    is_defaced = models.BooleanField(default=False)
    last_checked = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, null=True) # Kolom baru untuk menyimpan eror

    # Bidang baru untuk pemantauan SSL
    ssl_expiry_date = models.DateTimeField(null=True, blank=True)
    ssl_error_message = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name

class BandwidthTest(models.Model):
    download_speed_mbps = models.FloatField()
    upload_speed_mbps = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Test at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"