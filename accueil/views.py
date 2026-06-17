# from django.http import HttpResponse
# from django.shortcuts import render


# def accueil(request):
#     return HttpResponse('Where is Zlatan?')

# def xyz(request):
#     return HttpResponse('Zlatan was here')

# def index(request):
#     return render(request, 'accueil/index.html')

# def contact(request):
#     return render(request, 'accueil/contact.html')


from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from galeries.models import AccesGalerie, Galerie, VisiteurGalerie

from .forms import ContactForm


def index(request):
    """Vue pour la page d'accueil du studio photographique."""

    # Récupérer la configuration de l'accueil
    from .models import AccueilConfig, SectionAccueil

    config = AccueilConfig.get_config()

    # Traiter le formulaire d'accès privé (AJAX)
    if request.method == "POST" and (
        "email" in request.POST and "code" in request.POST
    ):
        email = request.POST.get("email", "").strip()
        code_acces = request.POST.get("code", "").upper().strip()

        if not email or not code_acces:
            return JsonResponse(
                {"success": False, "error": "Email et code d'accès requis."}
            )

        try:
            # Rechercher l'accès galerie
            acces = AccesGalerie.objects.get(code_acces=code_acces)

            if not acces.est_valide():
                return JsonResponse(
                    {"success": False, "error": "Ce code d'accès n'est plus valide."}
                )

            # Vérifier que le visiteur est autorisé (ne pas créer automatiquement)
            try:
                visiteur = VisiteurGalerie.objects.get(acces_galerie=acces, email=email)
            except VisiteurGalerie.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Votre adresse email n'est pas autorisée pour cette galerie.",
                    }
                )

            if not visiteur.peut_acceder():
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Votre accès à cette galerie a été désactivé.",
                    }
                )

            # Marquer la visite et incrémenter les compteurs
            visiteur.marquer_visite()
            acces.incrementer_acces()

            # Stocker le token en session
            request.session["visiteur_token"] = visiteur.token_acces
            request.session["acces_galerie_id"] = acces.id

            # Rediriger vers la galerie privée
            galerie_url = f"/galerie/prive/{acces.galerie.slug}/"
            return JsonResponse(
                {
                    "success": True,
                    "message": f"Accès autorisé à la galerie : {acces.galerie.nom}",
                    "redirect_url": galerie_url,
                }
            )

        except AccesGalerie.DoesNotExist:
            return JsonResponse({"success": False, "error": "Code d'accès invalide."})
        except Exception:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Erreur lors de la vérification. Veuillez réessayer.",
                }
            )

    # Récupérer les galeries depuis la base de données
    galeries = Galerie.objects.filter(est_publique=True).order_by(
        "ordre_affichage", "nom"
    )

    # Récupérer les sections personnalisées
    sections = SectionAccueil.objects.filter(est_active=True).order_by(
        "position", "ordre"
    )

    context = {
        "config": config,
        "galeries": galeries,
        "total_collections": galeries.count(),
        "hero_image": config.hero_image,
        "sections": sections,
    }

    return render(request, "accueil/index.html", context)


def contact(request):
    """Vue pour le formulaire de contact."""

    # Récupérer la configuration de l'accueil
    from .models import AccueilConfig

    config = AccueilConfig.get_config()

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            if form.send_email():
                messages.success(
                    request,
                    "Votre message a bien été envoyé ! Je vous répondrai dans les plus brefs délais.",
                )
                return redirect("accueil:contact")
            else:
                messages.error(
                    request,
                    "Erreur lors de l'envoi du message. Veuillez réessayer ou me contacter directement à contact@horslemurs.fr",
                )
    else:
        form = ContactForm()

    context = {
        "form": form,
        "titre_site": config.titre_site,
        "sous_titre": config.sous_titre,
    }

    return render(request, "accueil/contact.html", context)
