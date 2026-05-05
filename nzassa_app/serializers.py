from rest_framework import serializers

from .models import (
    AudioTrack,
    Book,
    Course,
    Ethnicity,
    Language,
    LearningGroup,
    Lesson,
    OfflinePack,
    ShortVideo,
    SocialComment,
    SocialPost,
    Story,
    UserProfile,
)


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ("id", "name", "slug", "code", "description", "category", "difficulty", "is_premium")


class CourseSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "title",
            "slug",
            "short_description",
            "description",
            "language",
            "focus",
            "level",
            "estimated_minutes",
            "xp_reward",
            "is_premium",
            "lesson_count",
        )


class LessonSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="module.course.title", read_only=True)
    language = serializers.CharField(source="module.course.language.name", read_only=True)

    class Meta:
        model = Lesson
        fields = ("id", "title", "order", "lesson_type", "content", "culture_note", "key_phrase", "estimated_minutes", "xp_reward", "course_title", "language")


class EthnicitySerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    story_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ethnicity
        fields = ("id", "name", "slug", "language", "region", "description", "traditions", "latitude", "longitude", "map_color", "story_count")


class StorySerializer(serializers.ModelSerializer):
    ethnicity = EthnicitySerializer(read_only=True)
    author_name = serializers.CharField(source="author.username", read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    youtube_embed_url = serializers.CharField(read_only=True)

    class Meta:
        model = Story
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "image",
            "audio_file",
            "location",
            "youtube_url",
            "youtube_embed_url",
            "ethnicity",
            "author_name",
            "reading_minutes",
            "like_count",
            "comment_count",
            "created_at",
        )


class BookSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.username", read_only=True)
    favorite_count = serializers.IntegerField(source="favorites.count", read_only=True)

    class Meta:
        model = Book
        fields = ("id", "title", "slug", "author_name", "description", "cover", "pdf_file", "category", "uploaded_by_name", "favorite_count", "created_at")


class AudioTrackSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    source_url = serializers.CharField(read_only=True)
    story_title = serializers.CharField(source="story.title", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)

    class Meta:
        model = AudioTrack
        fields = ("id", "title", "slug", "language", "story_title", "lesson_title", "source_url", "transcript", "duration_seconds", "is_downloadable", "created_at")


class SocialCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = SocialComment
        fields = ("id", "author_name", "content", "created_at")


class SocialPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    comments = SocialCommentSerializer(many=True, read_only=True)

    class Meta:
        model = SocialPost
        fields = ("id", "author_name", "group", "group_name", "content", "image", "like_count", "comment_count", "comments", "created_at")
        read_only_fields = ("author_name",)


class LearningGroupSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LearningGroup
        fields = ("id", "name", "slug", "language", "description", "owner_name", "is_public", "member_count", "created_at")


class ShortVideoSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    author_name = serializers.CharField(source="author.username", read_only=True)
    video_source = serializers.CharField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShortVideo
        fields = ("id", "title", "slug", "language", "author_name", "caption", "video_source", "thumbnail", "like_count", "created_at")


class OfflinePackSerializer(serializers.ModelSerializer):
    target_label = serializers.SerializerMethodField()

    class Meta:
        model = OfflinePack
        fields = ("id", "status", "target_label", "size_kb", "last_synced_at", "created_at")

    def get_target_label(self, obj):
        target = obj.course or obj.story or obj.book or obj.audio
        return str(target) if target else "Pack offline"


class UserProfileSerializer(serializers.ModelSerializer):
    selected_language = LanguageSerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ("level", "goal", "is_premium", "total_xp", "streak_days", "selected_language")
