from django import forms
from .models import Client

class ClientForm(forms.ModelForm):
    """
    Форма для создания и редактирования клиента
    """
    class Meta:
        model = Client
        fields = ['inn', 'company_name', 'code_word', 'phone_number', 'telegram_chat_id', 'active']
        widgets = {
            'inn': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Введите ИНН'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название компании'}),
            'code_word': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Кодовое слово'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (XXX) XXX-XX-XX'}),
            'telegram_chat_id': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'ID чата Telegram'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'inn': 'ИНН',
            'company_name': 'Название компании',
            'code_word': 'Кодовое слово',
            'phone_number': 'Номер телефона',
            'telegram_chat_id': 'Telegram Chat ID',
            'active': 'Активен',
        }
    
    def clean_inn(self):
        """Валидация ИНН"""
        inn = self.cleaned_data.get('inn')
        # Проверка длины ИНН (10 для юрлиц, 12 для ИП)
        if len(str(inn)) not in [10, 12]:
            raise forms.ValidationError('ИНН должен содержать 10 или 12 цифр')
        return inn
    
    def clean_phone_number(self):
        """Валидация телефона"""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            # Убираем все кроме цифр
            cleaned = ''.join(filter(str.isdigit, phone))
            if len(cleaned) not in [10, 11]:  # 10 или 11 цифр
                raise forms.ValidationError('Некорректный номер телефона')
        return phone


class ClientImportForm(forms.Form):
    """
    Форма для импорта клиентов из CSV
    """
    csv_file = forms.FileField(
        label='CSV файл',
        help_text='Файл с колонками: ИНН, Название компании, Кодовое слово, Телефон (опционально)',
        widget=forms.FileInput(attrs={'class': 'form-control-file'})
    )
