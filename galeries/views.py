from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import render

from .models import Galerie, Photo


def galerie_detail(request, galerie_slug):
    """Vue pour afficher une galerie spécifique."""
    try:
        galerie = Galerie.objects.get(slug=galerie_slug, est_publique=True)
    except Galerie.DoesNotExist:
        raise Http404("Galerie non trouvée")

    collections = galerie.collections.order_by("ordre_affichage", "nom").prefetch_related(
        Prefetch("photos", queryset=Photo.objects.order_by("id"))
    )

    photos_directes = (
        galerie.photos.exclude(collections__galerie=galerie).distinct().order_by("id")
    )

    autres_galeries = (
        Galerie.objects.filter(est_publique=True)
        .exclude(pk=galerie.pk)
        .order_by("ordre_affichage", "nom")
    )

    context = {
        "galerie": galerie,
        "collections": collections,
        "photos_directes": photos_directes,
        "galeries": autres_galeries,
    }

    return render(request, "accueil/galerie_detail.html", context)
