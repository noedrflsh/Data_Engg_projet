from django.contrib import admin
from .models import DimMovie, DimGenre, DimUser, FactRating, FactTag

@admin.register(DimMovie)
class DimMovieAdmin(admin.ModelAdmin):
    list_display = ('movie_id', 'title', 'release_year')
    search_fields = ('title',)
    list_filter = ('release_year',)

@admin.register(DimGenre)
class DimGenreAdmin(admin.ModelAdmin):
    list_display = ('genre_id', 'genre_name')

admin.site.register(DimUser)
admin.site.register(FactRating)
admin.site.register(FactTag)
