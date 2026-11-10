import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


# =====================================================================
# 1. Таблица пользователей (library_customuser)
# =====================================================================

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('director', 'Директор'),
        ('librarian', 'Библиотекарь'),
        ('reader', 'Читатель'),
    )

    BASE_READER_PERMS = ['library.view_book']

    BASE_LIBRARIAN_PERMS = BASE_READER_PERMS + [
        'library.add_book',
        'library.change_book',
        'library.view_book',
        'library.view_physicalcopy',
        'library.change_physicalcopy',
    ]

    BASE_DIRECTOR_PERMS = BASE_LIBRARIAN_PERMS + [
        'library.add_customuser',
        'library.change_customuser',
        'library.view_customuser',
    ]

    ROLE_PERMISSIONS = {
        'director': BASE_DIRECTOR_PERMS,
        'librarian': BASE_LIBRARIAN_PERMS,
        'reader': BASE_READER_PERMS,
    }

    # Роль пользователя
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='reader', verbose_name="Роль")

    # Валидатор: разрешает только буквы (рус/лат), одиночные пробелы и дефисы
    name_validator = RegexValidator(
        regex=r'^[a-zA-Zа-яА-ЯёЁ]+([ \-\s][a-zA-Zа-яА-ЯёЁ]+)*$',
        message="Разрешены только буквы, одиночный пробел или дефис (например: Анна-Мария, фон Бисмарк)."
    )

    # Переопределяем Фамилию: ОБЯЗАТЕЛЬНО, проверяется валидатором
    last_name = models.CharField(
        max_length=150,
        blank=False,
        validators=[name_validator],
        verbose_name="Фамилия"
    )

    # Переопределяем Имя: ОБЯЗАТЕЛЬНО, проверяется валидатором
    first_name = models.CharField(
        max_length=150,
        blank=False,
        validators=[name_validator],
        verbose_name="Имя"
    )

    # Добавляем Отчество: НЕОБЯЗАТЕЛЬНО, но если заполнено проверяется валидатором
    middle_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        validators=[name_validator],
        verbose_name="Отчество"
    )

    # Валидатор: разрешает ровно 10 цифр (без пробелов и дефисов)
    phone_validator = RegexValidator(
        regex=r'^(\+7)?\d{10}$',
        message="Номер телефона должен состоять из 10 цифр в формате +7XXXXXXXXXX (или без +7)."
    )

    # Номер телефона: ОБЯЗАТЕЛЬНОЕ, УНИКАЛЬНОЕ, проверяется валидатором
    phone = models.CharField(
        max_length=12,
        blank=False,
        unique=True,
        validators=[phone_validator],
        verbose_name="Номер телефона",
        help_text="Введите 10 цифр мобильного номера в формате +7XXXXXXXXXX (или без +7)."
    )

    # Валидатор: разрешает буквы и цифры без пробелов, тире и спецсимволов
    document_validator = RegexValidator(
        regex=r'^[a-zA-Zа-яА-ЯёЁ0-9]+$',
        message="Номер документа должен содержать только буквы и цифры (без пробелов, тире и спецсимволов)."
    )

    # Номер документа (удостоверения): ОБЯЗАТЕЛЬНОЕ, УНИКАЛЬНОЕ, проверяется валидатором
    document_number = models.CharField(
        max_length=50,
        blank=False,
        unique=True,
        validators=[document_validator],
        verbose_name="Номер документа"
    )

    force_password_change = models.BooleanField(
        default=False,
        verbose_name="Требовать смену пароля"
    )

    def save(self, *args, **kwargs):
        # Логика автоматического распределения ролей
        if self.is_superuser:
            self.role = 'director'
            self.is_staff = True
        elif self.is_staff:
            self.role = 'librarian'
            self.is_staff = True
        else:
            self.role = 'reader'
            self.is_staff = False

        # Логика форматирования телефона
        if self.phone and len(self.phone) == 10 and self.phone.isdigit():
            self.phone = f"+7{self.phone}"

        # Логика автогенерации номера документа (удостоверения)
        if not self.pk and not self.document_number:
            unique_suffix = uuid.uuid4().hex[:6].upper()
            current_year = timezone.now().year
            self.document_number = f"L{current_year}{unique_suffix}"

        # Сохранение объекта в БД PostgreSQL
        super().save(*args, **kwargs)

    def has_perm(self, perm, obj=None):
        if self.is_active and self.is_superuser:
            return True
        allowed_perms = self.ROLE_PERMISSIONS.get(self.role, [])
        if perm in allowed_perms:
            return True
        return super().has_perm(perm, obj)

    def has_module_perms(self, app_label):
        if self.is_active and self.is_superuser:
            return True
        allowed_perms = self.ROLE_PERMISSIONS.get(self.role, [])
        return any(perm.startswith(f"{app_label}.") for perm in allowed_perms)

    def __str__(self):
        full_name = f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()
        return f"{full_name or self.username} ({self.get_role_display()})"


# =====================================================================
# 2. Таблица авторов (library_author)
# =====================================================================

class Author(models.Model):
    name_validator = RegexValidator(
        regex=r'^[a-zA-Zа-яА-ЯёЁ]+([ \-\s][a-zA-Zа-яА-ЯёЁ]+)*$',
        message="Разрешены только буквы, одиночный пробел или дефис."
    )

    last_name = models.CharField(max_length=150, blank=False, validators=[name_validator], verbose_name="Фамилия")
    first_name = models.CharField(max_length=150, blank=False, validators=[name_validator], verbose_name="Имя")
    # Отчество: НЕОБЯЗАТЕЛЬНО (blank=True, null=True)
    middle_name = models.CharField(max_length=150, blank=True, null=True, validators=[name_validator], verbose_name="Отчество")
    biography = models.TextField(blank=True, null=True, verbose_name="Биография")

    class Meta:
        verbose_name = "Автор"
        verbose_name_plural = "Авторы"

    def __str__(self):
        return f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()


# =====================================================================
# 3. Таблица книг (library_book)
# =====================================================================

class Book(models.Model):
    isbn_validator = RegexValidator(
        regex = r'^(978|979)-\d{1,5}-\d{1,7}-\d{1,6}-\d$',
        message="ISBN must be in the format XXX-XXXXX-XXXXX-XXXXX-X or XXX-XXXXX-XXXXX-XXXXX-XX"
    )

    title = models.CharField(
        max_length=255,
        verbose_name="Название книги",
        help_text="Введите название книги"
    )
    authors = models.ManyToManyField(
        Author,
        related_name='books',
        verbose_name="Авторы",
        help_text="Выберите автора или авторов книги"
    )
    genres = models.CharField(
        max_length=255,
        verbose_name="Жанр или список жанров",
        help_text="Введите жанр или список жанров через запятую"
    )
    isbn = models.CharField(
        max_length=17,
        unique=True,
        verbose_name="ISBN",
        validators=[isbn_validator],
        help_text=(
            "Международный стандартный книжный номер (ISBN-13). "
            "Должен состоять из 13 цифр и 4 дефисов. "
            "Формат: 978-X-XX-XXXXXX-X (или 979-X-XX-XXXXXX-X). "
            "[3 цифры] - [до 5 цифр] - [до 7 цифр] - [до 6 цифр] - [1 цифра]. "
            "Пример: 978-5-699-12014-7"
        )
    )
    reserved_by = models.ManyToManyField(
        CustomUser,
        verbose_name="Читатели, ожидающие книгу",
        blank=True,
        help_text="Список пользователей, которые зарезервировали книгу"
    )

    class Meta:
        verbose_name = "Книга"
        verbose_name_plural = "Книги"

    # Выполнение обратного запроса от родительской таблицы (Book) к дочерней (PhysicalCopy)
    @property
    def total_copies(self):
        return self.physical_copies.count()

    def __str__(self):
        authors_list = ", ".join([f"{a.last_name} {a.first_name}" for a in self.authors.all()])
        return f"{self.title} (Автор(ы): {authors_list or 'Не указан'})"


# =====================================================================
# 4. Таблица физических копий (library_physicalcopy)
# =====================================================================

class PhysicalCopy(models.Model):
    alphanumeric = RegexValidator(r'^[0-9a-zA-Z]*$', 'Инвентарный номер может содержать только буквы и цифры.')

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='physical_copies',
        verbose_name='Книга',
        help_text='Книга, к которой принадлежит данный экземпляр'
    )
    current_reader = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name='borrowed_books',
        verbose_name='Текущий читатель',
        help_text='Читатель, который держит книгу прямо сейчас',
        blank=True,
        null=True
    )
    inventory_number = models.CharField(
        max_length=100,
        unique=True,
        validators=[alphanumeric],
        verbose_name='Инвентарный номер',
        help_text='Уникальный инвентарный номер экземпляра книги'
    )
    STATUS_CHOICES = [
        ('available', 'Доступна'),
        ('loaned', 'Выдана'),
        ('reserved', 'Зарезервирована'),
        ('restoration', 'На реставрации'),
        ('archived', 'Списана'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        verbose_name='Статус экземпляра',
        help_text='Текущий статус экземпляра книги'
    )
    issue_date = models.DateField(
        verbose_name='Дата выдачи',
        help_text='Дата выдачи книги',
        blank=True,
        null=True
    )
    due_date = models.DateField(
        verbose_name='Дата возврата',
        help_text='Дата, когда книгу нужно вернуть',
        blank=True,
        null=True
    )

    class Meta:
        verbose_name = "Экземпляр книги"
        verbose_name_plural = "Экземпляры книг"

    def __str__(self):
        return f"{self.book.title} (Инв. №: {self.inventory_number}) — {self.get_status_display()}"


# =====================================================================
# 5. Таблица учета статистики (library_borrowlog)
# =====================================================================

class BorrowLog(models.Model):
    """
    Журнал истории выдачи книг читателям.
    """
    # Читатель
    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='borrow_logs',
        verbose_name="Читатель"
    )
    # Физический экземпляр
    physical_copy = models.ForeignKey(
        'PhysicalCopy',
        on_delete=models.PROTECT,
        related_name='borrow_logs',
        verbose_name="Экземпляр книги"
    )
    # Даты выдачи/возврата
    # Фиксируется один раз строго в момент создания записи
    issue_date = models.DateField(default=timezone.now, verbose_name="Дата выдачи")

    # Заполняется только тогда, когда читатель физически принес книгу назад
    return_date = models.DateField(null=True, blank=True, verbose_name="Дата фактического возврата")

    class Meta:
        verbose_name = "Запись журнала выдачи"
        verbose_name_plural = "Журнал выдачи книг"
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.reader.username} взял {self.physical_copy.book.title} ({self.issue_date})"

