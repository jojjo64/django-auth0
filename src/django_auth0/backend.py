import logging
import sys
from typing import Any

from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Group, User
from django.http import HttpRequest


class Auth0Backend(BaseBackend):
    GROUPS_UPDATED = False

    def authenticate(self, request: HttpRequest, token: dict = None) -> User | None:
        """
        Authenticates a user based on the oauth2 token that has been received from Auth0 via the callback function.
         * creates or updates the user based on the provided user id in the token.
         * updates user s attributes based on the provided token and mapping set in settings.DJANGO_AUTH0
         * updates group memberships and user flags based on the provided token and mapping set in settings.DJANGO_AUTH0

        Args:
            request (django.http.HttpRequest): The current HTTP request.
            token (dict, optional): The access token dictionary returned by Auth0.

        Returns:
            django.contrib.auth.models.User|None: The authenticated Django User instance or None if authentication failed.

        Raises:
            ValueError: If the value given in AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION is not a callable function
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        # TODO: ??? do we really need this ???
        request.session["auth0_token"] = token

        mapped_user_attributes = self._map_user_attributes(token)
        logger.debug(f"mapped_user_attributes {mapped_user_attributes}")

        if not (user := self._update_or_create_user(mapped_user_attributes)):
            return None

        user = self._adjust_users_groups_based_on_auth0_roles(user, token)
        user = self._adjust_users_flags_based_on_auth0_roles(user, token)

        return user

    def _map_user_attributes(self, token: dict | None) -> dict:
        """
        Maps user attributes from an input token to a structured dictionary, leveraging either a
        custom mapping function specified in the settings or the default mapping logic.

        Args:
            token (dict | None): A dictionary representing the input data to be mapped, typically retrieved
                from Auth0. May also be None.

        Returns:
            dict: A dictionary containing the mapped user attributes based on the input token.

        Raises:
            ValueError: If the function provided in setting `AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION`
                is not callable.
        """
        logger = logging.getLogger("DJANGO_AUTH0")

        if mapping_func := settings.DJANGO_AUTH0.get("AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION", None):
            if not callable(mapping_func):
                raise ValueError("The value given in AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION must be a callable function!!!")
            logger.debug(f"Calling AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION {mapping_func.__name__}...")
            mapped_user_attributes = mapping_func(token)
        else:
            mapped_user_attributes = self._map_auth0_to_user_attributes(token)
        return mapped_user_attributes

    def _map_auth0_to_user_attributes(self, token: dict) -> dict[Any, Any]:
        """
        Maps Auth0 user information to Django User attributes using the settings defined in DJANGO_AUTH0 s AUTH0_TO_USER_ATTRIBUTE_MAPPING
        mapping.

        Args:
            token (dict): The access token dictionary returned by Auth0, containing 'userinfo'.

        Returns:
            dict[Any, Any]: A dictionary of mapped Django User attributes.

        Raises:
            ValueError: If the resulting username is blank.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        userinfo = token.get("userinfo")
        logger.debug(f"userinfo is {userinfo}")
        auth0_to_user_attribute_mapping = settings.DJANGO_AUTH0.get("AUTH0_TO_USER_ATTRIBUTE_MAPPING", {"sub": "username"})
        logger.debug(f"auth0_to_user_attribute_mapping is {auth0_to_user_attribute_mapping}")
        mapped_user_attributes = {
            auth0_to_user_attribute_mapping[k]: v for k, v in userinfo.items() if k in auth0_to_user_attribute_mapping
        }

        if "username" not in mapped_user_attributes or not mapped_user_attributes["username"]:
            raise ValueError("username can't be empty!!!")

        # The format of user_id is
        #    {identity provider id}|{unique id in the provider}
        # The pipe character is invalid for the django username field
        # The solution is to replace the pipe with a dash
        mapped_user_attributes["username"] = mapped_user_attributes["username"].replace("|", "_")
        # while django has a first_name and last_name field, auth0 only has a name field
        # if the GET_FIRST_LAST_NAME_FROM_AUTHO_NAME flag is set to true, then use this algorithm:
        #  * the last blank separated word in name is the last name
        #  * all blank separated words except the last name make the first name
        # this may not be 100% error free --> thus we offer the AUTH0_TO_USER_ATTRIBUTE_MAPPING_FUNCTION setting the user can
        # configure to set his own callable to process the user attribute mapping...
        if settings.DJANGO_AUTH0.get("GET_FIRST_LAST_NAME_FROM_AUTHO_NAME", False):
            logger.debug("GET_FIRST_LAST_NAME_FROM_AUTHO_NAME is set -- try to split auth0 name...")
            if " " in userinfo["name"]:
                mapped_user_attributes["last_name"] = userinfo["name"].split()[-1]
                mapped_user_attributes["first_name"] = " ".join(userinfo["name"].split()[:-1])
            else:
                logger.warning(f'No blank found in userinfo s name "{userinfo["name"]}" !!!')

        return mapped_user_attributes

    def _update_or_create_user(self, mapped_user_attributes: dict) -> User | None:
        """
        Updates an existing Django User or creates a new one based on the mapped attributes.

        If the user exists and `UPDATE_DJANGO_USER_FROM_AUTHO` is True, its attributes are updated.
        If the user does not exist and `CREATE_DJANGO_USER_FROM_AUTHO` is True, a new user is created.
        In both cases, if the user has a usable password, it is set to unusable.

        Args:
            mapped_user_attributes (dict): A dictionary of Django User attributes.

        Returns:
            django.contrib.auth.models.User | None: The updated or created User instance,
                or None if creation was skipped.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        # if the user already exists and UPDATE_DJANGO_USER_FROM_AUTHO is set to True: update its attributes
        try:
            user = User.objects.get(username=mapped_user_attributes["username"])
            logger.debug(f"found existing user {user}")
            if settings.DJANGO_AUTH0.get("UPDATE_DJANGO_USER_FROM_AUTHO", True):
                logger.debug(f"update existing user {user}")
                user.__dict__.update(mapped_user_attributes)
                # if user has a usable password --> make it unusable since we are coming in via Auth0...
                if user.has_usable_password():
                    logger.debug("calling set_unusable_password()")
                    user.set_unusable_password()
                user.save()
        # else: if CREATE_DJANGO_USER_FROM_AUTHO is set to True: create the user
        except User.DoesNotExist:
            if settings.DJANGO_AUTH0.get("CREATE_DJANGO_USER_FROM_AUTHO", True):
                logger.info(f"creating new user {mapped_user_attributes}")
                user = User(**mapped_user_attributes)
                user.set_unusable_password()
                user.save()
            else:
                logger.warning(f"CREATE_DJANGO_USER_FROM_AUTHO set to False --> NOT creating user {mapped_user_attributes}")
                return None
        return user

    def _adjust_users_groups_based_on_auth0_roles(self, user, token) -> User | None:
        """
        Adjusts the Django User's group memberships based on Auth0 roles.

        This method maps Auth0 roles to Django groups based on the `AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS`
        setting in `DJANGO_AUTH0`.
        It ensures all relevant groups exist, adds the user to groups corresponding to their roles,
        and removes them from groups that are no longer assigned.

        Args:
            user (django.contrib.auth.models.User): The Django User instance to update.
            token (dict): The access token dictionary returned by Auth0, containing role information.

        Returns:
            django.contrib.auth.models.User: The updated User instance.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        role_mappings = settings.DJANGO_AUTH0.get("AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS", {})
        logger.debug(f"role_mappings: {role_mappings}")
        if not role_mappings:
            # No role mappings defined, nothing to do
            return user

        roles_claim = settings.DJANGO_AUTH0.get("ROLES_CLAIM", f"{settings.DJANGO_AUTH0['AUDIENCE_AKA_ROLE_NAMESPACE']}/roles")
        logger.debug(f"roles_claim: {roles_claim}")
        auth0_token_roles = token.get("userinfo", {}).get(roles_claim, [])
        logger.debug(f"auth0_token_roles: {auth0_token_roles}")

        token_groups = set()
        all_groups = set()
        for role_id, groups_and_flag_settings in role_mappings.items():
            for group_names in groups_and_flag_settings.get("GROUPS", []):
                if not isinstance(group_names, list):
                    group_names = [group_names]
                all_groups.update(group_names)
                if role_id in auth0_token_roles:
                    token_groups.update(group_names)
        logger.debug(f"token_groups: {token_groups}")
        logger.debug(f"all_groups: {all_groups}")
        self._initialize_groups(all_groups)

        current_groups = list(user.groups.values_list("name", flat=True))
        logger.debug(f"current_groups: {current_groups}")

        if to_add := [item for item in token_groups if item not in current_groups]:
            logger.info(f"adding groups {to_add}")
            user.groups.add(*Group.objects.filter(name__in=to_add))

        if to_remove := [item for item in current_groups if item in all_groups and item not in token_groups]:
            logger.info(f"removing groups {to_remove}")
            user.groups.remove(*Group.objects.filter(name__in=to_remove))
        return user

    def _initialize_groups(self, all_groups: set = None) -> None:
        """
        Ensures that all Django groups that are mentioned in the `AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS`
        exist in the django database.

        This initialization is performed only once on the first run of the authenticate method
        (when `GROUPS_UPDATED` is False).

        Args:
            all_groups (set, optional): A set of group names to be created if they don't exist.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        if not self.GROUPS_UPDATED:
            if all_groups:
                logger.debug(f"get_or_create groups {all_groups}")
                for group_name in all_groups:
                    if group_name:
                        Group.objects.get_or_create(name=group_name)
        self.GROUPS_UPDATED = True

    def _adjust_users_flags_based_on_auth0_roles(self, user, token) -> User | None:
        """
        Adjusts the Django User's flags based on Auth0 roles.

        This method maps Auth0 roles to Django user flags based on the `AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS`
        setting in `DJANGO_AUTH0`.

        Args:
            user (django.contrib.auth.models.User): The Django User instance to update.
            token (dict): The access token dictionary returned by Auth0, containing role information.

        Returns:
            django.contrib.auth.models.User: The updated User instance.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        flag_mappings = settings.DJANGO_AUTH0.get("AUTH0_ROLE_TO_GROUP_AND_USER_FLAG_MAPPINGS", {})
        logger.debug(f"flag_mappings: {flag_mappings}")
        if not flag_mappings:
            # No flag mappings defined, nothing to do
            return user

        roles_claim = settings.DJANGO_AUTH0.get("ROLES_CLAIM", f"{settings.DJANGO_AUTH0['AUDIENCE_AKA_ROLE_NAMESPACE']}/roles")
        logger.debug(f"roles_claim: {roles_claim}")
        auth0_token_roles = token.get("userinfo", {}).get(roles_claim, [])
        logger.debug(f"auth0_token_roles: {auth0_token_roles}")

        users_flags = set()
        users_flags.update(["is_active"])
        all_settable_flags = ("is_staff", "is_superuser", "is_active")
        for role_id, groups_and_flag_settings in flag_mappings.items():
            for flag in groups_and_flag_settings.get("FLAGS", []):
                if role_id in auth0_token_roles:
                    if flag in all_settable_flags:
                        logger.debug(f'found role_id "{role_id}" in auth0_token_roles --> will set flag "{flag}"')
                        users_flags.add(flag)
                    else:
                        logger.warning(f'flag "{flag} NOT in all_settable_flags --> will NOT set flag "{flag}"!')
        logger.debug(f"users_flags: {users_flags}")

        for flag in all_settable_flags:
            setattr(user, flag, True if flag in users_flags else False)
            logger.debug(f'set flag "{flag}" to "{getattr(user, flag)}"...')

        user.save()
        return user

    def get_user(self, user_id: int) -> User:
        """
        Retrieves a User instance by its primary key.

        Args:
            user_id (int): The primary key of the user.

        Returns:
            django.contrib.auth.models.User or None: The User instance if found, otherwise None.
        """
        logger = logging.getLogger("DJANGO_AUTH0")
        logger.debug(sys._getframe().f_code.co_name + " starts...")

        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
