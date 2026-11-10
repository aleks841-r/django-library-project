from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from rest_framework import filters, generics, status, viewsets
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .forms import AuthorSearchForm, BookReserveForm, BookSearchForm, ReaderRegistrationForm
from .models import Author, Book, PhysicalCopy, BorrowLog
from .serializers import AuthorSerializer, BookSerializer, PhysicalCopySerializer, BookBorrowInputSerializer, ReserveBookInputSerializer


# =====================================================================
# 1. Незарегистрированный пользователь
# =====================================================================

def index_view(request):
    """
    Отображение главной (домашней) страницы библиотеки.
    Отсюда читатели и персонал переходят в нужные разделы.
    """
    return render(request, 'library/index.html')


def author_view(request):
    """
    Отображение списка авторов с динамическим поиском и сортировкой по Фамилии/Имени.
    """
    search_query = request.GET.get('search', '').strip()
    current_sort = request.GET.get('sort', '').strip()

    form = AuthorSearchForm(request.GET or None)

    authors = Author.objects.all().prefetch_related('books')

    if search_query:
        authors = authors.filter(
            Q(last_name__icontains=search_query) | Q(first_name__icontains=search_query)
        )

    if current_sort in ['last_name', 'first_name']:
        authors = authors.order_by(current_sort)

    paginator = Paginator(authors, 6)

    page_number = request.GET.get('page')

    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'authors': page_obj,
        'search_query': search_query,
        'current_sort': current_sort,
    }
    return render(request, 'library/author.html', context)


def book_view(request):
    """
    Отображение списка книг с возможностью поиска и сортировки.
    """
    form = BookSearchForm(request.GET or None)
    search_query = request.GET.get('query', '').strip()
    current_sort = request.GET.get('sort', '').strip()

    books = Book.objects.annotate(
        computed_available_count=Count(
            'physical_copies',
            filter=Q(physical_copies__status='available')
        )
    ).prefetch_related('authors')

    # Логика поиска
    if form.is_valid() and form.cleaned_data.get('query'):
        query = form.cleaned_data['query']
        books = books.filter(
            Q(title__icontains=query) |
            Q(authors__last_name__icontains=query) |
            Q(authors__first_name__icontains=query)
        ).distinct()

    # Логика сортировки
    if current_sort == 'title':
        books = books.order_by('title')
    elif current_sort == 'authors':
        books = books.order_by('authors__last_name', 'authors__first_name').distinct()

    # Исключаем дубли из-за связи Many-to-Many с таблицей авторов
    books = books.distinct()

    # Собираем весь список книг
    raw_books_with_forms = []
    for book in books:
        available_count = book.computed_available_count
        has_available_copies = available_count > 0

        reserve_form = BookReserveForm(initial={'book_id': book.id})

        raw_books_with_forms.append({
            'instance': book,
            'available_count': available_count,
            'has_available_copies': has_available_copies,
            'reserve_form': reserve_form
        })

    # Разбиваем готовый список на страницы (по 8 штук)
    paginator = Paginator(raw_books_with_forms, 8)
    page_number = request.GET.get('page')
    books_with_forms = paginator.get_page(page_number)

    context = {
        'form': form,
        'books_with_forms': books_with_forms,
        'current_sort': current_sort,
        'search_query': search_query,
    }
    return render(request, 'library/book.html', context)


def register_reader_view(request):
    """
    Регистрация нового читателя с последующим автоматическим входом.
    """
    if request.method == 'POST':
        form = ReaderRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Вы успешно зарегистрировались как читатель, {user.first_name}!")
            return redirect('book')
    else:
        form = ReaderRegistrationForm()

    return render(request, 'library/register.html', {'form': form})


# =====================================================================
# 2. Зарегистрированный пользователь (reader)
# =====================================================================

@login_required
def borrow_book_view(request):
    """
    Бизнес-логика выдачи книги читателю на руки с фиксацией в журнале.
    """
    if request.method == 'POST':
        book_id = request.POST.get('book_id')
        book = get_object_or_404(Book, id=book_id)

        # Проверка, есть ли у читателя такая книга
        already_has_copy = book.physical_copies.filter(
            current_reader=request.user, status="loaned"
        ).exists()

        if already_has_copy:
            messages.error(
                request,
                f"Вы не можете взять книгу '{book.title}', так как один экземпляр уже находится у вас на руках.",
            )
            return redirect("book")

        # Поиск доступного экземпляра для выдачи
        available_copy = book.physical_copies.filter(status="available").first()

        if available_copy:
            # Обновляем состояние самого физического экземпляра
            available_copy.status = 'loaned'
            available_copy.current_reader = request.user
            available_copy.issue_date = timezone.now().date()
            available_copy.due_date = timezone.now().date() + timezone.timedelta(days=14)
            available_copy.save()

            # Создаем новую открытую запись в журнале выдачи
            BorrowLog.objects.create(
                reader=request.user,
                physical_copy=available_copy,
                issue_date=timezone.now().date()
            )

            messages.success(
                request,
                f"Книга '{book.title}' успешно выдана вам на руки! Инвентарный номер: {available_copy.inventory_number}"
            )
        else:
            messages.error(
                request,
                "К сожалению, свободные экземпляры закончились. Вы можете встать в очередь."
            )

        return redirect('book')

    return redirect('book')


@login_required
def reserve_book_view(request):
    """
    Бизнес-логика добавления читателя в очередь резервирования книги.
    """
    if request.method == 'POST':
        book_id = request.POST.get('book_id')
        book = get_object_or_404(Book, id=book_id)

        # Праверка правила - один экземпляр в руки
        has_loaned_copy = book.physical_copies.filter(
            current_reader=request.user,
            status="loaned"
        ).exists()

        if has_loaned_copy:
            messages.error(
                request,
                f"Вы не можете забронировать книгу '{book.title}', так как один экземпляр уже находится у вас на руках.",
            )
            return redirect('book')

        # Проверка правила - одна бронь на экземпляр
        if request.user not in book.reserved_by.all():
            book.reserved_by.add(request.user)
            messages.success(request, f"Вы успешно встали в очередь на книгу '{book.title}'!")
        else:
            messages.warning(request, f"Вы не можете забронировать книгу '{book.title}', так как вы её уже забронировали.")

        return redirect('book')

    return redirect('book')


@login_required
def my_book_view(request):
    """
    Личный кабинет читателя
    """
    # Список книг на руках
    borrow_book = PhysicalCopy.objects.filter(
        current_reader=request.user,
        status='loaned'
    ).select_related('book').prefetch_related('book__authors')

    # Список забронированных книг
    reserved_books = Book.objects.filter(
        reserved_by=request.user
    ).prefetch_related('authors')

    context = {
        'borrow_book': borrow_book,
        'reserved_books': reserved_books,
    }

    return render(request, 'library/my_book.html', context)


# =====================================================================
# 3. Панель управления привилегированного пользователя (in_staff)
# =====================================================================

@login_required
@permission_required('library.view_physicalcopy', login_url='index', raise_exception=False)
def librarian_view(request):
    """
    Библиотекарь: панель управления читателями и книгами фонда с поиском и фильтрацией.
    """
    # Книги на руках
    borrowed_copies = PhysicalCopy.objects.filter(
        status='loaned'
    ).select_related('book', 'current_reader').prefetch_related('book__authors')

    # Книги, на которые есть очереди
    reserved_books = Book.objects.filter(
        reserved_by__isnull=False
    ).prefetch_related(
        'authors',
        'reserved_by'  # Подгружает пользователей из очереди
    ).distinct()

    # Логика поиска и фильтации книг в фонде
    search_query = request.GET.get('copy_search', '').strip()
    status_filter = request.GET.get('copy_status', '').strip()

    all_physical_copies = PhysicalCopy.objects.all().select_related(
        'book', 'current_reader'
    ).prefetch_related('book__authors')

    # Поиск книг по: инвентарному номеру, ISBN, названию
    if search_query:
        all_physical_copies = all_physical_copies.filter(
            Q(inventory_number__icontains=search_query) |
            Q(book__isbn__icontains=search_query) |
            Q(book__title__icontains=search_query)
        )

    # Фильтрация экземпляров по статусу
    if status_filter in ['available', 'loaned', 'restoration', 'archived']:
        all_physical_copies = all_physical_copies.filter(status=status_filter)

    # Сортировка
    all_physical_copies = all_physical_copies.order_by('book__title', 'inventory_number')

    context = {
        'borrowed_copies': borrowed_copies,
        'reserved_books': reserved_books,
        'all_physical_copies': all_physical_copies,
        'copy_search': search_query,
        'copy_status': status_filter,
    }
    return render(request, 'library/librarian.html', context)


@login_required
@permission_required('library.change_physicalcopy', login_url='index', raise_exception=False)
def return_book_view(request, copy_id):
    """
    Библиотекарь: принять книгу от читателя и вернуть её в доступ.
    """
    if request.method == 'POST':
        # Найти выданный экземпляр книги
        copy = get_object_or_404(
            PhysicalCopy.objects.select_related('book', 'current_reader'),
            id=copy_id,
            status='loaned'
        )

        book_title = copy.book.title
        # Получить имя читателя, у которого была книга
        reader_name = copy.current_reader.get_full_name() if copy.current_reader else "Неизвестный читатель"

        active_log = BorrowLog.objects.filter(
            physical_copy=copy,
            return_date__isnull=True
        ).first()

        if active_log:
            active_log.return_date = timezone.now().date()
            active_log.save()

        # Изменить статус книги на "доступна"
        copy.status = 'available'
        copy.current_reader = None
        copy.due_date = None
        copy.save()

        messages.success(request, f"Книга '{book_title}' принята от читателя {reader_name} и возвращена на полку!")
        return redirect('librarian')

    return redirect('librarian')


@login_required
@permission_required('library.change_physicalcopy', login_url='index', raise_exception=False)
def assign_reserve_view(request, book_id):
    """
    Библиотекарь: выдать книгу первому читателю из очереди.
    """
    if request.method == 'POST':
        book = get_object_or_404(
            Book.objects.prefetch_related('reserved_by', 'physical_copies'),
            id=book_id
        )

        # Взять первого читателя из очереди на книгу
        first_reader = book.reserved_by.all().first()
        if not first_reader:
            messages.error(request, "Очередь ожидания на эту книгу пуста.")
            return redirect('librarian')

        # Найти свободный физический экземпляр на полке
        available_copy = book.physical_copies.filter(status='available').first()
        if not available_copy:
            messages.error(request, f"Нет свободных экземпляров книги '{book.title}' на полке.")
            return redirect('librarian')

        # Выдать книгу читателю и изменить статус книги на "аренда"
        available_copy.status = 'loaned'
        available_copy.current_reader = first_reader
        available_copy.due_date = timezone.now().date() + timezone.timedelta(days=14)
        available_copy.save()

        # Удалить читателя из очереди на книгу
        book.reserved_by.remove(first_reader)

        # Получить имя читателя, которому выдана книга
        reader_name = first_reader.get_full_name()

        messages.success(
            request,
            f"Книга '{book.title}' выдана читателю {reader_name} из очереди! (Инв. №: {available_copy.inventory_number})"
        )
        return redirect('librarian')

    return redirect('librarian')


@login_required
@permission_required('library.change_book', login_url='index', raise_exception=False)
def remove_from_reserve_view(request, book_id, user_id):
    """
    Библиотекарь: удалить конкретного читателя из очереди на книгу.
    """
    if request.method == 'POST':
        book = get_object_or_404(Book.objects.prefetch_related('reserved_by'), id=book_id)

        User = get_user_model()
        user_to_remove = get_object_or_404(User, id=user_id)

        if user_to_remove in book.reserved_by.all():
            book.reserved_by.remove(user_to_remove)

            # Удалить конкретного читателя из очереди на книгу
            reader_name = user_to_remove.get_full_name()
            messages.info(request, f"Читатель {reader_name} удален из очереди на книгу '{book.title}'.")

        return redirect('librarian')

    return redirect('librarian')


@login_required
@permission_required('library.change_physicalcopy', login_url='index', raise_exception=False)
def manage_copy_status_view(request, copy_id):
    """
    Библиотекарь: переназначить статус экземпляра (доступен, на реставрации, списан).
    """
    if request.method == 'POST':
        copy = get_object_or_404(PhysicalCopy.objects.select_related('book'), id=copy_id)
        action = request.POST.get('action')

        if action == 'to_available':
            copy.status = 'available'
            copy.current_reader = None
            copy.due_date = None
            messages.success(request, f"Экземпляр №{copy.inventory_number} книги '{copy.book.title}' возвращен на полку.")

        elif action == 'to_archive':
            copy.status = 'archived'
            copy.current_reader = None
            copy.due_date = None
            messages.warning(request, f"Экземпляр №{copy.inventory_number} книги '{copy.book.title}' списан.")

        elif action == 'to_restoration':
            copy.status = 'restoration'
            copy.current_reader = None
            copy.due_date = None
            messages.info(request, f"Экземпляр №{copy.inventory_number} книги '{copy.book.title}' отправлен на реставрацию.")

        copy.save()
        return redirect('librarian')

    return redirect('librarian')


# =====================================================================
# 3. Панель управления привилегированного пользователя (in_staff)
# =====================================================================

class AuthorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API эндпоинт для получения списка авторов
    с поддержкой динамического поиска и сортировки.
    """
    queryset = Author.objects.all().prefetch_related('books')
    serializer_class = AuthorSerializer
    permission_classes = [AllowAny]

    # Подключаем встроенные фильтры DRF для поиска и сортировки
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    # Поля, по которым будет идти поиск (?search=значение)
    search_fields = ['last_name', 'first_name']

    # Поля, по которым разрешено сортировать (?ordering=last_name)
    ordering_fields = ['last_name', 'first_name']

    # Сортировка по умолчанию (если параметр не передан)
    ordering = ['last_name']


class BookListAPIView(generics.ListAPIView):
    """
    API эндпоинт для получения списка книг с динамическим поиском,
    сортировкой и автоматическим подсчетом доступных экземпляров.
    """
    serializer_class = BookSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Book.objects.annotate(
            computed_available_count=Count(
                'physical_copies',
                filter=Q(physical_copies__status='available')
            )
        ).prefetch_related('authors')

    # Подключаем фильтры DRF для поиска и сортировки
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    search_fields = ['title', 'authors__last_name', 'authors__first_name']

    ordering_fields = {
        'title': 'title',
        'authors': ['authors__last_name', 'authors__first_name']
    }
    # Сортировка по умолчанию
    ordering = ['title']

    def get_renderers(self):
        # Убираем дубли из-за Many-to-Many связей с таблицей author
        self.queryset = self.get_queryset().distinct()
        return super().get_renderers()


class BookBorrowAPIView(APIView):
    """
    API эндпоинт для выдачи книги читателю на руки (аренда).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Передаем request в контекст, чтобы сериализатор знал, какой читатель делает запрос
        serializer = BookBorrowInputSerializer(data=request.data, context={'request': request})

        # Запускает валидацию: проверяет существование книги и что у читателя ее еще нет
        serializer.is_valid(raise_exception=True)

        # Достаем уже готовый объект Книги
        book = serializer.validated_data['book_id']

        # Поиск доступного экземпляра для выдачи
        available_copy = book.physical_copies.filter(status="available").first()

        if available_copy:
            available_copy.status = 'loaned'
            available_copy.current_reader = request.user
            available_copy.issue_date = timezone.now().date()
            available_copy.due_date = timezone.now().date() + timezone.timedelta(days=14)
            available_copy.save()

            return Response({
                "message": f"Книга '{book.title}' успешно выдана вам на руки!",
                "inventory_number": available_copy.inventory_number,
                "issue_date": available_copy.issue_date.strftime("%d.%m.%Y"),
                "due_date": available_copy.due_date.strftime("%d.%m.%Y")
            }, status=status.HTTP_200_OK)

        else:
            return Response({
                "error": "К сожалению, свободные экземпляры закончились. Вы можете встать в очередь."
            }, status=status.HTTP_400_BAD_REQUEST)


class ReserveBookAPIView(APIView):
    """
    API эндпоинт для включения читателя в очередь на книгу (бронирование).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Передаем данные из запроса в сериализатор
        serializer = ReserveBookInputSerializer(data=request.data)

        # Если book_id не передан или книги нет, DRF автоматически вернет ошибку 400 Bad Request
        serializer.is_valid(raise_exception=True)

        # Получаем уже готовый объект книги из валидированных данных
        book = serializer.validated_data['book_id']

        # Проверяем, не находится ли книга уже на руках у этого читателя
        has_loaned_copy = book.physical_copies.filter(
            current_reader=request.user,
            status="loaned"
        ).exists()

        if has_loaned_copy:
            return Response({
                "message": f"Вы не можете забронировать книгу '{book.title}', так как один экземпляр уже находится у вас на руках.",
                "status": "error"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Добавляем читателя в очередь на книгу
        if request.user not in book.reserved_by.all():
            book.reserved_by.add(request.user)
            return Response({
                "message": f"Вы успешно встали в очередь на книгу '{book.title}'!",
                "status": "success"
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                "message": f"Вы не можете забронировать книгу '{book.title}', так как вы её уже забронировали.",
                "status": "warning"
            }, status=status.HTTP_400_BAD_REQUEST)


class MyBookAPIView(APIView):
    """
    API эндпоинт для получения данных о полученных и забронированных книгах
    из личного кабинета читателя.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Книги на руках
        borrow_book = PhysicalCopy.objects.filter(
            current_reader=request.user,
            status='loaned'
        ).select_related('book').prefetch_related('book__authors')

        # Забронированные книги
        reserved_books = Book.objects.filter(
            reserved_by=request.user
        ).annotate(
            # Считаем только те копии, у которых статус 'available'
            computed_available_count=Count(
                'physical_copies',
                filter=Q(physical_copies__status='available')
            )
        ).prefetch_related('authors')

        borrow_serializer = PhysicalCopySerializer(borrow_book, many=True, context={'request': request})
        reserved_serializer = BookSerializer(reserved_books, many=True, context={'request': request})

        return Response({
            'borrow_book': borrow_serializer.data,
            'reserved_books': reserved_serializer.data
        })



class IsLibrarianOrStaff(BasePermission):
    """
    Разрешение, пропускающее только сотрудников (in_staff).
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or getattr(request.user, 'role', '') == 'librarian')
        )


class LibraryHistoryStatsAPIView(APIView):
    """
    API-эндпоинт для получения журнала статистики выдачи книг.
    """
    permission_classes = [IsLibrarianOrStaff]
    # permission_classes = [AllowAny]

    def get(self, request):
        # ОПТИМИЗАЦИЯ SQL: select_related сразу подтягивает данные читателя,
        # экземпляра и самой книги за 1 единый JOIN-запрос к базе данных.
        logs = BorrowLog.objects.select_related(
            'reader',
            'physical_copy__book'
        ).all()

        payload = []
        for log in logs:
            # Берем due_date из физического экземпляра
            due_date_val = log.physical_copy.due_date

            payload.append({
                "log_id": log.id,
                "reader_id": log.reader.id,
                "username": log.reader.username,
                "phone": getattr(log.reader, 'phone', '—'),
                "copy_id": log.physical_copy.id,
                "inventory_number": log.physical_copy.inventory_number,
                "isbn": log.physical_copy.book.isbn,
                "title": log.physical_copy.book.title,
                "issue_date": log.issue_date.strftime("%d.%m.%Y") if log.issue_date else "—",
                "due_date": due_date_val.strftime("%d.%m.%Y") if due_date_val else "—",
                "return_date": log.return_date.strftime("%d.%m.%Y") if log.return_date else "На руках",
            })

        return Response({
            "status": "success",
            "count": len(payload),
            "history": payload
        }, status=status.HTTP_200_OK)

