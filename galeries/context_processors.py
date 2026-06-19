from .models import VisiteurGalerie


def visiteur_prive(request):
    """Expose le visiteur privé de la session courante à tous les templates,
    pour afficher un indicateur de mode privé persistant sur l'ensemble du site."""
    token = request.session.get("visiteur_token")
    if not token:
        return {}

    visiteur = VisiteurGalerie.get_visiteur_par_token(token)
    if not visiteur or not visiteur.peut_acceder():
        return {}

    return {
        "visiteur_prive": visiteur,
        "galerie_privee_session": visiteur.acces_galerie.galerie,
    }
