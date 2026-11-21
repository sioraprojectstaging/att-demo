from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import serializers


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Check if user is approved (for ADMIN accounts)
        if self.user.role == 'ADMIN' and not self.user.is_approved:
            raise serializers.ValidationError({
                "error": "Your account is pending approval by system administrator."
            })
        
        # Add extra responses including location
        data.update({'user': {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'role': self.user.role,
            'location': self.user.location.id if self.user.location else None,
            'location_display': self.user.location.name if self.user.location else '',
        }})
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
