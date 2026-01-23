![Coverage Status](./reports/coverage/coverage-badge.svg?dummy=8484744)

# django-auth0

A Django plugin to add Auth0 OIDC authentication to Django.

## Description

`django-auth0` simplifies the integration of Auth0 authentication into your Django applications. 
* It handles the OIDC flow, including user login, logout, and callback. 
* It also provides a custom authentication backend that can automatically create or update Django users based on Auth0 user claims and map Auth0 roles to 
  * Django groups (if you want to configure django permissions based on these) and 
  * user flags (is_staff, is_superuser) - e.g. if you want to set up django admin access for users

## Installation

You can install the package via pip (or your favorite package manager):

```bash
pip install django-auth0
```

Ensure you have `authlib` and `django` installed in your environment.

## Configuration

### Configure Auth0

Configure Auth0

### django settings
Add `django_auth0.backends.Auth0Backend` to your `AUTHENTICATION_BACKENDS` in `settings.py`:

```python
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'django_auth0.backends.Auth0Backend',
]
```

Configure the `DJANGO_AUTH0` setting in your `settings.py`:

```python
DJANGO_AUTH0 = {
    # Auth0 Application Credentials
    "AUTH0_CLIENT_ID": "your-client-id",
    "AUTH0_CLIENT_SECRET": "your-client-secret",
    "AUTH0_DOMAIN": "your-domain.auth0.com",
    
    # OIDC Configuration
    "SERVER_METADATA_URL": "https://your-domain.auth0.com/.well-known/openid-configuration",
    "AUDIENCE_AKA_ROLE_NAMESPACE": "https://your-api-identifier",
    "SCOPE": "openid profile email",
    
    # User Creation and Update Logic
    "CREATE_DJANGO_USER_FROM_AUTHO": True, # Create a new Django user if they don't exist
    "UPDATE_DJANGO_USER_FROM_AUTHO": True, # Update existing Django user attributes on every login
    
    # Attribute Mapping
    # Maps Auth0 'userinfo' keys to Django User model fields
    "AUTH0_TO_USER_ATTRIBUTE_MAPPING": {
        "sub": "username",
        "email": "email",
    },
    
    # If True, tries to split Auth0 'name' into 'first_name' and 'last_name'
    "GET_FIRST_LAST_NAME_FROM_AUTHO_NAME": False,
    
    # Optional: Custom mapping function (must be a callable)
    # "AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION": your_custom_mapping_func,

    # Role and Group Mapping
    "ROLES_CLAIM": "https://your-api-identifier/roles", # Claim in the token containing roles
    "AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS": {
        "auth0-role-name": {
            "GROUPS": ["Django Group Name"],
            "FLAGS": ["is_staff"], # Can be 'is_staff', 'is_superuser', 'is_active'
        },
    },
}
```

#### Settings Explanation

- `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_DOMAIN`: Standard Auth0 application credentials.
- `SERVER_METADATA_URL`: The URL to the OIDC well-known configuration.
- `AUDIENCE_AKA_ROLE_NAMESPACE`: Used as the audience for the token request and as a fallback prefix for the roles claim.
- `SCOPE`: The OIDC scopes to request.
- `CREATE_DJANGO_USER_FROM_AUTHO`: If `True`, a new Django user will be created if the Auth0 user doesn't exist locally.
- `UPDATE_DJANGO_USER_FROM_AUTHO`: If `True`, the Django user's attributes will be updated from Auth0 on every login.
- `AUTH0_TO_USER_ATTRIBUTE_MAPPING`: A dictionary mapping Auth0 profile keys to Django User model fields. The `username` field is mandatory and `|` characters in Auth0 IDs are automatically replaced with `_`.
- `GET_FIRST_LAST_NAME_FROM_AUTHO_NAME`: If `True`, the backend will attempt to split the `name` field from Auth0 into `first_name` and `last_name`.
- `AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION`: A callable that takes the `token` and returns a dictionary of Django user attributes. If provided, it overrides the default mapping logic.
- `ROLES_CLAIM`: The key in the Auth0 `userinfo` that contains the user's roles.
- `AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS`: A dictionary where keys are Auth0 role names and values are dictionaries specifying which Django `GROUPS` and `FLAGS` (is_staff, is_superuser, is_active) should be assigned to users with that role.

## Usage

Include the `django_auth0` URLs in your project's `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... your other urls
    path("auth0_auth/", include("django_auth0.urls")),
]
```

This will provide the following endpoints:
- `/auth0_auth/login`: Initiates the Auth0 login flow.
- `/auth0_auth/logout`: Logs the user out of Django and Auth0.
- `/auth0_auth/callback`: The callback URL for Auth0 (ensure this is registered in your Auth0 Application settings).

You can then use these in your templates:

### django template notation
```html
<a href="{% url 'auth0_auth:login' %}">Login</a>
<a href="{% url 'auth0_auth:logout' %}">Logout</a>
```

### Jinja2 template notation
```html
<a href="{% url('auth0_auth:login') %}">Login</a>
<a href="{% url('auth0_auth:logout') %}">Logout</a>
```

## Credits
This package is heavily inspired and some code parts are based on the excellent [django-azure-auth](https://pypi.org/project/django-azure-auth/) package.