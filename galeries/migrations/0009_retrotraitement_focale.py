from fractions import Fraction

from django.db import migrations


def extraire_focale_photos_existantes(apps, schema_editor):
    import pyexiv2

    # Modèles réels (pas les historiques) pour bénéficier de Tag.save()
    # qui génère le slug automatiquement.
    from galeries.models import Photo, Tag

    for photo in Photo.objects.exclude(image=""):
        try:
            with pyexiv2.Image(photo.image.path) as img:
                exif = img.read_exif()
        except Exception:
            continue

        focale = exif.get("Exif.Photo.FocalLength")
        if not focale:
            continue

        try:
            nom_tag = f"{round(float(Fraction(focale)))}mm"
        except (ValueError, ZeroDivisionError):
            continue

        tag_focale, _ = Tag.objects.get_or_create(nom=nom_tag)
        photo.tags.add(tag_focale)


class Migration(migrations.Migration):

    dependencies = [
        ("galeries", "0008_photo_date_chargement"),
    ]

    operations = [
        migrations.RunPython(
            extraire_focale_photos_existantes, migrations.RunPython.noop
        ),
    ]
