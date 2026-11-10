import uuid

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import Author, Book, CustomUser, PhysicalCopy


# =====================================================================
# 1. Управление пользователями (CustomUser)
# =====================================================================

class CustomUserCreationForm(UserCreationForm):
    """
    Кастомная форма для управления пользователями в админ-панели Django
    """
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "first_name", "last_name", "middle_name", "role", "phone")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Контроллер для управления отображением пользователей в админ-панели Django
    """
    model = CustomUser
    add_form = CustomUserCreationForm

    # Выбираем отображаемые поля и критерии фильтрации
    list_display = ['username', 'last_name', 'first_name', 'role', 'document_number', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_superuser', 'is_active']

    # Защищаем сгенерированный номер от ручного изменения
    readonly_fields = ['document_number']

    # Группируем поля на странице редактирования существующего пользователя
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Персональные данные', {'fields': ('first_name', 'last_name', 'middle_name', 'email')}),
        ('Статусы доступа', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Дополнительные данные библиотеки', {'fields': ('role', 'phone', 'document_number')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined')}),
    )

    # Настраиваем поля на странице создания нового пользователя
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Персональные данные', {
            'fields': ('first_name', 'last_name', 'middle_name'),
        }),
        ('Дополнительные данные библиотеки', {
            'fields': ('role', 'phone'),
        }),
    )


# =====================================================================
# 2. Управление книгами (Book)
# =====================================================================

class BookAdminForm(forms.ModelForm):
    """
        Кастомная форма для создания и редактирования книг в админ-панели Django,
        с виртуальным полем quantity для генерации физических копий
    """
    quantity = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label="Добавить физических экземпляров",
        help_text="Укажите, сколько новых копий этой книги нужно сгенерировать и поставить на учёт. Если копии добавлять не нужно, оставьте 0."
    )

    class Meta:
        model = Book
        fields = '__all__'


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    """
        Контроллер админ-панели Django для книг, с механизмом автоматического
        инвентарного учета новых физических экземпляров
    """
    form = BookAdminForm

    # Настраиваем список и определяем критерии для поиска
    list_display = ('title', 'get_authors_display', 'isbn', 'total_copies')
    search_fields = ('title', 'authors__last_name', 'authors__first_name', 'isbn')

    # Задаем состав и порядок отображения полей
    fields = ('title', 'authors', 'genres', 'isbn', 'quantity')

    def get_authors_display(self, obj):
        """
        Кастомный метод для отображения списка авторов в виде строки через запятую.
        """
        return ", ".join([f"{a.last_name} {a.first_name}" for a in obj.authors.all()])
    get_authors_display.short_description = "Автор(ы)"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('authors')

    def save_model(self, request, obj, form, change):
        obj._temporary_quantity = form.cleaned_data.get('quantity', 0) or 0
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        obj = form.instance
        # Извлекаем количество, которое нужно добавить
        quantity_to_add = getattr(obj, '_temporary_quantity', 0)

        if quantity_to_add > 0:
            # Генерация инвентарных номеров на основе UUID и поля quantity
            for _ in range(quantity_to_add):
                unique_inv = f"INV{uuid.uuid4().hex[:6].upper()}"
                PhysicalCopy.objects.create(
                    book=obj,
                    status='available',
                    inventory_number=unique_inv
                )

            # Очистка поля добавление количество копий
            form.cleaned_data['quantity'] = 0

    # Права доступа для библиотекаря (добавление, редактирование, удаление)
    def has_add_permission(self, request):
        return request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian')

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian')


# =====================================================================
# 3. Управление авторами (Author)
# =====================================================================

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    """
    Контроллер админ-панели Django для управления авторами.
    Включает автоматическое усечение длинных биографий.
    """
    list_display = ('last_name', 'first_name', 'middle_name', 'biography_short')
    search_fields = ('last_name', 'first_name')
    ordering = ('last_name', 'first_name')

    # Обрезаем текст биографии в таблице, если он длиннее 50 символов
    def biography_short(self, obj):
        if obj.biography and len(obj.biography) > 50:
            return obj.biography[:50] + "..."
        return obj.biography or "—"
    biography_short.short_description = "Биография"

    # Права доступа для библиотекаря (добавление, редактирование, удаление)
    def has_add_permission(self, request):
        if request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian'):
            return True
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian'):
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_authenticated and (request.user.is_superuser or request.user.role == 'librarian'):
            return True
        return False




