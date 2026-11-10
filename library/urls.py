from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView

from . import views

router = DefaultRouter()
router.register(r'authors', views.AuthorViewSet, basename='author')

urlpatterns = [
    path('', views.index_view, name='index'),
    path('authors/', views.author_view, name='author'),
    path('books/', views.book_view, name='book'),
    path('books/borrow/', views.borrow_book_view, name='borrow_book'),
    path('books/reserve/', views.reserve_book_view, name='reserve_book'),
    path('books/my_books/', views.my_book_view, name='my_book'),
    path('register/', views.register_reader_view, name='register_reader'),
    path('login/', auth_views.LoginView.as_view(template_name='library/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('librarian/dashboard/', views.librarian_view, name='librarian'),
    path('librarian/return/<int:copy_id>/', views.return_book_view, name='return_book'),
    path('librarian/reserve/assign/<int:book_id>/', views.assign_reserve_view, name='assign_reserve'),
    path('librarian/reserve/remove/<int:book_id>/<int:user_id>/', views.remove_from_reserve_view, name='remove_reserve'),
    path('librarian/copy/status/<int:copy_id>/', views.manage_copy_status_view, name='manage_copy_status'),

    path('api/librarian/stats/history/', views.LibraryHistoryStatsAPIView.as_view(), name='api_history_stats'),

    path('api/token/', TokenObtainPairView.as_view(), name='api_token_obtain'),
    path('api/', include(router.urls)),
    path('api/books/', views.BookListAPIView.as_view(), name='api_book_catalog'),
    path('api/books/borrow/', views.BookBorrowAPIView.as_view(), name='api_borrow_book'),
    path('api/books/reserve/', views.ReserveBookAPIView.as_view(), name='api_reserve_book'),
    path('api/my-books/', views.MyBookAPIView.as_view(), name='api_my_books'),

]

