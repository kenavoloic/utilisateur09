from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Collection, Galerie, Photo


def _ajouter(cible, pks):
    ordre = list(cible.ordre_photos)
    nouveaux = [pk for pk in pks if pk not in ordre]
    if not nouveaux:
        return
    cible.ordre_photos = ordre + nouveaux
    cible.save(update_fields=["ordre_photos"])


def _retirer(cible, pks):
    pks = set(pks)
    ordre = [pk for pk in cible.ordre_photos if pk not in pks]
    if len(ordre) == len(cible.ordre_photos):
        return
    cible.ordre_photos = ordre
    cible.save(update_fields=["ordre_photos"])


def _maj_ordre_photos(instance, action, reverse, pk_set, modele_cible):
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    if not reverse:
        # instance est une Photo ; pk_set contient les pk de Galerie/Collection visées
        if action == "post_clear":
            return
        for cible in modele_cible.objects.filter(pk__in=pk_set):
            if action == "post_add":
                _ajouter(cible, [instance.pk])
            else:
                _retirer(cible, [instance.pk])
    else:
        # instance est une Galerie/Collection ; pk_set contient les pk de Photo visées
        if action == "post_clear":
            instance.ordre_photos = []
            instance.save(update_fields=["ordre_photos"])
        elif action == "post_add":
            _ajouter(instance, pk_set)
        else:
            _retirer(instance, pk_set)


@receiver(m2m_changed, sender=Photo.galeries.through)
def maj_ordre_photos_galerie(sender, instance, action, reverse, pk_set, **kwargs):
    _maj_ordre_photos(instance, action, reverse, pk_set, Galerie)


@receiver(m2m_changed, sender=Photo.collections.through)
def maj_ordre_photos_collection(sender, instance, action, reverse, pk_set, **kwargs):
    _maj_ordre_photos(instance, action, reverse, pk_set, Collection)
