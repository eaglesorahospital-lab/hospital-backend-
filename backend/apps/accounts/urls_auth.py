from django.urls import path
from .views_auth import (
    LoginView,
    RegisterView,
    CurrentUserView,
    LogoutView,
    TokenRefreshWithThrottleView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth_login'),
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('refresh/', TokenRefreshWithThrottleView.as_view(), name='auth_refresh'),
    path('me/', CurrentUserView.as_view(), name='auth_me'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
]
