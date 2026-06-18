import datetime
from collections import OrderedDict
from urllib.parse import urlencode

from adminsortable2.admin import SortableAdminMixin, SortableInlineAdminMixin
from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.forms.widgets import ClearableFileInput
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _
from rangefilter.filters import AdminSplitDateTime, DateRangeFilter, DateTimeRangeFilter

from .models import Photo, Galerie, Collection, Tag, calculer_hash_fichier, ordonner_photos
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


class AjouterTagForm(forms.Form):
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tags existants",
    )
    nouveaux_tags = forms.CharField(
        required=False,
        label="Nouveaux tags",
        help_text="Séparés par des virgules",
    )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("tags") and not cleaned_data.get("nouveaux_tags"):
            raise forms.ValidationError(
                "Sélectionnez au moins un tag existant ou saisissez-en un nouveau."
            )
        return cleaned_data


class WidgetDateHeurePreRemplie(AdminSplitDateTime):
    """Pré-affiche une heure par défaut dans le sous-champ heure tant qu'aucune
    valeur n'a été saisie (le sous-champ date, lui, reste vide)."""

    def __init__(self, heure_par_defaut, attrs=None):
        self.heure_par_defaut = heure_par_defaut
        super().__init__(attrs=attrs)

    def decompress(self, value):
        date_partie, heure_partie = super().decompress(value)
        if heure_partie is None:
            heure_partie = self.heure_par_defaut
        return [date_partie, heure_partie]


class ChampDateHeurePreRempli(forms.SplitDateTimeField):
    """Si seule la date est renseignée, applique l'heure par défaut plutôt que
    d'exiger une saisie ; si la date est vide, le champ est simplement ignoré
    (filtre ouvert d'un seul côté), même si l'heure pré-remplie est présente."""

    def __init__(self, *args, heure_par_defaut, **kwargs):
        self.heure_par_defaut = heure_par_defaut
        super().__init__(*args, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return None
        date_valeur, heure_valeur = data_list
        if date_valeur in self.empty_values:
            return None
        if heure_valeur in self.empty_values:
            heure_valeur = self.heure_par_defaut
        return make_aware(datetime.datetime.combine(date_valeur, heure_valeur))


class FiltrePlageDateHeure(DateTimeRangeFilter):
    """DateTimeRangeFilter dont les champs heure affichent 00:00:00/23:59:59
    par défaut, pour filtrer une journée entière sans saisie manuelle de l'heure."""

    def _get_form_fields(self):
        return OrderedDict(
            (
                (
                    self.lookup_kwarg_gte,
                    ChampDateHeurePreRempli(
                        heure_par_defaut=datetime.time(0, 0, 0),
                        label="",
                        widget=WidgetDateHeurePreRemplie(
                            heure_par_defaut=datetime.time(0, 0, 0),
                            attrs={"placeholder": _("From date")},
                        ),
                        localize=True,
                        required=False,
                        initial=self.default_gte,
                    ),
                ),
                (
                    self.lookup_kwarg_lte,
                    ChampDateHeurePreRempli(
                        heure_par_defaut=datetime.time(23, 59, 59),
                        label="",
                        widget=WidgetDateHeurePreRemplie(
                            heure_par_defaut=datetime.time(23, 59, 59),
                            attrs={"placeholder": _("To date")},
                        ),
                        localize=True,
                        required=False,
                        initial=self.default_lte,
                    ),
                ),
            )
        )


class AttributionFilter(admin.SimpleListFilter):
    title = "Attribution"
    parameter_name = "attribution"

    def lookups(self, request, model_admin):
        return (
            ("galerie", "Dans une galerie"),
            ("collection", "Dans une collection"),
            ("aucune", "Sans attribution"),
        )

    def queryset(self, request, queryset):
        if self.value() == "galerie":
            return queryset.filter(galeries__isnull=False).distinct()
        if self.value() == "collection":
            return queryset.filter(collections__isnull=False).distinct()
        if self.value() == "aucune":
            return queryset.filter(galeries__isnull=True, collections__isnull=True)
        return queryset


class FocaleFilter(admin.SimpleListFilter):
    title = "Focale"
    parameter_name = "focale"

    def lookups(self, request, model_admin):
        tags_focale = Tag.objects.filter(nom__regex=r'^[0-9]+mm$')
        focales = sorted(tags_focale, key=lambda tag: int(tag.nom.removesuffix('mm')))
        return [(tag.slug, tag.nom) for tag in focales]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(tags__slug=self.value())
        return queryset


@admin.register(Photo)
class PhotoAdmin(RolesContributeursMixin, admin.ModelAdmin):

    #list_display    = ('vignette', 'nom_fichier', 'appareil', 'date_prise_de_vue', 'largeur', 'hauteur', 'taille_mo')

    actions = ['definir_auteur', 'ajouter_a_galerie', 'ajouter_a_collection', 'ajouter_un_tag']
    filter_horizontal = ('galeries', 'collections', 'tags')

    list_display    = ('vignette', 'nom_fichier', 'appareil', 'date_prise_de_vue', 'taille_mo')
    list_filter     = (AttributionFilter, 'appareil', FocaleFilter, ('date_prise_de_vue', FiltrePlageDateHeure), ('date_chargement', DateRangeFilter))
    search_fields   = ('nom_fichier', 'titre', 'description', 'appareil', 'objectif')

    PARAMS_FILTRE_DATE = (
        'date_prise_de_vue__range__gte_0', 'date_prise_de_vue__range__gte_1',
        'date_prise_de_vue__range__lte_0', 'date_prise_de_vue__range__lte_1',
    )
    CLE_SESSION_FILTRE_DATE = 'photo_admin_dernier_filtre_date'
    CLE_SESSION_DERNIER_UPLOAD = 'photo_admin_dernier_upload'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if getattr(request, '_filtrer_photos_recemment_uploadees', False):
            return qs.filter(pk__in=request.session[self.CLE_SESSION_DERNIER_UPLOAD])
        return qs

    def changelist_view(self, request, extra_context=None):
        if 'voir_toutes_photos' in request.GET:
            request.session.pop(self.CLE_SESSION_DERNIER_UPLOAD, None)
            return HttpResponseRedirect(request.path)

        if 'vider_filtre_date' in request.GET:
            request.session.pop(self.CLE_SESSION_FILTRE_DATE, None)
            return HttpResponseRedirect(request.path)

        if (
            request.GET.get('recemment_uploadees')
            and self.CLE_SESSION_DERNIER_UPLOAD in request.session
        ):
            nb = len(request.session[self.CLE_SESSION_DERNIER_UPLOAD])
            messages.info(
                request,
                format_html(
                    'Affichage des {} photo(s) récemment uploadée(s). '
                    '<a href="{}?voir_toutes_photos=1">Voir toutes les photos</a>',
                    nb,
                    request.path,
                ),
            )
            # Django rejette tout paramètre GET qui ne correspond pas à un
            # filtre/champ réel : on le retire avant de lui passer la main,
            # et on note l'info ailleurs pour que get_queryset() la lise.
            request._filtrer_photos_recemment_uploadees = True
            request.GET = request.GET.copy()
            del request.GET['recemment_uploadees']

        filtre_present = any(p in request.GET for p in self.PARAMS_FILTRE_DATE)

        if filtre_present:
            request.session[self.CLE_SESSION_FILTRE_DATE] = {
                p: request.GET[p] for p in self.PARAMS_FILTRE_DATE if p in request.GET
            }
            messages.info(
                request,
                format_html(
                    'Filtre de date mémorisé, il sera réappliqué automatiquement '
                    'à votre prochaine visite. <a href="{}?vider_filtre_date=1">Oublier ce filtre</a>',
                    request.path,
                ),
            )
        elif (
            request.method == 'GET'
            and not request.GET
            and self.CLE_SESSION_FILTRE_DATE in request.session
        ):
            query_string = urlencode(request.session[self.CLE_SESSION_FILTRE_DATE])
            messages.info(
                request,
                format_html(
                    'Le dernier filtre de date utilisé a été réappliqué automatiquement. '
                    '<a href="{}?vider_filtre_date=1">Réinitialiser le filtre</a>',
                    request.path,
                ),
            )
            return HttpResponseRedirect(f'{request.path}?{query_string}')

        return super().changelist_view(request, extra_context=extra_context)

    readonly_fields = (
        'vignette', 'nom_fichier', 'taille_mo', 'largeur', 'hauteur',
        'appareil', 'objectif', 'ouverture', 'vitesse', 'iso',
        'date_prise_de_vue', 'latitude', 'longitude', 'tags_affiches',
        'date_chargement',
    )

    fieldsets = (
        ("Fichier", {
            "fields": ('vignette', 'image', 'nom_fichier', 'date_chargement', 'taille_mo', 'largeur', 'hauteur', 'auteur_nom', 'auteur_prenom', 'auteur_email'),
        }),
        ("Contenu", {
            "fields": ('titre', 'description', 'est_couverture', 'tags_affiches'),
        }),
        ("Galeries", {
            "fields": ('galeries', 'collections', 'tags'),
            "classes": ('collapse',),            
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

    @admin.display(description='Tags')
    def tags_affiches(self, obj):
        tags = obj.tags.all() if obj.pk else []
        if not tags:
            return '—'
        return format_html_join(
            ' ',
            '<span style="background:#eee; border-radius:10px; padding:2px 8px; font-size:12px;">{}</span>',
            ((tag.nom,) for tag in tags),
        )

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

    @admin.action(description="Ajouter un tag")
    def ajouter_un_tag(self, request, queryset):
        request.session['photos_ids'] = list(queryset.values_list('pk', flat=True))
        return HttpResponseRedirect('ajouter-tag/')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('batch-upload/', self.admin_site.admin_view(self.batch_upload_view), name='galeries_photo_batch_upload'),
            path('definir-auteur/', self.admin_site.admin_view(self.definir_auteur_view), name='galeries_photo_definir_auteur'),
            path('ajouter-galerie/', self.admin_site.admin_view(self.ajouter_a_galerie_view), name='galeries_photo_ajouter_galerie'),
            path('ajouter-collection/', self.admin_site.admin_view(self.ajouter_a_collection_view), name='galeries_photo_ajouter_collection'),
            path('ajouter-tag/', self.admin_site.admin_view(self.ajouter_un_tag_view), name='galeries_photo_ajouter_tag'),
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

    def ajouter_un_tag_view(self, request):
        ids = request.session.get('photos_ids', [])
        queryset = Photo.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = AjouterTagForm(request.POST)
            if form.is_valid():
                tags = list(form.cleaned_data['tags'])
                noms_nouveaux_tags = [
                    nom.strip()
                    for nom in form.cleaned_data['nouveaux_tags'].split(',')
                    if nom.strip()
                ]
                for nom in noms_nouveaux_tags:
                    tag, _cree = Tag.objects.get_or_create(nom=nom)
                    tags.append(tag)

                for tag in tags:
                    tag.photos.add(*queryset)

                del request.session['photos_ids']
                noms_tags = ", ".join(f"« {tag.nom} »" for tag in tags)
                messages.success(
                    request,
                    f"{queryset.count()} photo(s) taguée(s) avec {noms_tags}.",
                )
                return HttpResponseRedirect('../')
        else:
            form = AjouterTagForm()

        context = {
            **self.admin_site.each_context(request),
            'title': "Ajouter un tag",
            'form': form,
            'queryset': queryset,
            'opts': self.model._meta,
        }
        return render(request, 'admin/galeries/photo/ajouter_tag.html', context)

    def batch_upload_view(self, request):
        if not self.has_add_permission(request):
            messages.error(request, "Vous n'avez pas la permission d'uploader des photos.")
            return HttpResponseRedirect('../')

        if request.method == 'POST':
            form = BatchUploadForm(request.POST, request.FILES)
            if form.is_valid():
                fichiers = request.FILES.getlist('images')
                pks_nouvelles_photos = []
                nb_doublons = 0
                for fichier in fichiers:
                    if Photo.objects.filter(
                        hash_fichier=calculer_hash_fichier(fichier)
                    ).exists():
                        nb_doublons += 1
                        continue
                    photo = Photo()
                    photo.image.save(fichier.name, fichier, save=True)
                    pks_nouvelles_photos.append(photo.pk)
                message = f"{len(pks_nouvelles_photos)} photo(s) uploadée(s) avec succès."
                if nb_doublons:
                    message += f" {nb_doublons} photo(s) déjà existante(s) ignorée(s)."
                messages.success(request, message)
                if pks_nouvelles_photos:
                    request.session[self.CLE_SESSION_DERNIER_UPLOAD] = pks_nouvelles_photos
                    return HttpResponseRedirect('../?recemment_uploadees=1')
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
    list_display = ('nom', 'slug', 'nombre_photos_admin')
    search_fields = ('nom',)
    readonly_fields = ('slug',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            nombre_photos_annote=Count('photos', distinct=True),
        )

    @admin.display(description='Photos', ordering='nombre_photos_annote')
    def nombre_photos_admin(self, obj):
        url = reverse('admin:galeries_photo_changelist') + f'?tags__id__exact={obj.pk}'
        return format_html('<a href="{}">{}</a>', url, obj.nombre_photos_annote)
