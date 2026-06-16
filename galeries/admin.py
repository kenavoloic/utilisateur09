from django import forms
from django.contrib import admin, messages
from django.forms.widgets import ClearableFileInput
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from .models import Photo
from utilisateurs.models import Utilisateur

class MultipleFileInput(ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
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


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):

    #list_display    = ('vignette', 'nom_fichier', 'appareil', 'date_prise_de_vue', 'largeur', 'hauteur', 'taille_mo')

    liste_roles_contributeurs = {Utilisateur.Role.ASSISTANT, Utilisateur.Role.PHOTOGRAPHE}
    actions = ['definir_auteur']

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
            "fields": ('titre', 'description'),
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

    def has_add_permission(self, request):
        return request.user.role in self.liste_roles_contributeurs

    def has_change_permission(self, request, obj=None):
        return request.user.role in self.liste_roles_contributeurs

    def has_delete_permission(self, request, obj=None):
        return request.user.role in self.liste_roles_contributeurs

    @admin.action(description="Définir l'auteur des photos sélectionnées")
    def definir_auteur(self, request, queryset):
        request.session['photos_ids'] = list(queryset.values_list('pk', flat=True))
        return HttpResponseRedirect('definir-auteur/')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('batch-upload/', self.admin_site.admin_view(self.batch_upload_view), name='galeries_photo_batch_upload'),
            path('definir-auteur/', self.admin_site.admin_view(self.definir_auteur_view), name='galeries_photo_definir_auteur'),
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
