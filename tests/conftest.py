from django.conf import settings

def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            },
            INSTALLED_APPS=[
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django_auth0',
            ],
            DJANGO_AUTH0={
                'AUTH0_DOMAIN': 'test.auth0.com',
                'AUTH0_CLIENT_ID': 'test_client_id',
                'AUTH0_CLIENT_SECRET': 'test_client_secret',
                'AUDIENCE_AKA_ROLE_NAMESPACE': 'https://test.com',
            },
            SECRET_KEY='fake-key',
        )
