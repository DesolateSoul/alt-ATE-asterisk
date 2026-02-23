from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('logs/', views.VerificationLogListView.as_view(), name='logs_list'),
    path('export/', views.ExportLogsView.as_view(), name='export_logs'),
    
    # Клиенты
    path('clients/', views.ClientListView.as_view(), name='clients_list'),
    path('clients/create/', views.ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/update/', views.ClientUpdateView.as_view(), name='client_update'),
    path('clients/<int:pk>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),
    path('clients/import/', views.ClientImportView.as_view(), name='client_import'),
]
