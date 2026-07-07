from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from django.views import View


def _ok(request):
    return HttpResponse("ok")


class _OkView(View):
    """Project CBV: the views check must resolve it via ``view_class``."""

    def get(self, request):
        return HttpResponse("ok cbv")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("ok/", _ok, name="ok"),
    path("ok-cbv/", _OkView.as_view(), name="ok-cbv"),
]
