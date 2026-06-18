from adminsortable2.admin import SortableAdminMixin, SortableInlineAdminMixin
from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.forms.widgets import ClearableFileInput
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Photo, Galerie, Collection, Tag, ordonner_photos
from utilisateurs.models import Utilisateur

# création d'un mixin pour éviter les répétitions de code
class RolesContributeursMixin:
    """rôles pouvant charger des images, le photographe ou ses assistants"""
    liste_roles_contributeurs = {Utilisateur.Role.ASSISTANT, Utilisateur.Role.PHOTOGRAPHE}

    def has_add_permission(self, request):
        return request.user.role in self.liste_roles_contributeurs

    def has_change_permission(self, request, obj=None):
        return request.user.role in self.liste_roles_contributeurs

    def has_delete_permission(self, request, obj=None):
        return request.user.role in self.liste_roles_contributeurs

    
class MultipleFileInput(ClearableFileInput):
    """permet la sélection de plusieurs images en une fois et rend donc possible le chargement par batch"""
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """seuls les jpg et les jpegs sont permis, pour l'instant"""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': '.jpg,.jpeg'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(d, initial) for d in data]
        return single_clean(data, initial)


class BatchUploadForm(forms.Form):
    images = MultipleFileField(label="Photos (JPG/JPEG)")


class DefinirAuteurForm(forms.Form):
    auteur_nom    = forms.CharField(max_length=255, required=False, label="Nom")
    auteur_prenom = forms.CharField(max_length=255, required=False, label="Prénom")
    auteur_email  = forms.EmailField(max_length=255, required=False, label="Email")


class AjouterGalerieForm(forms.Form):
    galerie = forms.ModelChoiceField(queryset=Galerie.objects.all(), label="Galerie")


class AjouterCollectionForm(forms.Form):
    collection = forms.ModelChoiceField(queryset=Collection.objects.all(), label="Collection")


@admin.register(Photo)
class PhotoAdmin(RolesContributeursMixin, admin.ModelAdmin):

    #list_display    = ('vignette', 'nom_fichier', 'appareil', 'date_prise_de_vue', 'largeur', 'hauteur', 'taille_mo')

    actions = ['definir_auteur', 'ajouter_a_galerie', 'ajouter_a_collection']
    filter_horizontal = ('galeries', 'collections', 'tags')

    list_display    = ('vignette', 'nom_fichier', 'appareil', 'date_prise_de_vue', 'taille_mo')
    list_filter     = ('appareil', 'date_prise_de_vue')
    search_fields   = ('nom_fichier', 'titre', 'description', 'appareil', 'objectif')
    readonly_fields = (
        'vignette', 'nom_fichier', 'taille_mo', 'largeur', 'hauteur',
        'appareil', 'objectif', 'ouverture', 'vitesse', 'iso',
        'date_prise_de_vue', 'latitude', 'longitude',
    )

    fieldsets = (
        ("Fichier", {
            "fields": ('vignette', 'image', 'nom_fichier', 'taille_mo', 'largeur', 'hauteur', 'auteur_nom', 'auteur_prenom', 'auteur_email'),
        }),
        ("Contenu", {
            "fields": ('titre', 'description', 'est_couverture'),
        }),
        ("Galeries", {
            "fields": ('galeries', 'collections', 'tags'),
        }),
        ("Prise de vue", {
            "fields": ('date_prise_de_vue', 'appareil', 'objectif', 'ouverture', 'vitesse', 'iso'),
            "classes": ('collapse',),
        }),
        ("GPS", {
            "fields": ('latitude', 'longitude'),
            "classes": ('collapse',),
        }),
    )

    change_list_template = 'admin/galeries/photo/change_list.html'

    @admin.display(description='Taille')
    def taille_mo(self, obj):
        if obj.taille is None:
            return '-'
        return f"{round(obj.taille / (1024 * 1024), 2)} Mo"

    @admin.display(description='Vignette')
    def vignette(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:60px; border-radius:4px;">', obj.image.url)
        return '-'

    @admin.action(description="Définir l'auteur des photos sélectionnées")
    def definir_auteur(self, request, queryset):
        request.session['photos_ids'] = list(queryset.values_list('pk', flat=True))
        return HttpResponseRedirect('definir-auteur/')

    @admin.action(description="Ajouter à une galerie")
    def ajouter_a_galerie(self, request, queryset):
        request.session['photos_ids'] = list(queryset.values_list('pk', flat=True))
        return HttpResponseRedirect('ajouter-galerie/')

    @admin.action(description="Ajouter à une collection")
    def ajouter_a_collection(self, request, queryset):
        request.session['photos_ids'] = list(queryset.values_list('pk', flat=True))
        return HttpResponseRedirect('ajouter-collection/')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('batch-upload/', self.admin_site.admin_view(self.batch_upload_view), name='galeries_photo_batch_upload'),
            path('definir-auteur/', self.admin_site.admin_view(self.definir_auteur_view), name='galeries_photo_definir_auteur'),
            path('ajouter-galerie/', self.admin_site.admin_view(self.ajouter_a_galerie_view), name='galeries_photo_ajouter_galerie'),
            path('ajouter-collection/', self.admin_site.admin_view(self.ajouter_a_collection_view), name='galeries_photo_ajouter_collection'),
        ]
        return custom_urls + urls

    def definir_auteur_view(self, request):
        ids = request.session.get('photos_ids', [])
        queryset = Photo.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = DefinirAuteurForm(request.POST)
            if form.is_valid():
                queryset.update(
                    auteur_nom=form.cleaned_data['auteur_nom'],
                    auteur_prenom=form.cleaned_data['auteur_prenom'],
                    auteur_email=form.cleaned_data['auteur_email'],
                )
                del request.session['photos_ids']
                messages.success(request, f"Auteur mis à jour pour {queryset.count()} photo(s).")
                return HttpResponseRedirect('../')
        else:
            form = DefinirAuteurForm()

        context = {
            **self.admin_site.each_context(request),
            'title': "Définir l'auteur",
            'form': form,
            'queryset': queryset,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/photo/definir_auteur.html', context)

    def ajouter_a_galerie_view(self, request):
        ids = request.session.get('photos_ids', [])
        queryset = Photo.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = AjouterGalerieForm(request.POST)
            if form.is_valid():
                galerie = form.cleaned_data['galerie']
                galerie.photos.add(*queryset)
                del request.session['photos_ids']
                messages.success(request, f"{queryset.count()} photo(s) ajoutée(s) à la galerie « {galerie} ».")
                return HttpResponseRedirect('../')
        else:
            form = AjouterGalerieForm()

        context = {
            **self.admin_site.each_context(request),
            'title': "Ajouter à une galerie",
            'form': form,
            'queryset': queryset,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/photo/ajouter_galerie.html', context)

    def ajouter_a_collection_view(self, request):
        ids = request.session.get('photos_ids', [])
        queryset = Photo.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = AjouterCollectionForm(request.POST)
            if form.is_valid():
                collection = form.cleaned_data['collection']
                collection.photos.add(*queryset)
                del request.session['photos_ids']
                messages.success(request, f"{queryset.count()} photo(s) ajoutée(s) à la collection « {collection} ».")
                return HttpResponseRedirect('../')
        else:
            form = AjouterCollectionForm()

        context = {
            **self.admin_site.each_context(request),
            'title': "Ajouter à une collection",
            'form': form,
            'queryset': queryset,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/photo/ajouter_collection.html', context)

    def batch_upload_view(self, request):
        if not self.has_add_permission(request):
            messages.error(request, "Vous n'avez pas la permission d'uploader des photos.")
            return HttpResponseRedirect('../')

        if request.method == 'POST':
            form = BatchUploadForm(request.POST, request.FILES)
            if form.is_valid():
                fichiers = request.FILES.getlist('images')
                nb_succes = 0
                for fichier in fichiers:
                    photo = Photo()
                    photo.image.save(fichier.name, fichier, save=True)
                    nb_succes += 1
                messages.success(request, f"{nb_succes} photo(s) uploadée(s) avec succès.")
                return HttpResponseRedirect('../')
        else:
            form = BatchUploadForm()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Upload en lot',
            'form': form,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/photo/batch_upload.html', context)


class OrdonnerPhotosAdminMixin:
    """Vue d'administration pour réordonner par glisser-déposer les photos
    d'une galerie ou d'une collection, en réécrivant le tuple `ordre_photos`."""

    def get_photos_a_ordonner(self, obj):
        raise NotImplementedError

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/ordonner-photos/',
                self.admin_site.admin_view(self.ordonner_photos_view),
                name=f'{self.model._meta.app_label}_{self.model._meta.model_name}_ordonner_photos',
            ),
        ]
        return custom_urls + urls

    def ordonner_photos_view(self, request, object_id):
        from django.shortcuts import get_object_or_404

        obj = get_object_or_404(self.model, pk=object_id)
        photos = ordonner_photos(self.get_photos_a_ordonner(obj), obj.ordre_photos)

        if request.method == 'POST':
            ordre = [int(pk) for pk in request.POST.getlist('ordre')]
            obj.ordre_photos = ordre
            obj.save(update_fields=['ordre_photos'])
            messages.success(request, "Ordre des photos mis à jour.")
            return HttpResponseRedirect(request.path)

        context = {
            **self.admin_site.each_context(request),
            'title': f"Ordre des photos — {obj}",
            'objet': obj,
            'photos': photos,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/ordonner_photos.html', context)

    @admin.display(description='Photos')
    def lien_ordre_photos(self, obj):
        url = reverse(
            f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_ordonner_photos',
            args=[obj.pk],
        )
        return format_html('<a href="{}">🔄 Ordonner les photos</a>', url)


class CollectionInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Collection
    extra = 1
    fields = ('nom',)


@admin.register(Galerie)
class GalerieAdmin(OrdonnerPhotosAdminMixin, RolesContributeursMixin, SortableAdminMixin, admin.ModelAdmin):
    list_display = ('nom', 'slug', 'est_publique', 'masonry_layout_manuel', 'nombre_collections_admin', 'nombre_total_photos_admin', 'lien_ordre_photos')
    list_filter = ('est_publique',)
    search_fields = ('nom', 'description')
    readonly_fields = ('slug',)
    inlines = [CollectionInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            nombre_collections_annote=Count('collections', distinct=True),
        )

    @admin.display(description='Collections', ordering='nombre_collections_annote')
    def nombre_collections_admin(self, obj):
        return obj.nombre_collections_annote

    @admin.display(description='Photos (total)')
    def nombre_total_photos_admin(self, obj):
        return obj.nombre_total_photos()

    def get_photos_a_ordonner(self, obj):
        return obj.photos.exclude(collections__galerie=obj).distinct()


@admin.register(Collection)
class CollectionAdmin(OrdonnerPhotosAdminMixin, RolesContributeursMixin, SortableAdminMixin, admin.ModelAdmin):
    list_display = ('nom', 'slug', 'galerie', 'masonry_layout_manuel', 'nombre_photos_admin', 'lien_ordre_photos')
    list_filter = ('galerie',)
    readonly_fields = ('slug',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            nombre_photos_annote=Count('photos', distinct=True),
        )

    @admin.display(description='Photos', ordering='nombre_photos_annote')
    def nombre_photos_admin(self, obj):
        return obj.nombre_photos_annote

    def get_photos_a_ordonner(self, obj):
        return obj.photos.all()


@admin.register(Tag)
class TagAdmin(RolesContributeursMixin, admin.ModelAdmin):
    list_display = ('nom', 'slug')
    search_fields = ('nom',)
    readonly_fields = ('slug',)
