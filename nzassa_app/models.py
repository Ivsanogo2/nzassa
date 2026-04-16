from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Traduction(models.Model):
    LANGUES_CHOIX = [
        ("FR", "Francais"),
        ("BAO", "Baoule"),
        ("DIO", "Dioula"),
        ("LSI", "Langue des Signes"),
    ]

    mot_origine = models.CharField(max_length=200, verbose_name="Mot ou phrase")
    langue_cible = models.CharField(max_length=10, choices=LANGUES_CHOIX)
    resultat_traduction = models.TextField()
    video_signe = models.FileField(upload_to="videos/", null=True, blank=True)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["mot_origine"]

    def __str__(self):
        return f"{self.mot_origine} en {self.get_langue_cible_display()}"


class Language(models.Model):
    CATEGORY_CHOICES = [
        ("spoken", "Langue orale"),
        ("sign", "Langue des signes"),
    ]

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="spoken")
    difficulty = models.CharField(max_length=50, blank=True)
    is_premium = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    LEVEL_CHOICES = [
        ("beginner", "Debutant"),
        ("intermediate", "Intermediaire"),
        ("advanced", "Avance"),
    ]

    GOAL_CHOICES = [
        ("culture", "Culture"),
        ("school", "Etudes"),
        ("travel", "Voyage"),
        ("family", "Famille et diaspora"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    selected_language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learners",
    )
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default="beginner")
    goal = models.CharField(max_length=20, choices=GOAL_CHOICES, default="culture")
    is_premium = models.BooleanField(default=False)
    total_xp = models.PositiveIntegerField(default=0)
    streak_days = models.PositiveIntegerField(default=0)
    last_learning_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profil de {self.user.username}"


class Course(models.Model):
    FOCUS_CHOICES = [
        ("language", "Langue"),
        ("culture", "Culture"),
        ("sign", "Langue des signes"),
        ("vr", "Immersion VR"),
        ("ai", "Pratique IA"),
    ]

    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    short_description = models.CharField(max_length=240)
    description = models.TextField()
    focus = models.CharField(max_length=20, choices=FOCUS_CHOICES, default="language")
    level = models.CharField(max_length=40, default="Debutant")
    estimated_minutes = models.PositiveIntegerField(default=30)
    xp_reward = models.PositiveIntegerField(default=120)
    is_premium = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["language__name", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def lesson_count(self):
        return Lesson.objects.filter(module__course=self).count()


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=180)
    order = models.PositiveIntegerField(default=1)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["course", "order", "title"]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    LESSON_TYPES = [
        ("vocabulary", "Vocabulaire"),
        ("conversation", "Conversation"),
        ("culture", "Culture"),
        ("sign", "Signes"),
        ("vr", "VR"),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=180)
    order = models.PositiveIntegerField(default=1)
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, default="vocabulary")
    content = models.TextField()
    culture_note = models.TextField(blank=True)
    key_phrase = models.CharField(max_length=255, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=10)
    xp_reward = models.PositiveIntegerField(default=30)

    class Meta:
        ordering = ["module", "order", "title"]

    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="questions")
    prompt = models.CharField(max_length=255)
    choice_a = models.CharField(max_length=255)
    choice_b = models.CharField(max_length=255)
    choice_c = models.CharField(max_length=255)
    choice_d = models.CharField(max_length=255)
    correct_choice = models.CharField(max_length=1, default="A")
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["lesson", "id"]

    def __str__(self):
        return self.prompt


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ("active", "Actif"),
        ("completed", "Termine"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    progress_percent = models.PositiveIntegerField(default=0)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "course")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.course.title}"


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress_entries")
    completed = models.BooleanField(default=False)
    score = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "lesson")
        ordering = ["lesson__module__course", "lesson__order"]

    def __str__(self):
        return f"{self.user.username} - {self.lesson.title}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Tentative de {self.user.username} sur {self.lesson.title}"


class Badge(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.CharField(max_length=255)
    xp_threshold = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=20, default="star")

    class Meta:
        ordering = ["xp_threshold", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="users")
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "badge")
        ordering = ["badge__xp_threshold", "badge__name"]

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


class CulturalExperience(models.Model):
    EXPERIENCE_TYPES = [
        ("vr", "VR"),
        ("sign", "Signes"),
        ("ai", "IA"),
        ("culture", "Culture"),
    ]

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    experience_type = models.CharField(max_length=20, choices=EXPERIENCE_TYPES)
    description = models.TextField()
    cta_label = models.CharField(max_length=80, default="Explorer")
    cta_url = models.CharField(max_length=255, blank=True)
    is_premium = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
