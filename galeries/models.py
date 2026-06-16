import datetime
from fractions import Fraction
import os
import pyexiv2
from PIL import Image as PILImage

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


class PhotoStorage(FileSystemStorage):
    """Renomme les fichiers en collision avec un suffixe numérique (_01, _02, ..., _99)"""

    def get_available_name(self, name, max_length=None):
        base, ext = os.path.splitext(name)
        compteur = 1
        nouveau_nom = name
        while self.exists(nouveau_nom):
            nouveau_nom = f"{base}_{compteur:02d}{ext}"
            compteur += 1
        return nouveau_nom


def photo_upload_path(instance, filename):
    return f'photos/{filename}'


class Galerie(models.Model):
    nom = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    est_publique = models.BooleanField(default=True)
    #created_at = models.DateTimeField(auto_now_add=True)
    #updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Galerie"
        verbose_name_plural = "Galeries"

    def __str__(self):
        return self.nom



class Collection(models.Model):
    nom = models.CharField(max_length=200)
    galerie = models.ForeignKey(
        Galerie,
        on_delete=models.CASCADE,
        related_name='collections',
    )

    def __str__(self):
        return self.nom


class Photo(models.Model):
    """Photo chargée dans une galerie ou dans la collection d'une galerie"""

    image        = models.ImageField(upload_to=photo_upload_path, storage=PhotoStorage())
    nom_fichier  = models.CharField(max_length=255, editable=False)
    taille       = models.PositiveIntegerField(null=True, help_text="octets")
    largeur      = models.PositiveIntegerField(null=True, help_text="pixels")
    hauteur      = models.PositiveIntegerField(null=True, help_text="pixels")

    titre        = models.CharField(max_length=255, blank=True)
    description  = models.TextField(blank=True)

    date_prise_de_vue = models.DateTimeField(null=True, blank=True)
    appareil     = models.CharField(max_length=100, blank=True)
    objectif     = models.CharField(max_length=100, blank=True)
    ouverture    = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    vitesse      = models.CharField(max_length=20, blank=True)
    iso          = models.PositiveIntegerField(null=True, blank=True, verbose_name="ISO")

    latitude     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    auteur_nom = models.CharField(max_length=255, null=True, blank=True)
    auteur_prenom = models.CharField(max_length=255, null=True, blank=True)
    auteur_email = models.EmailField(max_length=255, null=True, blank=True)

    galeries = models.ManyToManyField(
        Galerie,
        blank=True,
        related_name='photos',
    )
    collections = models.ManyToManyField(
        Collection,
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
