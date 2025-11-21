# monitoring/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.monitor_websites, name='monitor_dashboard'),
    path('add/', views.add_website, name='add_website'),
    path('edit/<int:pk>/', views.edit_website, name='edit_website'),
    path('delete/<int:pk>/', views.delete_website, name='delete_website'),
    path('ssl/', views.ssl_dashboard, name='ssl_dashboard'), # Jalur URL SSL
    path('bandwidth/', views.bandwidth_dashboard, name='bandwidth_dashboard'),
    path('bandwidth/report/weekly/', views.generate_bandwidth_report, {'report_type': 'weekly'}, name='bandwidth_report_weekly'),
    path('bandwidth/report/monthly/', views.generate_bandwidth_report, {'report_type': 'monthly'}, name='bandwidth_report_monthly'),
]