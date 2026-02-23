from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
import io
from .forms import ClientForm, ClientImportForm
from django.shortcuts import render
from django.views.generic import ListView, DetailView, View
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta, datetime
from .models import Client, VerificationLog, TelegramGroupBinding
import csv
import json

class VerificationLogListView(ListView):
    """
    Список логов верификации с фильтрацией
    """
    model = VerificationLog
    template_name = 'verification_system/logs_list.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = VerificationLog.objects.select_related('matched_client').all()
        
        # Фильтр по успешности
        success = self.request.GET.get('success')
        if success == 'true':
            queryset = queryset.filter(success=True)
        elif success == 'false':
            queryset = queryset.filter(success=False)
        
        # Фильтр по номеру
        caller = self.request.GET.get('caller')
        if caller:
            queryset = queryset.filter(caller_number__icontains=caller)
        
        # Фильтр по дате
        days = self.request.GET.get('days')
        if days:
            try:
                days = int(days)
                date_from = timezone.now() - timedelta(days=days)
                queryset = queryset.filter(created_at__gte=date_from)
            except ValueError:
                pass
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Статистика для отображения
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0)
        
        context['stats'] = {
            'today_total': VerificationLog.objects.filter(created_at__gte=today).count(),
            'today_success': VerificationLog.objects.filter(
                created_at__gte=today, success=True
            ).count(),
            'total_clients': Client.objects.filter(active=True).count(),
            'total_bindings': TelegramGroupBinding.objects.filter(active=True).count(),
        }
        
        # Сохраняем параметры фильтрации для формы
        context['current_filters'] = {
            'success': self.request.GET.get('success', ''),
            'caller': self.request.GET.get('caller', ''),
            'days': self.request.GET.get('days', ''),
        }
        
        return context


class ClientListView(ListView):
    """
    Список клиентов
    """
    model = Client
    template_name = 'verification_system/clients_list.html'
    context_object_name = 'clients'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Client.objects.all()
        
        # Поиск
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(company_name__icontains=search) | 
                Q(inn__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class ClientDetailView(DetailView):
    """
    Детальная информация о клиенте
    """
    model = Client
    template_name = 'verification_system/client_detail.html'
    context_object_name = 'client'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_object()
        
        # Получаем логи этого клиента
        context['logs'] = VerificationLog.objects.filter(
            matched_client=client
        ).order_by('-created_at')[:20]
        
        # Получаем привязки Telegram групп
        context['bindings'] = TelegramGroupBinding.objects.filter(
            client=client, active=True
        )
        
        # Статистика по клиенту
        total_calls = VerificationLog.objects.filter(matched_client=client).count()
        success_calls = VerificationLog.objects.filter(matched_client=client, success=True).count()
        
        context['stats'] = {
            'total_calls': total_calls,
            'success_calls': success_calls,
            'success_rate': (success_calls / total_calls * 100) if total_calls > 0 else 0,
        }
        
        return context


class DashboardView(ListView):
    template_name = 'verification_system/dashboard.html'
    
    def get_queryset(self):
        return []
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0)
        
        # Основная статистика
        total_calls = VerificationLog.objects.count()
        success_calls = VerificationLog.objects.filter(success=True).count()
        
        context['total_clients'] = Client.objects.count()
        context['calls_today'] = VerificationLog.objects.filter(created_at__gte=today).count()
        context['success_today'] = VerificationLog.objects.filter(
            created_at__gte=today, success=True
        ).count()
        context['success_rate'] = round((success_calls / total_calls * 100), 1) if total_calls > 0 else 0
        
        # Данные для графика по дням
        last_7_days = []
        calls_count = []
        
        for i in range(6, -1, -1):
            day = now - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0)
            day_end = day.replace(hour=23, minute=59, second=59)
            
            last_7_days.append(day.strftime('%d.%m'))
            calls_count.append(
                VerificationLog.objects.filter(
                    created_at__range=[day_start, day_end]
                ).count()
            )
        
        context['chart_days'] = json.dumps(last_7_days)
        context['chart_calls'] = json.dumps(calls_count)
        
        # Топ клиентов
        top_clients_data = []
        clients = Client.objects.filter(
            verificationlog__isnull=False
        ).annotate(
            total_calls=Count('verificationlog'),
            success_calls=Count('verificationlog', filter=Q(verificationlog__success=True))
        ).order_by('-total_calls')[:5]
        
        for client in clients:
            success_rate = round((client.success_calls / client.total_calls * 100), 1) if client.total_calls > 0 else 0
            top_clients_data.append({
                'id': client.id,
                'company_name': client.company_name,
                'total_calls': client.total_calls,
                'success_rate': success_rate
            })
        
        context['top_clients'] = top_clients_data
        
        # Последние звонки
        context['recent_calls'] = VerificationLog.objects.select_related(
            'matched_client'
        ).order_by('-created_at')[:10]
        
        return context


class ExportLogsView(View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="verification_logs.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Время', 'Номер', 'ИНН', 'Клиент', 'Кодовое слово', 'Статус', 'Проблема'])
        
        logs = VerificationLog.objects.select_related('matched_client').all()
        
        success = request.GET.get('success')
        if success == 'true':
            logs = logs.filter(success=True)
        elif success == 'false':
            logs = logs.filter(success=False)
        
        days = request.GET.get('days')
        if days:
            try:
                days = int(days)
                date_from = timezone.now() - timedelta(days=days)
                logs = logs.filter(created_at__gte=date_from)
            except ValueError:
                pass
        
        for log in logs:
            writer.writerow([
                log.id,
                log.created_at.strftime('%d.%m.%Y %H:%M:%S'),
                log.caller_number or '',
                log.spoken_inn or '',
                log.matched_client.company_name if log.matched_client else '',
                log.spoken_codeword or '',
                'Успешно' if log.success else 'Ошибка',
                log.problem_text or ''
            ])
        
        return response


class ClientCreateView(SuccessMessageMixin, CreateView):
    """
    Создание нового клиента
    """
    model = Client
    form_class = ClientForm
    template_name = 'verification_system/client_form.html'
    success_url = reverse_lazy('clients_list')
    success_message = "Клиент '%(company_name)s' успешно создан"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Добавление клиента'
        context['button_text'] = 'Создать'
        return context


class ClientUpdateView(SuccessMessageMixin, UpdateView):
    """
    Редактирование клиента
    """
    model = Client
    form_class = ClientForm
    template_name = 'verification_system/client_form.html'
    success_url = reverse_lazy('clients_list')
    success_message = "Клиент '%(company_name)s' успешно обновлен"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Редактирование клиента'
        context['button_text'] = 'Сохранить'
        return context


class ClientDeleteView(DeleteView):
    """
    Удаление клиента
    """
    model = Client
    template_name = 'verification_system/client_confirm_delete.html'
    success_url = reverse_lazy('clients_list')
    success_message = "Клиент успешно удален"
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)


class ClientImportView(View):
    """
    Импорт клиентов из CSV
    """
    template_name = 'verification_system/client_import.html'
    
    def get(self, request):
        form = ClientImportForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = ClientImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            # Проверка расширения файла
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'Файл должен быть в формате CSV')
                return redirect('client_import')
            
            # Чтение CSV
            try:
                decoded_file = csv_file.read().decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string, delimiter=',')
                
                # Пропускаем заголовок
                header = next(reader, None)
                
                created_count = 0
                updated_count = 0
                error_count = 0
                
                for row in reader:
                    if len(row) < 3:
                        error_count += 1
                        continue
                    
                    try:
                        inn = int(row[0].strip())
                        company_name = row[1].strip()
                        code_word = row[2].strip()
                        phone = row[3].strip() if len(row) > 3 else None
                        
                        # Проверяем существование клиента
                        client, created = Client.objects.update_or_create(
                            inn=inn,
                            defaults={
                                'company_name': company_name,
                                'code_word': code_word,
                                'phone_number': phone,
                                'active': True
                            }
                        )
                        
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                            
                    except (ValueError, IndexError) as e:
                        error_count += 1
                        continue
                
                messages.success(
                    request, 
                    f'Импорт завершен. Создано: {created_count}, Обновлено: {updated_count}, Ошибок: {error_count}'
                )
                
            except Exception as e:
                messages.error(request, f'Ошибка при обработке файла: {str(e)}')
            
            return redirect('clients_list')
        
        return render(request, self.template_name, {'form': form})
