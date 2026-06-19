from .models import AccueilConfig


def config(request):
    """Expose la configuration du site à tous les templates, pour que le logo
    et les liens de navigation s'affichent sur toutes les pages (pas
    seulement celles qui la passaient explicitement dans leur contexte)."""
    return {"config": AccueilConfig.get_config()}
