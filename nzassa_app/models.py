from django.conf import settings
from django.db import models
from django.utils.text import slugify
from urllib.parse import parse_qs, urlparse


def build_unique_slug(instance, value):
    base_slug = slugify(value) or "contenu"
    slug = base_slug
    suffix = 2
    model_class = instance.__class__

    while model_class.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    return slug


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


class Ethnicity(models.Model):
    name = models.CharField(max_length=140, unique=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ethnicities",
    )
    region = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    traditions = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    map_color = models.CharField(max_length=20, default="#155e4b")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Ethnicities"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Story(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to="stories/", blank=True)
    audio_file = models.FileField(upload_to="stories/audio/", blank=True)
    location = models.CharField(max_length=180, blank=True)
    youtube_url = models.URLField(blank=True)
    ethnicity = models.ForeignKey(
        Ethnicity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stories",
    )
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="liked_stories",
    )
    is_published = models.BooleanField(default=True)
    reading_minutes = models.PositiveIntegerField(default=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def youtube_embed_url(self):
        if not self.youtube_url:
            return ""

        parsed = urlparse(self.youtube_url)
        host = parsed.netloc.lower()
        video_id = ""

        if "youtu.be" in host:
            video_id = parsed.path.strip("/").split("/")[0]
        elif "youtube.com" in host or "youtube-nocookie.com" in host:
            if parsed.path.startswith("/watch"):
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif parsed.path.startswith("/embed/"):
                video_id = parsed.path.split("/embed/", 1)[1].split("/")[0]
            elif parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/shorts/", 1)[1].split("/")[0]

        if not video_id:
            return ""
        return f"https://www.youtube.com/embed/{video_id}"

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.count()


class StoryComment(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="story_comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Commentaire de {self.author.username} sur {self.story.title}"


class Book(models.Model):
    CATEGORY_CHOICES = [
        ("language", "Langue"),
        ("culture", "Culture"),
        ("tale", "Conte"),
        ("history", "Histoire"),
        ("research", "Recherche"),
        ("other", "Autre"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    author_name = models.CharField(max_length=160)
    description = models.TextField()
    cover = models.ImageField(upload_to="library/covers/", blank=True)
    pdf_file = models.FileField(upload_to="library/pdfs/")
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="culture")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_books",
    )
    favorites = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="favorite_books",
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class AudioTrack(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    story = models.ForeignKey(
        Story,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audio_tracks",
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audio_tracks",
    )
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audio_tracks",
    )
    audio_file = models.FileField(upload_to="audio/podcasts/", blank=True)
    external_url = models.URLField(blank=True)
    transcript = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_downloadable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def source_url(self):
        if self.audio_file:
            return self.audio_file.url
        return self.external_url


class ShortVideo(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="short_videos",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="short_videos",
    )
    caption = models.TextField(blank=True)
    video_file = models.FileField(upload_to="shorts/videos/", blank=True)
    video_url = models.URLField(blank=True)
    thumbnail = models.ImageField(upload_to="shorts/thumbnails/", blank=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="liked_short_videos",
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def video_source(self):
        if self.video_file:
            return self.video_file.url
        return self.video_url

    @property
    def like_count(self):
        return self.likes.count()


class LearningGroup(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_groups",
    )
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_learning_groups",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="GroupMembership",
        related_name="learning_groups",
        blank=True,
    )
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    ROLE_CHOICES = [
        ("member", "Membre"),
        ("moderator", "Moderateur"),
        ("owner", "Createur"),
    ]

    group = models.ForeignKey(LearningGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "user")
        ordering = ["group__name", "user__username"]

    def __str__(self):
        return f"{self.user.username} - {self.group.name}"


class FriendConnection(models.Model):
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("accepted", "Accepte"),
        ("blocked", "Bloque"),
    ]

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_sent")
    addressee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_received")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("requester", "addressee")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.requester.username} -> {self.addressee.username} ({self.status})"


class PrivateMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="private_messages_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="private_messages_received")
    body = models.TextField()
    image = models.ImageField(upload_to="discussion/messages/", blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender.username} -> {self.recipient.username}"


class School(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    city = models.CharField(max_length=120, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_schools",
    )
    invite_code = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.name)
        if not self.invite_code:
            self.invite_code = self.slug[:24].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class SchoolMembership(models.Model):
    ROLE_CHOICES = [
        ("student", "Eleve"),
        ("teacher", "Formateur"),
        ("admin", "Administrateur"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="school_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("school", "user")
        ordering = ["school__name", "role", "user__username"]

    def __str__(self):
        return f"{self.user.username} - {self.school.name}"


class Certificate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificates")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="certificates")
    code = models.CharField(max_length=40, unique=True)
    level_label = models.CharField(max_length=80, blank=True)
    score = models.PositiveIntegerField(default=0)
    pdf_file = models.FileField(upload_to="certificates/", blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        course_title = self.course.title if self.course_id else "Nzassa"
        return f"{self.user.username} - {course_title}"


class EducationalGame(models.Model):
    GAME_TYPES = [
        ("memory", "Memory"),
        ("quick_quiz", "Quiz rapide"),
        ("match", "Association mots/images"),
    ]

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    game_type = models.CharField(max_length=30, choices=GAME_TYPES, default="quick_quiz")
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="games",
    )
    payload = models.JSONField(default=dict, blank=True)
    xp_reward = models.PositiveIntegerField(default=25)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "title"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class OfflinePack(models.Model):
    STATUS_CHOICES = [
        ("queued", "A telecharger"),
        ("downloaded", "Telecharge"),
        ("synced", "Synchronise"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="offline_packs")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True, related_name="offline_packs")
    story = models.ForeignKey(Story, on_delete=models.CASCADE, null=True, blank=True, related_name="offline_packs")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, null=True, blank=True, related_name="offline_packs")
    audio = models.ForeignKey(AudioTrack, on_delete=models.CASCADE, null=True, blank=True, related_name="offline_packs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    size_kb = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.course or self.story or self.book or self.audio or "pack"
        return f"{self.user.username} - {target}"


class MicroLessonSubscription(models.Model):
    CHANNEL_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("sms", "SMS"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="micro_lesson_subscriptions")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="whatsapp")
    phone_number = models.CharField(max_length=40)
    language = models.ForeignKey(Language, on_delete=models.SET_NULL, null=True, blank=True, related_name="micro_subscriptions")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "channel", "phone_number")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.channel}"


class MobileMoneyPayment(models.Model):
    PROVIDER_CHOICES = [
        ("mtn", "MTN Mobile Money"),
        ("orange", "Orange Money"),
        ("moov", "Moov Money"),
    ]
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("paid", "Paye"),
        ("failed", "Echoue"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobile_money_payments")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    phone_number = models.CharField(max_length=40)
    amount = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.status}"


class LearningEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="learning_events")
    event_type = models.CharField(max_length=80)
    object_label = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} - {self.object_label}"


class SocialPost(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_posts")
    group = models.ForeignKey(
        LearningGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    content = models.TextField()
    image = models.ImageField(upload_to="discussion/posts/", blank=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="liked_social_posts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post de {self.author.username} - {self.created_at:%Y-%m-%d}"

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.count()


class SocialComment(models.Model):
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Commentaire de {self.author.username}"


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_sent",
    )
    verb = models.CharField(max_length=160)
    target_label = models.CharField(max_length=200, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification pour {self.recipient.username}: {self.verb}"


class CoachConversation(models.Model):
    CHANNEL_CHOICES = [
        ("coach", "Coach IA"),
        ("landing", "Accueil"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coach_conversations",
    )
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="coach")
    selected_language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coach_conversations",
    )
    title = models.CharField(max_length=180, blank=True)
    last_remote_response_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        owner = self.user.username if self.user_id else self.session_key or "anonyme"
        return f"{self.get_channel_display()} - {owner}"


class CoachMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "Utilisateur"),
        ("assistant", "Assistant"),
    ]

    conversation = models.ForeignKey(
        CoachConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    used_openai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.conversation_id} - {self.role}"


class LearnedWord(models.Model):
    conversation = models.ForeignKey(
        CoachConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learned_words",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="learned_words",
    )
    session_key = models.CharField(max_length=80, blank=True, db_index=True)
    owner_key = models.CharField(max_length=80, db_index=True)
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learned_words",
    )
    language_label = models.CharField(max_length=120, blank=True)
    word = models.CharField(max_length=120)
    normalized_word = models.CharField(max_length=120, db_index=True)
    meaning = models.CharField(max_length=255, blank=True)
    example = models.TextField(blank=True)
    pronunciation_hint = models.CharField(max_length=255, blank=True)
    times_seen = models.PositiveIntegerField(default=0)
    times_practiced = models.PositiveIntegerField(default=0)
    times_correct = models.PositiveIntegerField(default=0)
    mastery_level = models.PositiveIntegerField(default=0)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-mastery_level", "-times_seen", "word"]
        unique_together = ("owner_key", "normalized_word", "language_label")

    def __str__(self):
        return f"{self.word} ({self.language_label or 'Sans langue'})"

    @property
    def success_rate(self):
        if not self.times_practiced:
            return 0
        return round((self.times_correct / self.times_practiced) * 100)


class PronunciationAttempt(models.Model):
    learned_word = models.ForeignKey(
        LearnedWord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pronunciation_attempts",
    )
    conversation = models.ForeignKey(
        CoachConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pronunciation_attempts",
    )
    expected_word = models.CharField(max_length=120)
    transcript = models.CharField(max_length=255, blank=True)
    score = models.PositiveIntegerField(default=0)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.expected_word} - {self.score}"
