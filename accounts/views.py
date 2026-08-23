from django.contrib.auth import views as auth_views

from .forms import LoginForm


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True
