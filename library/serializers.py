from rest_framework import serializers
from .models import Author, Book, PhysicalCopy


# =====================================================================
# 1. Сериализаторы для вложенных данных
# =====================================================================

class BookShortSerializer(serializers.ModelSerializer):
    """Короткий сериализатор для вывода книг автора"""
    class Meta:
        model = Book
        fields = ['id', 'title', 'genres']  # Укажите нужные поля книги


class AuthorSerializer(serializers.ModelSerializer):
    # Выводим список книг вложенным массивом JSON
    books = BookShortSerializer(many=True, read_only=True)

    class Meta:
        model = Author
        fields = ['id', 'last_name', 'first_name', 'books']


class AuthorShortSerializer(serializers.ModelSerializer):
    """Короткий сериализатор для авторов внутри книги"""
    class Meta:
        model = Author
        fields = ['id', 'last_name', 'first_name']


class BookSerializer(serializers.ModelSerializer):
    # Выводим авторов вложенным списком объектов
    authors = AuthorShortSerializer(many=True, read_only=True)

    # Добавляем вычисляемые поля, которые приходят из аннотации QuerySet
    available_count = serializers.IntegerField(source='computed_available_count', read_only=True)
    has_available_copies = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = ['id', 'title', 'authors', 'available_count', 'has_available_copies']

    def get_has_available_copies(self, obj):
        # Метод проверяет наличие, основываясь на аннотированном значении SQL
        return getattr(obj, 'computed_available_count', 0) > 0


class AuthorSerializerList(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'last_name', 'first_name']  # Укажите нужные поля автора


class BookSerializerList(serializers.ModelSerializer):
    authors = AuthorSerializerList(many=True, read_only=True)

    class Meta:
        model = Book
        fields = ['id', 'title', 'authors']  # Укажите нужные поля книги


class PhysicalCopySerializer(serializers.ModelSerializer):
    book = BookSerializerList(read_only=True)

    class Meta:
        model = PhysicalCopy
        fields = ['id', 'inventory_number', 'status', 'book']  # Укажите нужные поля копии


class BookBorrowInputSerializer(serializers.Serializer):
    """
        Сериализатор валидации входящих данных для выдачи книги на руки.
    """
    book_id = serializers.PrimaryKeyRelatedField(
        queryset=Book.objects.all(),
        error_messages={
            'required': "Параметр 'book_id' обязателен для заполнения.",
            'does_not_exist': "Книга с таким ID не найдена."
        }
    )

    def validate_book_id(self, book):
        """
        Валидация поля book_id.
        Один экземпляр книги в одни руки.
        """
        user = self.context['request'].user

        already_has_copy = book.physical_copies.filter(
            current_reader=user,
            status="loaned"
        ).exists()

        if already_has_copy:
            raise serializers.ValidationError(
                f"Вы не можете взять книгу '{book.title}', так как один экземпляр уже находится у вас на руках."
            )

        return book


class ReserveBookInputSerializer(serializers.Serializer):
    """
        Сериализатор валидации входящих данных для бронирования книги.
    """
    book_id = serializers.PrimaryKeyRelatedField(
        queryset=Book.objects.all(),
        error_messages={
            'required': 'Параметр book_id обязателен.',
            'does_not_exist': 'Книга с таким ID не найдена.'
        }
    )
