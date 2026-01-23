import pytest
from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Group
from django_auth0.backends import Auth0Backend

@pytest.fixture
def auth0_token():
    return {
        "access_token": "test_access_token",
        "id_token": "test_id_token",
        "userinfo": {
            "sub": "auth0|123456",
            "name": "John Doe",
            "email": "john@example.com",
            "https://test.com/roles": ["admin", "editor"]
        }
    }

@pytest.mark.usefixtures("auth0_token")
class Auth0BackendTest(TestCase):
    def setUp(self):
        self.backend = Auth0Backend()

    @pytest.fixture(autouse=True)
    def _get_token(self, auth0_token):
        self.auth0_token = auth0_token

    @override_settings(DJANGO_AUTH0={
        "AUTH0_TO_USER_ATTRIBUTE_MAPPING": {"sub": "username", "email": "email"},
        "GET_FIRST_LAST_NAME_FROM_AUTHO_NAME": False
    })
    def test_map_auth0_to_user_attributes_basic(self):
        # We need to ensure that the replacement of | with _ is tested
        token = {
            "userinfo": {
                "sub": "auth0|67890",
                "email": "test@example.com"
            }
        }
        mapped = self.backend._map_auth0_to_user_attributes(token)
        self.assertEqual(mapped["username"], "auth0_67890")
        self.assertEqual(mapped["email"], "test@example.com")

    @override_settings(DJANGO_AUTH0={
        "AUTH0_TO_USER_ATTRIBUTE_MAPPING": {"sub": "username"},
        "GET_FIRST_LAST_NAME_FROM_AUTHO_NAME": True
    })
    def test_map_auth0_to_user_attributes_name_split(self):
        mapped = self.backend._map_auth0_to_user_attributes(self.auth0_token)
        self.assertEqual(mapped["first_name"], "John")
        self.assertEqual(mapped["last_name"], "Doe")

    def test_map_auth0_to_user_attributes_no_username(self):
        token = {"userinfo": {"email": "john@example.com"}}
        with override_settings(DJANGO_AUTH0={"AUTH0_TO_USER_ATTRIBUTE_MAPPING": {"email": "email"}}):
            with self.assertRaisesRegex(ValueError, "username can't be empty!!!"):
                self.backend._map_auth0_to_user_attributes(token)

    def test_update_or_create_user_create(self):
        mapped_attributes = {
            "username": "new_user",
            "email": "new@example.com"
        }
        user = self.backend._update_or_create_user(mapped_attributes)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "new_user")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(User.objects.filter(username="new_user").exists())

    def test_update_or_create_user_update(self):
        existing_user = User.objects.create(username="existing_user", email="old@example.com")
        existing_user.set_password("password123")
        existing_user.save()
        
        mapped_attributes = {
            "username": "existing_user",
            "email": "new@example.com"
        }
        user = self.backend._update_or_create_user(mapped_attributes)
        self.assertEqual(user.pk, existing_user.pk)
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.has_usable_password())

    @override_settings(DJANGO_AUTH0={"CREATE_DJANGO_USER_FROM_AUTHO": False})
    def test_update_or_create_user_no_create(self):
        mapped_attributes = {"username": "non_existent"}
        user = self.backend._update_or_create_user(mapped_attributes)
        self.assertIsNone(user)

    @override_settings(DJANGO_AUTH0={
        "AUDIENCE_AKA_ROLE_NAMESPACE": "https://test.com",
        "AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS": {
            "admin": {"GROUPS": ["Admins", "Staff"]},
            "editor": {"GROUPS": ["Editors"]}
        }
    })
    def test_adjust_users_groups_based_on_auth0_roles(self):
        user = User.objects.create(username="testuser")
        # Ensure groups don't exist yet
        Group.objects.all().delete()
        
        updated_user = self.backend._adjust_users_groups_based_on_auth0_roles(user, self.auth0_token)
        
        group_names = updated_user.groups.values_list("name", flat=True)
        self.assertIn("Admins", list(group_names))
        self.assertIn("Staff", list(group_names))
        self.assertIn("Editors", list(group_names))
        
        # Test removal
        self.auth0_token["userinfo"]["https://test.com/roles"] = ["admin"]
        updated_user = self.backend._adjust_users_groups_based_on_auth0_roles(user, self.auth0_token)
        group_names = updated_user.groups.values_list("name", flat=True)
        self.assertIn("Admins", list(group_names))
        self.assertIn("Staff", list(group_names))
        self.assertNotIn("Editors", list(group_names))

    @override_settings(DJANGO_AUTH0={
        "AUDIENCE_AKA_ROLE_NAMESPACE": "https://test.com",
        "AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS": {
            "admin": {"FLAGS": ["is_staff", "is_superuser"]},
        }
    })
    def test_adjust_users_flags_based_on_auth0_roles(self):
        user = User.objects.create(username="testuser", is_staff=False, is_superuser=False)
        
        # Admin role present
        updated_user = self.backend._adjust_users_flags_based_on_auth0_roles(user, self.auth0_token)
        self.assertTrue(updated_user.is_staff)
        self.assertTrue(updated_user.is_superuser)
        self.assertTrue(updated_user.is_active) 

        # Admin role removed
        self.auth0_token["userinfo"]["https://test.com/roles"] = []
        updated_user = self.backend._adjust_users_flags_based_on_auth0_roles(user, self.auth0_token)
        self.assertFalse(updated_user.is_staff)
        self.assertFalse(updated_user.is_superuser)
        self.assertTrue(updated_user.is_active)
