from django.http import Http404
from django.shortcuts import render

from .models import Collection, Galerie, ordonner_photos


def galerie_detail(request, galerie_slug):
    """Vue pour afficher une galerie spécifique."""
    try:
        galerie = Galerie.objects.get(slug=galerie_slug, est_publique=True)
    except Galerie.DoesNotExist:
        raise Http404("Galerie non trouvée")

    collections = list(galerie.collections.order_by("ordre_affichage", "nom"))

    photos_directes = ordonner_photos(
        galerie.photos.exclude(collections__galerie=galerie).distinct(),
        galerie.ordre_photos,
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


def collection_detail(request, galerie_slug, collection_slug):
    """Vue pour afficher une collection spécifique d'une galerie."""
    try:
        galerie = Galerie.objects.get(slug=galerie_slug, est_publique=True)
    except Galerie.DoesNotExist:
        raise Http404("Galerie non trouvée")

    try:
        collection = galerie.collections.get(slug=collection_slug)
    except Collection.DoesNotExist:
        raise Http404("Collection non trouvée")

    photos = ordonner_photos(collection.photos.all(), collection.ordre_photos)

    collections_galerie = list(galerie.collections.order_by("ordre_affichage", "nom"))
    index = collections_galerie.index(collection)
    collection_precedente = collections_galerie[index - 1] if index > 0 else None
    collection_suivante = (
        collections_galerie[index + 1] if index < len(collections_galerie) - 1 else None
    )

    context = {
        "galerie": galerie,
        "collection": collection,
        "photos": photos,
        "collection_precedente": collection_precedente,
        "collection_suivante": collection_suivante,
    }

    return render(request, "accueil/collection_detail.html", context)
