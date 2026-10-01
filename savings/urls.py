from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("pay/", views.submit_payment, name="submit_payment"),
    path("pay/<int:day_id>/", views.submit_payment, name="submit_payment_day"),
    path("manage/", views.admin_home, name="admin_home"),
    path("manage/payments/<int:pk>/confirm/", views.confirm_payment, name="confirm_payment"),
    path("manage/payments/<int:pk>/reject/", views.reject_payment, name="reject_payment"),
    path("manage/days/<int:pk>/skip/", views.toggle_skip, name="toggle_skip"),
    path("manage/rounds/<int:pk>/payout/", views.record_payout, name="record_payout"),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]