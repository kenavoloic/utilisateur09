from django.urls import path

from . import views

app_name = "galeries"

urlpatterns = [
    path("<slug:galerie_slug>/", views.galerie_detail, name="galerie_detail"),
]
