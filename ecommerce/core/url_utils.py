import warnings

from threadlocals.threadlocals import get_current_request

from ecommerce.core.exceptions import MissingRequestError


def _get_site_configuration():
    """ Retrieve the SiteConfiguration from the current request from the global thread.

    Notes:
        This is a stopgap. Do NOT use this with any expectation that it will remain in place.
        This function WILL be removed.
    """
    warnings.warn('Usage of _get_site_configuration and django-threadlocals is deprecated. '
                  'Use the helper methods on the SiteConfiguration model.', DeprecationWarning)

    request = get_current_request()

    if request:
        return request.site.siteconfiguration

    raise MissingRequestError


def get_ecommerce_url(path=''):
    """
    Returns path joined with the appropriate ecommerce URL root for the current site

    Raises:
        MissingRequestError: If the current ecommerce site is not in threadlocal storage
    """
    site_configuration = _get_site_configuration()
    return site_configuration.build_ecommerce_url(path)


def get_lms_dashboard_url():
    site_configuration = _get_site_configuration()
    return site_configuration.student_dashboard_url


def get_lms_enrollment_api_url():
    # TODO Update consumers of this method to use `get_lms_enrollment_base_api_url` (which should be renamed
    # get_lms_enrollment_api_url).
    return get_lms_url('/api/enrollment/v1/enrollment')


def get_lms_enrollment_base_api_url():
    """ Returns the Base lms enrollment api url."""
    site_configuration = _get_site_configuration()
    return site_configuration.enrollment_api_url


def get_lms_url(path=''):
    """
    Returns path joined with the appropriate LMS URL root for the current site

    Raises:
        MissingRequestError: If the current ecommerce site is not in threadlocal storage
    """
    site_configuration = _get_site_configuration()
    return site_configuration.build_lms_url(path)


def get_oauth2_provider_url():
    site_configuration = _get_site_configuration()
    return site_configuration.oauth2_provider_url
