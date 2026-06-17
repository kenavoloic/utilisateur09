from django.urls import include, path
from . import views

app_name = 'accueil'

urlpatterns = [
    path('', views.index, name='index'),
    path('contact/', views.contact, name='contact'),
   # path('xyz', views.xyz),

]
