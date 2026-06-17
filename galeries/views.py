from django.db.models import Q
from django.http import Http404
from django.shortcuts import render

from .models import Galerie, Photo


def galerie_detail(request, galerie_slug):
    """Vue pour afficher une galerie spécifique."""
    try:
        galerie = Galerie.objects.get(slug=galerie_slug, est_publique=True)
    except Galerie.DoesNotExist:
        raise Http404("Galerie non trouvée")

    photos = Photo.objects.filter(
        Q(galeries=galerie) | Q(collections__galerie=galerie)
    ).distinct().order_by("id")

    autres_galeries = (
        Galerie.objects.filter(est_publique=True)
        .exclude(pk=galerie.pk)
        .order_by("ordre_affichage", "nom")
    )

    context = {
        "galerie": galerie,
        "photos": photos,
        "galeries": autres_galeries,
    }

    return render(request, "accueil/galerie_detail.html", context)
