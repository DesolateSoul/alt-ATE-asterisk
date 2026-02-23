from django.db import models

class Client(models.Model):
    """
    Модель для таблицы clients - клиенты с ИНН и кодовым словом
    """
    id = models.BigAutoField(primary_key=True)
    inn = models.BigIntegerField(unique=True, verbose_name="ИНН")
    company_name = models.CharField(max_length=255, verbose_name="Название компании")
    code_word = models.CharField(max_length=100, verbose_name="Кодовое слово")
    phone_number = models.CharField(max_length=30, null=True, blank=True, verbose_name="Телефон")
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, verbose_name="Telegram Chat ID")
    active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        db_table = 'clients'  # имя таблицы в вашей БД
        managed = False  # Django не будет создавать/изменять таблицу
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} (ИНН: {self.inn})"


class TelegramGroupBinding(models.Model):
    """
    Модель для таблицы telegram_group_bindings - привязка Telegram групп к клиентам
    """
    id = models.BigAutoField(primary_key=True)
    chat_id = models.BigIntegerField(verbose_name="Chat ID группы")
    chat_title = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название группы")
    client = models.ForeignKey(Client, on_delete=models.DO_NOTHING, db_column='client_id', verbose_name="Клиент")
    client_inn = models.BigIntegerField(verbose_name="ИНН клиента")
    company_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Название компании")
    bound_by = models.BigIntegerField(null=True, blank=True, verbose_name="ID привязавшего")
    bound_at = models.DateTimeField(auto_now_add=True, verbose_name="Время привязки")
    active = models.BooleanField(default=True, verbose_name="Активна")

    class Meta:
        db_table = 'telegram_group_bindings'
        managed = False
        verbose_name = "Привязка Telegram группы"
        verbose_name_plural = "Привязки Telegram групп"
        unique_together = [('chat_id', 'client')]
        indexes = [
            models.Index(fields=['chat_id'], name='idx_bindings_chat'),
            models.Index(fields=['client'], name='idx_bindings_client'),
            models.Index(fields=['client_inn'], name='idx_bindings_inn'),
            models.Index(fields=['active'], name='idx_bindings_active'),
        ]

    def __str__(self):
        return f"{self.chat_title or self.chat_id} -> {self.company_name}"


class VerificationLog(models.Model):
    """
    Модель для таблицы verification_logs - логи верификации по звонкам
    """
    DISPOSITION_CHOICES = [
        ('SUCCESS', 'Успешно'),
        ('FAIL', 'Ошибка'),
        ('PENDING', 'В обработке'),
    ]

    id = models.BigAutoField(primary_key=True)
    call_uniqueid = models.CharField(max_length=150, verbose_name="Уникальный ID звонка")
    caller_number = models.CharField(max_length=40, null=True, blank=True, verbose_name="Номер звонящего")
    spoken_inn = models.BigIntegerField(null=True, blank=True, verbose_name="Названный ИНН")
    matched_client = models.ForeignKey(
        Client, 
        on_delete=models.SET_NULL, 
        db_column='matched_client_id', 
        null=True, 
        blank=True,
        verbose_name="Найденный клиент"
    )
    spoken_codeword = models.CharField(max_length=100, null=True, blank=True, verbose_name="Названное кодовое слово")
    success = models.BooleanField(default=False, verbose_name="Успешно")
    problem_text = models.TextField(null=True, blank=True, verbose_name="Текст проблемы")
    problem_recognized_at = models.DateTimeField(null=True, blank=True, verbose_name="Время распознавания проблемы")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        db_table = 'verification_logs'
        managed = False
        verbose_name = "Лог верификации"
        verbose_name_plural = "Логи верификации"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['caller_number'], name='idx_verif_caller'),
            models.Index(fields=['matched_client'], name='idx_verif_client'),
            models.Index(fields=['success'], name='idx_verif_success'),
            models.Index(fields=['-created_at'], name='idx_verif_time'),
        ]

    def __str__(self):
        status = "✅" if self.success else "❌"
        return f"{self.created_at} - {self.caller_number} {status}"
