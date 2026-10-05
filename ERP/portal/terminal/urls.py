from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from terminal import views
from terminal.erpnext import JOB_CARD_NAME


class JobCardConverter:
    """Only real job card names route; anything else is a 404 before ERPNext is called."""

    regex = JOB_CARD_NAME.pattern

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(JobCardConverter, "jobcard")

urlpatterns = [
    path("", views.queue_view, name="queue"),
    path("job/<jobcard:name>/start/", views.job_action, {"action": "start"}, name="start"),
    path("job/<jobcard:name>/pause/", views.job_action, {"action": "pause"}, name="pause"),
    path("job/<jobcard:name>/resume/", views.job_action, {"action": "resume"}, name="resume"),
    path("job/<jobcard:name>/complete/", views.complete_view, name="complete"),
    path("login/", auth_views.LoginView.as_view(template_name="terminal/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
