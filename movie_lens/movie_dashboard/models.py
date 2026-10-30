from django.db import models

class DimMovie(models.Model):
    movie_id = models.IntegerField(primary_key=True, db_column='movie_id')
    title = models.TextField(db_column='title')
    release_year = models.IntegerField(null=True, blank=True, db_column='release_year')

    class Meta:
        managed = False
        db_table = 'dim_movies'


class DimGenre(models.Model):
    genre_id = models.IntegerField(primary_key=True, db_column='genre_id')
    genre_name = models.CharField(max_length=100, db_column='genre_name')

    class Meta:
        managed = False
        db_table = 'dim_genres'


class BridgeMovieGenre(models.Model):
    # For many-to-many bridge tables without a single surrogate PK,
    # link them as standard foreign keys.
    movie = models.ForeignKey(DimMovie, on_delete=models.DO_NOTHING, db_column='movie_id', primary_key=True)
    genre = models.ForeignKey(DimGenre, on_delete=models.DO_NOTHING, db_column='genre_id')

    class Meta:
        managed = False
        db_table = 'bridge_movie_genre'
        unique_together = (('movie', 'genre'),)


class DimUser(models.Model):
    user_id = models.IntegerField(primary_key=True, db_column='user_id')

    class Meta:
        managed = False
        db_table = 'dim_users'


class DimDate(models.Model):
    date_key = models.IntegerField(primary_key=True, db_column='date_key') # YYYYMMDD
    full_date = models.DateField(db_column='full_date')
    year = models.IntegerField(db_column='year')
    quarter = models.IntegerField(db_column='quarter')
    month = models.IntegerField(db_column='month')

    class Meta:
        managed = False
        db_table = 'dim_date'


class FactRating(models.Model):
    rating_id = models.BigAutoField(primary_key=True, db_column='rating_id')
    user = models.ForeignKey(DimUser, on_delete=models.DO_NOTHING, db_column='user_id')
    movie = models.ForeignKey(DimMovie, on_delete=models.DO_NOTHING, db_column='movie_id')
    date_key = models.ForeignKey(DimDate, on_delete=models.DO_NOTHING, db_column='date_key', to_field='date_key')
    rating = models.FloatField(db_column='rating')

    class Meta:
        managed = False
        db_table = 'fact_ratings'


class FactTag(models.Model):
    tag_id = models.BigAutoField(primary_key=True, db_column='tag_id')
    user = models.ForeignKey(DimUser, on_delete=models.DO_NOTHING, db_column='user_id')
    movie = models.ForeignKey(DimMovie, on_delete=models.DO_NOTHING, db_column='movie_id')
    date_key = models.ForeignKey(DimDate, on_delete=models.DO_NOTHING, db_column='date_key', to_field='date_key')
    tag = models.TextField(db_column='tag')

    class Meta:
        managed = False
        db_table = 'fact_tags'

class DimGenomeTag(models.Model):
    tag_id = models.IntegerField(primary_key=True,
	db_column='tag_id')
    tag = models.CharField(max_length=255, db_column='tag')

    class Meta:
        managed = False
        db_table = 'dim_genome_tags'

    def __str__(self):
        return self.tag

class FactGenomeScore(models.Model):
	# 	# In unmanaged models with composite
	# primary keys in PostgreSQL,
	# # we mark the first FK as primary_key to
	# satisfy Django ORM
    movie = models.ForeignKey(DimMovie,
        on_delete=models.DO_NOTHING,
        db_column='movie_id', primary_key=True)
    tag = models.ForeignKey(DimGenomeTag,
        on_delete=models.DO_NOTHING,
        db_column='tag_id')
    relevance = models.FloatField(db_column='relevance')

    class Meta:
        managed = False
        db_table = 'fact_genome_scores'
        unique_together = (('movie', 'tag'),)

    def __str__(self):
        return f"{self.movie_id} - {self.tag_id}: {self.relevance}"
