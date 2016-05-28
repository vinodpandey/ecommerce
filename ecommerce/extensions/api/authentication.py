""" Custom DRF authentication modules. """

from edx_rest_framework_extensions.authentication import BearerAuthentication as BaseBearerAuthentication


class BearerAuthentication(BaseBearerAuthentication):
    def authenticate(self, request):
        self.request = request  # pylint: disable=attribute-defined-outside-init
        return super(BearerAuthentication, self).authenticate(request)

    def get_user_info_url(self):
        """ Returns the URL, hosted by the OAuth2 provider, from which user information can be pulled. """
        return '{base}/user_info/'.format(base=self.request.site.siteconfiguration.oauth2_provider_url)
