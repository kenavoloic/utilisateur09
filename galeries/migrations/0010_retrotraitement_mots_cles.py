from django.db import migrations


def extraire_mots_cles_photos_existantes(apps, schema_editor):
    import pyexiv2

    # Modèles réels (pas les historiques) pour bénéficier de Tag.save()
    # qui génère le slug automatiquement.
    from galeries.models import Photo, Tag

    for photo in Photo.objects.exclude(image=""):
        try:
            with pyexiv2.Image(photo.image.path) as img:
                xmp = img.read_xmp()
        except Exception:
            continue

        for mot_cle in xmp.get("Xmp.dc.subject", []):
            mot_cle = mot_cle.strip()
            if not mot_cle:
                continue
            tag, _ = Tag.objects.get_or_create(nom=mot_cle)
            photo.tags.add(tag)


class Migration(migrations.Migration):

    dependencies = [
        ("galeries", "0009_retrotraitement_focale"),
    ]

    operations = [
        migrations.RunPython(
            extraire_mots_cles_photos_existantes, migrations.RunPython.noop
        ),
    ]
