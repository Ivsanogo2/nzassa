from django.contrib import admin

from .models import (
    AudioTrack,
    Badge,
    CoachConversation,
    CoachMessage,
    Course,
    CulturalExperience,
    Enrollment,
    Ethnicity,
    Language,
    Lesson,
    LearnedWord,
    LessonProgress,
    LearningEvent,
    LearningGroup,
    MicroLessonSubscription,
    MobileMoneyPayment,
    Module,
    Notification,
    OfflinePack,
    PrivateMessage,
    PronunciationAttempt,
    QuizAttempt,
    QuizQuestion,
    Book,
    Certificate,
    EducationalGame,
    FriendConnection,
    GroupMembership,
    School,
    SchoolMembership,
    ShortVideo,
    SocialComment,
    SocialPost,
    Story,
    StoryComment,
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


@admin.register(Ethnicity)
class EthnicityAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "region", "latitude", "longitude", "created_at")
    search_fields = ("name", "region", "description", "traditions")
    list_filter = ("language",)
    prepopulated_fields = {"slug": ("name",)}


class StoryCommentInline(admin.TabularInline):
    model = StoryComment
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title", "ethnicity", "location", "author", "is_published", "created_at")
    list_filter = ("is_published", "ethnicity", "location")
    search_fields = ("title", "description", "location", "ethnicity__name")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [StoryCommentInline]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author_name", "category", "uploaded_by", "is_published", "created_at")
    list_filter = ("category", "is_published")
    search_fields = ("title", "author_name", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(AudioTrack)
class AudioTrackAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "story", "lesson", "is_downloadable", "created_at")
    list_filter = ("language", "is_downloadable")
    search_fields = ("title", "transcript", "story__title", "lesson__title")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ShortVideo)
class ShortVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "author", "is_published", "created_at")
    list_filter = ("language", "is_published")
    search_fields = ("title", "caption")
    prepopulated_fields = {"slug": ("title",)}


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0


@admin.register(LearningGroup)
class LearningGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "owner", "is_public", "created_at")
    list_filter = ("language", "is_public")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GroupMembershipInline]


@admin.register(FriendConnection)
class FriendConnectionAdmin(admin.ModelAdmin):
    list_display = ("requester", "addressee", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("requester__username", "addressee__username")


@admin.register(PrivateMessage)
class PrivateMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "recipient", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("sender__username", "recipient__username", "body")


class SchoolMembershipInline(admin.TabularInline):
    model = SchoolMembership
    extra = 0


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "owner", "invite_code", "is_active", "created_at")
    list_filter = ("is_active", "city")
    search_fields = ("name", "city", "invite_code")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SchoolMembershipInline]


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "level_label", "score", "code", "issued_at")
    search_fields = ("user__username", "course__title", "code")


@admin.register(EducationalGame)
class EducationalGameAdmin(admin.ModelAdmin):
    list_display = ("title", "game_type", "language", "xp_reward", "is_published")
    list_filter = ("game_type", "language", "is_published")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(OfflinePack)
class OfflinePackAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "story", "book", "audio", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "course__title", "story__title", "book__title", "audio__title")


@admin.register(MicroLessonSubscription)
class MicroLessonSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "channel", "phone_number", "language", "is_active", "created_at")
    list_filter = ("channel", "is_active", "language")
    search_fields = ("user__username", "phone_number")


@admin.register(MobileMoneyPayment)
class MobileMoneyPaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "amount", "reference", "status", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("user__username", "phone_number", "reference")


@admin.register(LearningEvent)
class LearningEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "object_label", "created_at")
    list_filter = ("event_type",)
    search_fields = ("user__username", "event_type", "object_label")


class SocialCommentInline(admin.TabularInline):
    model = SocialComment
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ("author", "group", "created_at", "updated_at")
    list_filter = ("group",)
    search_fields = ("author__username", "content", "group__name")
    inlines = [SocialCommentInline]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "actor", "verb", "target_label", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("recipient__username", "actor__username", "verb", "target_label")


@admin.register(CoachConversation)
class CoachConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "channel", "user", "selected_language", "updated_at")
    list_filter = ("channel", "selected_language")
    search_fields = ("user__username", "session_key", "title")


@admin.register(CoachMessage)
class CoachMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "used_openai", "created_at")
    list_filter = ("role", "used_openai")
    search_fields = ("content",)


@admin.register(LearnedWord)
class LearnedWordAdmin(admin.ModelAdmin):
    list_display = ("word", "language_label", "user", "mastery_level", "times_practiced", "times_correct")
    list_filter = ("language_label",)
    search_fields = ("word", "meaning", "example", "user__username", "session_key")


@admin.register(PronunciationAttempt)
class PronunciationAttemptAdmin(admin.ModelAdmin):
    list_display = ("expected_word", "score", "conversation", "created_at")
    search_fields = ("expected_word", "transcript", "feedback")
