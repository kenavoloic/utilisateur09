from django.core.exceptions import ValidationError
from django.db import models

class AccueilConfig(models.Model):

    titre_site = models.CharField(max_length=255, blank=True, null=True)
    sous_titre = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    hero_image = models.ImageField(upload_to="accueil/hero/", blank=True, null=True)
    titre_galeries = models.CharField(max_length=255, blank=True, null=True)
    titre_acces_prive = models.CharField(max_length=255, blank=True, null=True)
    description_acces_prive = models.TextField(blank=True, null=True)

    # Menu de navigation
    nav_galeries = models.CharField(max_length=50, default="Galeries", verbose_name="Lien menu galeries")
    nav_acces_prive = models.CharField(max_length=50, default="Accès privé", verbose_name="Lien menu accès privé")

    # Bloc hero
    nom_site = models.CharField(max_length=100, default="Hors les Murs", verbose_name="Nom du site")
    titre_complet = models.CharField(max_length=200, default="Hors les Murs — Studio Photographique", verbose_name="Titre complet", help_text="Titre affiché dans l'onglet du navigateur")
    hero_sous_titre = models.CharField(max_length=100, default="Studio photographique", verbose_name="Sous-titre hero")
    hero_description = models.TextField(default="Capturer l'instant, révéler l'émotion.", verbose_name="Description hero")
    btn_voir_galeries = models.CharField(max_length=50, default="Voir les galeries", verbose_name="Bouton galeries")
    btn_acces_prive = models.CharField(max_length=50, default="Accès privé", verbose_name="Bouton accès privé")

    # Modal d'accès privé
    modal_titre = models.CharField(max_length=255, blank=True, null=True)
    modal_sous_titre = models.TextField(blank=True, null=True)
    modal_placeholder_code = models.CharField(max_length=255, blank=True, null=True)
    modal_btn_entrer_code = models.CharField(max_length=50, default="Entrer mon code", verbose_name="Bouton modal")
    modal_btn_acceder = models.CharField(max_length=50, default="Accéder à la galerie", verbose_name="Bouton accès galerie")

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"

    def __str__(self):
        return f"Configuration accueil - {self.titre_site}"

    def save(self, *args, **kwargs):
        if not self.pk and AccueilConfig.objects.exists():
            raise ValidationError("Il ne peut y avoir qu'une configuration d'accueil")
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(pk=1)
        return config

class SectionAccueil(models.Model):
    """Sections personnalisables de la page d'accueil"""

    POSITION_CHOICES = [
        ("hero", "Section Hero"),
        ("galeries", "Avant les galeries"),
        ("prive", "Avant accès privé"),
        ("footer", "Avant le footer"),
    ]

    titre = models.CharField(max_length=200, blank=True, null=True)
    contenu = models.TextField(help_text="Contenu de la section (HTML autorisé)")
    position = models.CharField(
        max_length=20,
        choices=POSITION_CHOICES,
        help_text="Position de la section sur la page",
    )
    ordre = models.PositiveIntegerField(
        default=0, help_text="Ordre d'affichage (plus petit en premier)"
    )
    est_active = models.BooleanField(default=True, help_text="Afficher cette section")

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "ordre", "titre"]
        verbose_name = "Section d'accueil"
        verbose_name_plural = "Sections d'accueil"

    def __str__(self):
        return f"{self.titre} ({self.get_position_display()})"

                
