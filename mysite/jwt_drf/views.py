import requests
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import UserRegisterSerializer, UserLoginSerializer, UserMeSerializer


def crud_url(path: str) -> str:
    return f"{settings.CRUD_BASE_URL.rstrip('/')}{path}"


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = dict(serializer.validated_data)
        payload.pop("password_confirm", None)

        # CRUD должен создать пользователя в своей БД
        try:
            r = requests.post(crud_url("/api/auth/register/"), json=payload, timeout=8)
        except requests.RequestException:
            return Response({"detail": "CRUD сервис недоступен"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if r.status_code != 201:
            # Пробрасываем ошибку CRUD как есть
            try:
                return Response(r.json(), status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({"detail": "Ошибка регистрации в CRUD"}, status=status.HTTP_400_BAD_REQUEST)

        user = r.json()
        user_id = user.get("id")

        refresh = RefreshToken()
        refresh["user_id"] = user_id
        refresh["username"] = user.get("username")

        return Response({
            "message": "Регистрация успешна",
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            r = requests.post(crud_url("/api/auth/check/"), json=serializer.validated_data, timeout=8)
        except requests.RequestException:
            return Response({"detail": "CRUD сервис недоступен"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if r.status_code != 200:
            return Response({"detail": "Неверный логин или пароль"}, status=status.HTTP_400_BAD_REQUEST)

        user = r.json()
        user_id = user.get("id")

        refresh = RefreshToken()
        refresh["user_id"] = user_id
        refresh["username"] = user.get("username")

        return Response({
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh токен обязателен"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Выход выполнен успешно"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"detail": "Неверный или уже использованный refresh токен"}, status=status.HTTP_400_BAD_REQUEST)


class UserMeView(APIView):
    """
    Берем профиль из CRUD по токену
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        auth_header = request.headers.get("Authorization", "")
        try:
            r = requests.get(
                crud_url("/api/auth/me/"),
                headers={"Authorization": auth_header},
                timeout=8
            )
        except requests.RequestException:
            return Response({"detail": "CRUD сервис недоступен"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if r.status_code != 200:
            return Response({"detail": "Не удалось получить профиль"}, status=status.HTTP_400_BAD_REQUEST)

        data = r.json()
        out = UserMeSerializer(data=data)
        out.is_valid(raise_exception=True)
        return Response(out.validated_data, status=status.HTTP_200_OK)
