import datetime
from fractions import Fraction
import os
import pyexiv2
from PIL import Image as PILImage

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.text import slugify


class PhotoStorage(FileSystemStorage):
    """Renomme les fichiers en collision avec un suffixe numérique (_001, _002, ..., _999)"""

    def get_available_name(self, name, max_length=None):
        base, ext = os.path.splitext(name)
        compteur = 1
        nouveau_nom = name
        while self.exists(nouveau_nom):
            nouveau_nom = f"{base}_{compteur:03d}{ext}"
            compteur += 1
        return nouveau_nom


def photo_upload_path(instance, filename):
    return f'photos/{filename}'


class Galerie(models.Model):
    nom = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    image_couverture = models.ImageField(upload_to="galeries/couvertures/", blank=True)
    est_publique = models.BooleanField(default=True)
    ordre_affichage = models.PositiveIntegerField(default=0)

    masonry_layout_manuel = models.BooleanField(default=True, verbose_name="Masonry manuel", help_text="Ordre d'affichage défini par le photographe.",)
    #created_at = models.DateTimeField(auto_now_add=True)
    #updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Galerie"
        verbose_name_plural = "Galeries"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generer_slug_unique()
        super().save(*args, **kwargs)

    def _generer_slug_unique(self):
        slug_base = slugify(self.nom)
        slug = slug_base
        compteur = 1
        while Galerie.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            compteur += 1
            slug = f"{slug_base}-{compteur}"
        return slug

    def nombre_collections(self):
        return Galerie.objects.filter(pk=self.pk).aggregate(
            nombre=models.Count('collections', distinct=True)
        )['nombre']

    def nombre_total_photos(self):
        # un Count(distinct=True) ne peut pas dédupliquer une photo présente
        # à la fois via la relation directe et via une collection : on passe
        # par Photo plutôt que par un annotate sur Galerie
        return Photo.objects.filter(
            models.Q(galeries=self) | models.Q(collections__galerie=self)
        ).distinct().count()

    def get_total_photos(self):
        return self.nombre_total_photos()

    def get_photo_couverture(self):
        """Retourne la photo marquée comme couverture, sinon None"""
        return self.photos.filter(est_couverture=True).first()


class Collection(models.Model):
    nom = models.CharField(max_length=255)
    slug = models.SlugField(blank=True)

    #en cas de suppression de la galerie qui contient la collection, la collection est supprimée
    galerie = models.ForeignKey(
        Galerie,
        on_delete=models.CASCADE,
        related_name='collections',
    )

    masonry_layout_manuel = models.BooleanField(default=True, verbose_name="Masonry manuel", help_text="Ordre d'affichage défini par le photographe.",)
    ordre_affichage = models.PositiveIntegerField(default=0)
        
    class Meta:
        unique_together = ('galerie', 'slug')

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generer_slug_unique()
        super().save(*args, **kwargs)

    def _generer_slug_unique(self):
        slug_base = slugify(self.nom)
        slug = slug_base
        compteur = 1
        while Collection.objects.filter(galerie=self.galerie, slug=slug).exclude(pk=self.pk).exists():
            compteur += 1
            slug = f"{slug_base}-{compteur}"
        return slug

    def nombre_photos(self):
        return Collection.objects.filter(pk=self.pk).aggregate(
            nombre=models.Count('photos', distinct=True)
        )['nombre']


class Tag(models.Model):
    nom = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generer_slug_unique()
        super().save(*args, **kwargs)

    def _generer_slug_unique(self):
        slug_base = slugify(self.nom)
        slug = slug_base
        compteur = 1
        while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            compteur += 1
            slug = f"{slug_base}-{compteur}"
        return slug


class Photo(models.Model):
    """Photo chargée dans une galerie ou dans la collection d'une galerie"""

    image        = models.ImageField(upload_to=photo_upload_path, storage=PhotoStorage())
    nom_fichier  = models.CharField(max_length=255, editable=False)
    taille       = models.PositiveIntegerField(null=True, help_text="octets")
    largeur      = models.PositiveIntegerField(null=True, help_text="pixels")
    hauteur      = models.PositiveIntegerField(null=True, help_text="pixels")

    titre        = models.CharField(max_length=255, blank=True)
    description  = models.TextField(blank=True)
    est_couverture = models.BooleanField(default=False, verbose_name="Photo de couverture")

    date_prise_de_vue = models.DateTimeField(null=True, blank=True)
    appareil     = models.CharField(max_length=255, blank=True)
    objectif     = models.CharField(max_length=255, blank=True)
    ouverture    = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    vitesse      = models.CharField(max_length=20, blank=True)
    iso          = models.PositiveIntegerField(null=True, blank=True, verbose_name="ISO")

    latitude     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    auteur_nom = models.CharField(max_length=255, null=True, blank=True)
    auteur_prenom = models.CharField(max_length=255, null=True, blank=True)
    auteur_email = models.EmailField(max_length=255, null=True, blank=True)

    # une photo peut appartenir à plusieurs galeries  en même temps
    # en cas de suppression d'une galerie les photos demeurent
    galeries = models.ManyToManyField(
        Galerie,
        blank=True,
        related_name='photos',
    )
    
    # une photo peut appartenir à plusieurs collections en même temps
    # en cas de suppression d'une collection les photos demeurent
    collections = models.ManyToManyField(
        Collection,
        blank=True,
        related_name='photos',
    )
    
    # un tag va nécessairement s'appliquer à plusieurs images
    # un tag est nécessairement unique
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='photos',
    )

    def save(self, *args, **kwargs):
        is_new = not self.pk
        ancienne_image = None
        if not is_new:
            ancienne = Photo.objects.get(pk=self.pk)
            ancienne_image = ancienne.image.name

        super().save(*args, **kwargs)

        image_changee = is_new or (ancienne_image and ancienne_image != self.image.name)
        if image_changee:
            self._extraire_metadonnees()
            super().save(update_fields=[
                'nom_fichier', 'taille', 'largeur', 'hauteur',
                'titre', 'description', 'date_prise_de_vue',
                'appareil', 'objectif', 'ouverture', 'vitesse', 'iso',
                'latitude', 'longitude',
            ])

    def delete(self, *args, **kwargs):
        chemin = self.image.path if self.image else None
        super().delete(*args, **kwargs)
        if chemin and os.path.isfile(chemin):
            os.remove(chemin)

    def _extraire_metadonnees(self):
        chemin = self.image.path

        self.nom_fichier = os.path.basename(chemin)
        self.taille = os.path.getsize(chemin)

        try:
            with PILImage.open(chemin) as pil_img:
                self.largeur, self.hauteur = pil_img.size
        except Exception:
            pass

        try:
            with pyexiv2.Image(chemin) as img:
                exif = img.read_exif()
                iptc = img.read_iptc()
        except Exception:
            return

        marque = exif.get('Exif.Image.Make', '')
        modele = exif.get('Exif.Image.Model', '')
        self.appareil = f"{marque} {modele}".strip()

        self.objectif = exif.get('Exif.Photo.LensModel', '')

        fnumber = exif.get('Exif.Photo.FNumber')
        if fnumber:
            try:
                self.ouverture = round(float(Fraction(fnumber)), 1)
            except (ValueError, ZeroDivisionError):
                pass

        self.vitesse = exif.get('Exif.Photo.ExposureTime', '')

        iso = exif.get('Exif.Photo.ISOSpeedRatings')
        if iso:
            try:
                self.iso = int(iso)
            except ValueError:
                pass

        date_str = exif.get('Exif.Photo.DateTimeOriginal')
        if date_str:
            try:
                self.date_prise_de_vue = datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                pass

        self.titre = iptc.get('Iptc.Application2.ObjectName', '')
        self.description = iptc.get('Iptc.Application2.Caption', '')

        try:
            lat = exif.get('Exif.GPSInfo.GPSLatitude')
            lat_ref = exif.get('Exif.GPSInfo.GPSLatitudeRef', 'N')
            lon = exif.get('Exif.GPSInfo.GPSLongitude')
            lon_ref = exif.get('Exif.GPSInfo.GPSLongitudeRef', 'E')

            if lat and lon:
                self.latitude = self._dms_en_decimal(lat)
                self.longitude = self._dms_en_decimal(lon)
                if lat_ref == 'S':
                    self.latitude = -self.latitude
                if lon_ref == 'W':
                    self.longitude = -self.longitude
        except Exception:
            pass

    @staticmethod
    def _dms_en_decimal(dms_str):
        d, m, s = [Fraction(x) for x in dms_str.split()]
        return round(float(d) + float(m) / 60 + float(s) / 3600, 6)

class AccesGalerie(models.Model):
    """Système d'accès privé pour les galeries"""

    galerie = models.ForeignKey(
        Galerie, on_delete=models.CASCADE, related_name="acces_prives"
    )

    # Code d'accès unique pour cette galerie
    code_acces = models.CharField(
        max_length=20, unique=True, help_text="Code d'accès généré automatiquement"
    )

    # Titre personnalisé pour cet accès (optionnel)
    titre_acces = models.CharField(
        max_length=100,
        blank=True,
        help_text="Titre personnalisé pour identifier cet accès (ex: 'Mariage Julie & Pierre')",
    )

    # Configuration d'accès
    date_creation = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateTimeField(
        blank=True, null=True, help_text="Laissez vide pour un accès illimité"
    )

    # Limitations d'accès
    nombre_max_visiteurs = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Nombre maximum de visiteurs autorisés (laissez vide pour illimité)",
    )

    # Permissions
    permettre_telechargement = models.BooleanField(
        default=True,
        help_text="Autoriser le téléchargement des photos haute résolution",
    )

    # Statistiques
    nombre_acces = models.PositiveIntegerField(
        default=0, help_text="Nombre total d'accès avec ce code"
    )

    # Activation
    est_actif = models.BooleanField(
        default=True, help_text="Désactiver temporairement cet accès"
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Accès privé"
        verbose_name_plural = "Accès privés"

    def __str__(self):
        titre = self.titre_acces or f"Accès {self.code_acces}"
        return f"{self.galerie.nom} - {titre}"

    def save(self, *args, **kwargs):
        if not self.code_acces:
            self.code_acces = self.generer_code_acces()
        super().save(*args, **kwargs)

    @staticmethod
    def generer_code_acces():
        """Génère un code d'accès unique"""
        while True:
            # Générer un code lisible (sans caractères ambigus)
            code = get_random_string(
                length=8, allowed_chars="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            )
            # Vérifier l'unicité
            if not AccesGalerie.objects.filter(code_acces=code).exists():
                return code

    def est_valide(self):
        """Vérifie si l'accès est valide (actif, pas expiré, limite non atteinte)"""
        from django.utils import timezone

        if not self.est_actif:
            return False

        if self.date_expiration and timezone.now() > self.date_expiration:
            return False

        if self.nombre_max_visiteurs:
            visiteurs_actuels = self.visiteurs.filter(est_actif=True).count()
            if visiteurs_actuels >= self.nombre_max_visiteurs:
                return False

        return True

    def incrementer_acces(self):
        """Incrémente le compteur d'accès"""
        self.nombre_acces += 1
        self.save(update_fields=["nombre_acces"])


class VisiteurGalerie(models.Model):
    """Visiteur ayant accès à une galerie privée"""

    acces_galerie = models.ForeignKey(
        AccesGalerie, on_delete=models.CASCADE, related_name="visiteurs"
    )

    # Identité du visiteur
    email = models.EmailField(help_text="Email du visiteur")
    nom = models.CharField(
        max_length=100, blank=True, help_text="Nom du visiteur (optionnel)"
    )

    # Authentification
    token_acces = models.CharField(
        max_length=64,
        unique=True,
        help_text="Token unique pour l'authentification en session",
    )

    # Suivi d'activité
    date_premier_acces = models.DateTimeField(
        blank=True, null=True, help_text="Date du premier accès à la galerie"
    )
    date_dernier_acces = models.DateTimeField(
        blank=True, null=True, help_text="Date du dernier accès à la galerie"
    )

    nombre_visites = models.PositiveIntegerField(
        default=0, help_text="Nombre total de visites"
    )

    # Activation
    est_actif = models.BooleanField(
        default=True, help_text="Désactiver l'accès pour ce visiteur spécifique"
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("acces_galerie", "email")]
        ordering = ["-date_dernier_acces"]
        verbose_name = "Visiteur"
        verbose_name_plural = "Visiteurs"

    def __str__(self):
        nom_affiche = self.nom or self.email.split("@")[0]
        return f"{nom_affiche} - {self.acces_galerie.galerie.nom}"

    def save(self, *args, **kwargs):
        if not self.token_acces:
            self.token_acces = self.generer_token()
        super().save(*args, **kwargs)

    @staticmethod
    def generer_token():
        """Génère un token d'accès sécurisé unique"""
        while True:
            token = secrets.token_urlsafe(48)  # 64 caractères URL-safe
            if not VisiteurGalerie.objects.filter(token_acces=token).exists():
                return token

    def marquer_visite(self):
        """Enregistre une nouvelle visite"""
        from django.utils import timezone

        maintenant = timezone.now()

        if not self.date_premier_acces:
            self.date_premier_acces = maintenant

        self.date_dernier_acces = maintenant
        self.nombre_visites += 1
        self.save(
            update_fields=["date_premier_acces", "date_dernier_acces", "nombre_visites"]
        )

    def peut_acceder(self):
        """Vérifie si le visiteur peut accéder à la galerie"""
        return self.est_actif and self.acces_galerie.est_valide()

    def envoyer_notification_acces(self):
        """Envoie un email de notification d'accès au visiteur"""
        try:
            galerie = self.acces_galerie.galerie
            sujet = f"Accès à la galerie privée : {galerie.nom}"

            message = f"""Bonjour{" " + self.nom if self.nom else ""},

Vous avez maintenant accès à la galerie privée "{galerie.nom}".

Code d'accès : {self.acces_galerie.code_acces}
Lien direct : {settings.SITE_URL}/galerie/prive/{self.acces_galerie.code_acces}/?token={self.token_acces}

{galerie.description if galerie.description else ""}

Cordialement,
{settings.DEFAULT_FROM_EMAIL}
            """

            send_mail(
                subject=sujet,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.email],
                fail_silently=False,
            )
            return True

        except Exception:
            return False

    @staticmethod
    def get_galeries_accessibles(email):
        """Récupère toutes les galeries privées accessibles à un visiteur donné"""

        visiteurs = VisiteurGalerie.objects.filter(
            email=email, est_actif=True, acces_galerie__est_actif=True
        ).select_related("acces_galerie__galerie")

        # Filtrer les accès valides (non expirés, limites respectées)
        galeries_accessibles = []
        for visiteur in visiteurs:
            if visiteur.acces_galerie.est_valide():
                galeries_accessibles.append(visiteur.acces_galerie.galerie.id)

        return Galerie.objects.filter(
            id__in=galeries_accessibles, est_publique=False
        ).order_by("nom")

    @staticmethod
    def get_visiteur_par_token(token):
        """Récupère un visiteur par son token d'accès"""
        try:
            return VisiteurGalerie.objects.select_related("acces_galerie__galerie").get(
                token_acces=token, est_actif=True
            )
        except VisiteurGalerie.DoesNotExist:
            return None    
