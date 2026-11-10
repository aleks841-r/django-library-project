from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

# Получаем активную модель пользователя (CustomUser)
User = get_user_model()


# =====================================================================
# 1. Форма регистрации читателя
# =====================================================================

class ReaderRegistrationForm(forms.ModelForm):
    """
    Форма для самостоятельной регистрации новых читателей на сайте библиотеки.
    Автоматически хэширует пароли и присваивает базовую роль 'reader'.
    """
    password = forms.CharField(
        label=_('Пароль'),
        widget=forms.PasswordInput,
        required=True
    )

    # Определяем состав, порядок и локализацию полей
    class Meta:
        model = User
        fields = ['username', 'password', 'last_name', 'first_name', 'middle_name', 'phone']
        labels = {
            'username': _('Имя пользователя'),
            'last_name': _('Фамилия'),
            'first_name': _('Имя'),
            'middle_name': _('Отчество'),
            'phone': _('Номер телефона'),
        }
        widgets = {
            'phone': forms.TextInput(attrs={'placeholder': '9991234567'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Конструктор формы. Используется для динамической настройки полей
        после их инициализации стандартными механизмами Django.
        """
        super().__init__(*args, **kwargs)
        # Переопределяем обязательные поля (Имя, Фамилия, Телефон)
        required_fields = ['last_name', 'first_name', 'phone']
        for field in required_fields:
            self.fields[field].required = True

    def save(self, commit=True):
        """
        Переопределение метода сохранения для обеспечения безопасности
        и автоматического заполнения служебных полей профиля.
        """
        user = super().save(commit=False)
        # Хешируем сырой пароль из формы
        user.set_password(self.cleaned_data['password'])
        # Назначаем роль reader любому зарегистрированному пользователю
        user.role = 'reader'
        if commit:
            user.save()
        return user


# =====================================================================
# 2. Формы поиска и бизнес-логики
# =====================================================================

class AuthorSearchForm(forms.Form):
    """
    Форма для фильтрации и поиска авторов на соответствующей странице каталога
    """
    search = forms.CharField(
        required=False,
        label="Поиск автора",
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите имя или фамилию автора',
            'class': 'form-control'
        })
    )


class BookSearchForm(forms.Form):
    """
    Форма для фильтрации и поиска книг в каталоге.
    """
    query = forms.CharField(
        label=_('Поиск книги'),
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите название книги, имя или фамилию автора',
            'class': 'form-control'
        })
    )


class BookReserveForm(forms.Form):
    """
    Форма для отправки POST-запроса на бронирование конкретной книги
    """
    book_id = forms.IntegerField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['book_id'].label = _('ID книги')

