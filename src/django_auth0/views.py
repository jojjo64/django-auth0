import base64
import logging
import sys
import uuid
from http.client import HTTPConnection
from urllib.parse import quote_plus, unquote_plus, urlencode

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpResponse, HttpResponseRedirect, HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

STATE_NEXT_SEPARATOR = "||"

logger = logging.getLogger("DJANGO_AUTH0")
logger.debug("about to register auth0 client...")

HTTPConnection.debuglevel = 1
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

oauth = OAuth()
oauth.register(
    "auth0",
    client_id=settings.DJANGO_AUTH0["AUTH0_CLIENT_ID"],
    client_secret=settings.DJANGO_AUTH0["AUTH0_CLIENT_SECRET"],
    client_kwargs={
        "scope": settings.DJANGO_AUTH0.get("SCOPE", "openid profile email"),
        "audience": settings.DJANGO_AUTH0["AUDIENCE_AKA_ROLE_NAMESPACE"],
    },
    server_metadata_url=settings.DJANGO_AUTH0["SERVER_METADATA_URL"],
)


def auth0_login(request: HttpRequest) -> HttpResponse:
    """
    Redirects the user to the Auth0 Universal Login page.

    Args:
        request (django.http.HttpRequest): The incoming HTTP request.

    Returns:
        django.http.HttpResponse: An authorization redirect to Auth0.
    """
    logger = logging.getLogger("DJANGO_AUTH0")
    logger.debug(sys._getframe().f_code.co_name + " starts...")

    state = _add_next_url_to_state(request)
    logger.debug(f'auth0_login state "{state}"')
    return oauth.auth0.authorize_redirect(
        request,
        request.build_absolute_uri(reverse("callback")),
        state=state,
    )


def _add_next_url_to_state(request: HttpRequest) -> str:
    """
    Encodes a unique state string including the 'next' URL parameter.

    Args:
        request (django.http.HttpRequest): The incoming HTTP request containing GET parameters.

    Returns:
        str: A base64 encoded string containing a UUID and the next URL.
    """
    logger = logging.getLogger("DJANGO_AUTH0")
    logger.debug(sys._getframe().f_code.co_name + " starts...")

    next = request.GET.get("next")
    logger.debug(f'django s next is "{next}"')
    state = base64.b64encode(f"{uuid.uuid4()}{STATE_NEXT_SEPARATOR}{quote_plus(next)}".encode("utf-8")).decode("utf-8")
    return state


def auth0_callback(request: HttpRequest) -> HttpResponse:
    """
    Handles the callback from Auth0 after a user logs in.

    Args:
        request (django.http.HttpRequest): The incoming HTTP request from Auth0.

    Returns:
        django.http.HttpResponse: A redirect to the 'next' URL on success, or a 400 error on failure.
    """
    logger = logging.getLogger("DJANGO_AUTH0")
    logger.debug(sys._getframe().f_code.co_name + " starts...")

    token = oauth.auth0.authorize_access_token(request)
    logger.debug(f'token is "{token}"')

    user = auth.authenticate(request, token=token)

    if user:
        auth.login(request, user)
        next = _get_next_url_from_state(request, user)
        logger.debug(f'auth0_callback next "{next}"')
        if url_has_allowed_host_and_scheme(next, allowed_hosts=None):
            logger.debug("url_has_allowed_host_and_scheme ok...")
            return HttpResponseRedirect(next)
        logger.debug("redirecting to settings.LOGIN_REDIRECT_URL...")
        return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)

    logger.error("No valid user !!! Returning 400 (access denied)...")
    return HttpResponse(status=400)


def _get_next_url_from_state(request: HttpRequest, user: AbstractBaseUser) -> str:
    """
    Extracts and decodes the 'next' URL from the state parameter in the callback.

    Args:
        request (django.http.HttpRequest): The incoming HTTP request containing the state.
        user (django.contrib.auth.base_user.AbstractBaseUser): The authenticated user object.

    Returns:
        str: The URL to redirect to after successful login.
    """
    logger = logging.getLogger("DJANGO_AUTH0")
    logger.debug(sys._getframe().f_code.co_name + " starts...")

    state = base64.b64decode(request.GET.get("state", "").encode("utf-8")).decode("utf-8")
    logger.debug(f'state in callback is "{state}"')
    if STATE_NEXT_SEPARATOR in state:
        next = unquote_plus(state.split(STATE_NEXT_SEPARATOR)[1])
        if not next:
            logger.warning(f'No next found in state when processing user "{user}"...')
            next = settings.LOGIN_REDIRECT_URL
    else:
        logger.warning(f'No || separator found in state when processing user "{user}"...')
        next = settings.LOGIN_REDIRECT_URL
    return next


def auth0_logout(request: HttpRequest) -> HttpResponse:
    """
    Logs the user out of the Django session and redirects to Auth0 for global logout.

    Args:
        request (django.http.HttpRequest): The incoming HTTP request.

    Returns:
        django.http.HttpResponseRedirect: A redirect to the Auth0 logout endpoint.
    """
    logger = logging.getLogger("DJANGO_AUTH0")
    logger.debug(sys._getframe().f_code.co_name + " starts...")

    auth.logout(request)
    request.session.clear()

    return redirect(
        f"https://{settings.DJANGO_AUTH0['AUTH0_DOMAIN']}/v2/logout?"
        + urlencode(
            {
                "returnTo": request.build_absolute_uri(reverse("welcome_page")),
                "client_id": settings.DJANGO_AUTH0["AUTH0_CLIENT_ID"],
            },
            quote_via=quote_plus,
        ),
    )
