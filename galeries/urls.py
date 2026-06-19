from django.urls import path

from . import views

app_name = "galeries"

urlpatterns = [
    path("prive/<slug:galerie_slug>/", views.galerie_privee, name="galerie_privee"),
    path("deconnexion-privee/", views.deconnexion_privee, name="deconnexion_privee"),
    path("<slug:galerie_slug>/", views.galerie_detail, name="galerie_detail"),
    path(
        "<slug:galerie_slug>/<slug:collection_slug>/",
        views.collection_detail,
        name="collection_detail",
    ),
]
