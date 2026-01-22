from django.urls import path

from django_auth0.views import auth0_login, auth0_callback, auth0_logout

app_name = "azure_auth"
urlpatterns = [
    path("login", auth0_login, name="login"),
    path("logout", auth0_logout, name="logout"),
    path("callback", auth0_callback, name="callback"),
]