from django.contrib import admin

from .models import (
    Badge,
    Course,
    CulturalExperience,
    Enrollment,
    Language,
    Lesson,
    LessonProgress,
    Module,
    QuizAttempt,
    QuizQuestion,
    Traduction,
    UserBadge,
    UserProfile,
)


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "category", "difficulty", "is_premium", "is_active")
    search_fields = ("name", "code")
    prepopulated_fields = {"slug": ("name",)}


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "focus", "level", "is_premium", "is_published")
    list_filter = ("focus", "is_premium", "is_published", "language")
    search_fields = ("title", "short_description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ModuleInline]


class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 1


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "lesson_type", "estimated_minutes", "xp_reward")
    list_filter = ("lesson_type", "module__course")
    search_fields = ("title", "content", "culture_note")
    inlines = [QuizQuestionInline]


@admin.register(Traduction)
class TraductionAdmin(admin.ModelAdmin):
    list_display = ("mot_origine", "langue_cible", "date_ajout")
    list_filter = ("langue_cible",)
    search_fields = ("mot_origine", "resultat_traduction")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "selected_language", "level", "goal", "is_premium", "total_xp", "streak_days")
    list_filter = ("is_premium", "level", "goal")
    search_fields = ("user__username", "user__email")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "status", "progress_percent", "updated_at")
    list_filter = ("status", "course")
    search_fields = ("user__username", "course__title")


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "completed", "score", "completed_at")
    list_filter = ("completed", "lesson__module__course")
    search_fields = ("user__username", "lesson__title")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "score", "correct_answers", "total_questions", "created_at")
    list_filter = ("lesson__module__course",)
    search_fields = ("user__username", "lesson__title")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "xp_threshold", "icon")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "awarded_at")
    search_fields = ("user__username", "badge__name")


@admin.register(CulturalExperience)
class CulturalExperienceAdmin(admin.ModelAdmin):
    list_display = ("title", "experience_type", "is_premium", "cta_label")
    list_filter = ("experience_type", "is_premium")
    search_fields = ("title", "description")
    prepopulated_fields = {"slug": ("title",)}
