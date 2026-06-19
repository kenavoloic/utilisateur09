from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from .models import Collection, Galerie, VisiteurGalerie, ordonner_photos


@never_cache
def galerie_detail(request, galerie_slug):
    """Vue pour afficher une galerie spécifique.

    @never_cache : peut afficher le bandeau "Mode privé" d'une session
    active (cf. galerie_privee plus bas pour le détail du risque)."""
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


@never_cache
def collection_detail(request, galerie_slug, collection_slug):
    """Vue pour afficher une collection spécifique d'une galerie (cf.
    galerie_detail : même raison pour @never_cache)."""
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


@never_cache
def galerie_privee(request, galerie_slug):
    """Vue pour afficher une galerie privée à un visiteur authentifié.

    L'authentification se fait par token, transmis soit en session (suite à la
    saisie du code d'accès sur l'accueil), soit en paramètre d'URL (lien direct
    envoyé par email), ce qui permet de retrouver le visiteur sans relire le code.

    @never_cache : sans ça, le bouton précédent du navigateur peut réafficher
    une version mise en cache de la page après déconnexion, montrant les
    photos privées sans revérifier la session auprès du serveur.
    """
    token_url = request.GET.get("token")
    token = token_url or request.session.get("visiteur_token")

    visiteur = VisiteurGalerie.get_visiteur_par_token(token) if token else None

    if (
        not visiteur
        or not visiteur.peut_acceder()
        or visiteur.acces_galerie.galerie.slug != galerie_slug
    ):
        messages.error(request, "Accès non autorisé à cette galerie privée.")
        return redirect("accueil:index")

    # Un lien direct (token en paramètre) non encore présent en session
    # correspond à une nouvelle visite ; on ne recompte pas les rechargements
    # de page d'une session déjà authentifiée.
    if token_url and request.session.get("visiteur_token") != token:
        visiteur.marquer_visite()
        visiteur.acces_galerie.incrementer_acces()

    request.session["visiteur_token"] = visiteur.token_acces
    request.session["acces_galerie_id"] = visiteur.acces_galerie_id

    galerie = visiteur.acces_galerie.galerie

    collections = list(galerie.collections.order_by("ordre_affichage", "nom"))

    photos_directes = ordonner_photos(
        galerie.photos.exclude(collections__galerie=galerie).distinct(),
        galerie.ordre_photos,
    )

    context = {
        "galerie": galerie,
        "collections": collections,
        "photos_directes": photos_directes,
    }

    return render(request, "accueil/galerie_detail.html", context)


def deconnexion_privee(request):
    """Quitte le mode privé en effaçant la session du visiteur."""
    request.session.pop("visiteur_token", None)
    request.session.pop("acces_galerie_id", None)
    messages.info(request, "Vous avez quitté le mode privé.")
    return redirect("accueil:index")
