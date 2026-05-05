from django.db.models import Count, Q
from rest_framework import permissions, routers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AudioTrack,
    Book,
    Course,
    Enrollment,
    Ethnicity,
    Language,
    LearningGroup,
    Lesson,
    LessonProgress,
    OfflinePack,
    ShortVideo,
    SocialPost,
    Story,
    UserBadge,
)
from .serializers import (
    AudioTrackSerializer,
    BookSerializer,
    CourseSerializer,
    EthnicitySerializer,
    LanguageSerializer,
    LearningGroupSerializer,
    LessonSerializer,
    OfflinePackSerializer,
    ShortVideoSerializer,
    SocialPostSerializer,
    StorySerializer,
    UserProfileSerializer,
)
from .views import build_ai_content_recommendations, get_or_create_profile


class OwnerWriteMixin:
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Language.objects.filter(is_active=True)
    serializer_class = LanguageSerializer


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Course.objects.filter(is_published=True).select_related("language")
    serializer_class = CourseSerializer


class LessonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lesson.objects.select_related("module__course", "module__course__language")
    serializer_class = LessonSerializer


class EthnicityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ethnicity.objects.select_related("language").annotate(story_count=Count("stories", distinct=True))
    serializer_class = EthnicitySerializer


class StoryViewSet(OwnerWriteMixin, viewsets.ModelViewSet):
    queryset = Story.objects.filter(is_published=True).select_related("ethnicity", "author")
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.filter(is_published=True).select_related("uploaded_by").prefetch_related("favorites")
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class AudioTrackViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AudioTrack.objects.select_related("language", "story", "lesson")
    serializer_class = AudioTrackSerializer
    lookup_field = "slug"


class SocialPostViewSet(OwnerWriteMixin, viewsets.ModelViewSet):
    queryset = SocialPost.objects.select_related("author", "group").prefetch_related("comments", "likes")
    serializer_class = SocialPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class LearningGroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LearningGroup.objects.select_related("language", "owner").annotate(member_count=Count("memberships", distinct=True))
    serializer_class = LearningGroupSerializer
    lookup_field = "slug"


class ShortVideoViewSet(OwnerWriteMixin, viewsets.ModelViewSet):
    queryset = ShortVideo.objects.filter(is_published=True).select_related("language", "author").prefetch_related("likes")
    serializer_class = ShortVideoSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"


class OfflinePackViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OfflinePackSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OfflinePack.objects.filter(user=self.request.user).select_related("course", "story", "book", "audio")


class DashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_or_create_profile(request.user)
        enrollments = Enrollment.objects.filter(user=request.user).select_related("course", "course__language")
        completed_lessons = LessonProgress.objects.filter(user=request.user, completed=True).count()
        badges = UserBadge.objects.filter(user=request.user).select_related("badge")
        return Response(
            {
                "profile": UserProfileSerializer(profile).data,
                "enrollments": [
                    {
                        "course": item.course.title,
                        "slug": item.course.slug,
                        "language": item.course.language.name,
                        "progress_percent": item.progress_percent,
                        "status": item.status,
                    }
                    for item in enrollments
                ],
                "completed_lessons": completed_lessons,
                "badges": [item.badge.name for item in badges],
            }
        )


class RecommendationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get(self, request):
        prompt = request.GET.get("q", "")
        selected_language = None
        if request.user.is_authenticated:
            selected_language = get_or_create_profile(request.user).selected_language
        recommendations = build_ai_content_recommendations(prompt, selected_language=selected_language)
        return Response(
            {
                "stories": StorySerializer(recommendations["stories"], many=True, context={"request": request}).data,
                "books": BookSerializer(recommendations["books"], many=True, context={"request": request}).data,
                "courses": CourseSerializer(recommendations["courses"], many=True, context={"request": request}).data,
            }
        )


router = routers.DefaultRouter()
router.register("languages", LanguageViewSet, basename="api_languages")
router.register("courses", CourseViewSet, basename="api_courses")
router.register("lessons", LessonViewSet, basename="api_lessons")
router.register("ethnicities", EthnicityViewSet, basename="api_ethnicities")
router.register("stories", StoryViewSet, basename="api_stories")
router.register("books", BookViewSet, basename="api_books")
router.register("audio", AudioTrackViewSet, basename="api_audio")
router.register("posts", SocialPostViewSet, basename="api_posts")
router.register("groups", LearningGroupViewSet, basename="api_groups")
router.register("shorts", ShortVideoViewSet, basename="api_shorts")
router.register("offline-packs", OfflinePackViewSet, basename="api_offline_packs")
