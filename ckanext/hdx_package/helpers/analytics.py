import json
import logging
import urlparse

import pylons.config as config
from ckanext.hdx_theme.util.analytics import AbstractAnalyticsSender

import ckan.controllers.package as package_controller
import ckan.lib.base as base
import ckan.logic as logic
import ckan.model as model
from ckan.common import _, c, request

log = logging.getLogger(__name__)


def is_indicator(pkg_dict):
    if int(pkg_dict.get('indicator', 0)) == 1:
        return 'true'
    return 'false'


def is_cod(pkg_dict):
    tags = [tag.get('name', '') for tag in pkg_dict.get('tags', [])]
    if 'cod' in tags:
        return 'true'
    return 'false'


def is_private(pkg_dict):
    if pkg_dict.get('private'):
        return 'true'
    return 'false'


# def is_protected(pkg_dict):
#     if pkg_dict.get('is_requestdata_type'):
#         return 'true'
#     return 'false'


def dataset_availability(pkg_dict):
    if pkg_dict.get('is_requestdata_type'):
        level = 'metadata only'
    elif pkg_dict.get('private'):
        level = 'private'
    else:
        level = 'public'
    return level


def extract_locations(pkg_dict):
    locations = pkg_dict.get('groups', [])
    location_names = []
    location_ids = []
    for l in sorted(locations, key=lambda item: item.get('name', '')):
        location_names.append(l.get('name', ''))
        location_ids.append(l.get('id', ''))

    return location_names, location_ids


def extract_locations_in_json(pkg_dict):
    locations = pkg_dict.get('groups', [])
    location_names = []
    location_ids = []
    for l in sorted(locations, key=lambda item: item.get('name', '')):
        location_names.append(l.get('name', ''))
        location_ids.append(l.get('id', ''))

    return json.dumps(location_names), json.dumps(location_ids)


def _ga_dataset_type(is_indicator, is_cod):
    '''
    :param is_indicator:
    :type is_indicator: bool
    :param is_cod:
    :type is_cod: bool
    :return:  standard / indicator / cod / cod~indicator
    :rtype: str
    '''

    type = 'standard'
    if is_indicator:
        type = 'indicator'
    if is_cod:
        type = 'cod~indicator' if type == 'indicator' else 'cod'

    return type


def generate_analytics_data(dataset_dict):
    # in case of an edit event we populate the analytics info

    # it's going to be used mostly in JSON so using camelCase
    analytics_dict = {}
    if dataset_dict and dataset_dict.get('id'):
        analytics_dict['datasetId'] = dataset_dict['id']
        analytics_dict['datasetName'] = dataset_dict['name']
        analytics_dict['organizationName'] = dataset_dict.get('organization', {}).get('name') \
                                                if dataset_dict.get('organization') else None
        analytics_dict['organizationId'] = dataset_dict.get('organization', {}).get('name') \
                                                if dataset_dict.get('organization') else None
        analytics_dict['isCod'] = is_cod(dataset_dict)
        analytics_dict['isIndicator'] = is_indicator(dataset_dict)
        analytics_dict['groupNames'], analytics_dict['groupIds'] = extract_locations_in_json(dataset_dict)
        analytics_dict['datasetAvailability'] = dataset_availability(dataset_dict)
    else:
        analytics_dict['datasetId'] = ''
        analytics_dict['datasetName'] = ''
        analytics_dict['organizationName'] = ''
        analytics_dict['organizationId'] = ''
        analytics_dict['isCod'] = 'false'
        analytics_dict['isIndicator'] = 'false'
        analytics_dict['groupNames'] = '[]'
        analytics_dict['groupIds'] = '[]'
        analytics_dict['datasetAvailability'] = None
    return analytics_dict


def _ga_location(location_names):
    '''
    :param location_names:
    :type location_names: list[str]
    :return:
    :rtype: str
    '''
    limit = 15
    if len(location_names) >= limit:
        result = 'many'
    else:
        result = "~".join(location_names)

    if not result:
        result = 'none'

    return result


def wrap_resource_download_function():
    '''
    Changes the original resource_download function from the package controller with a version that
    wraps the original function but also enqueues the tracking events
    '''
    original_resource_download = package_controller.PackageController.resource_download

    def new_resource_download(self, id, resource_id, filename=None):

        send_event = True
        referer_url = request.referer

        if referer_url:
            ckan_url = config.get('ckan.site_url', '//localhost:5000')
            ckan_parsed_url = urlparse.urlparse(ckan_url)
            referer_parsed_url = urlparse.urlparse(referer_url)

            if ckan_parsed_url.hostname == referer_parsed_url.hostname:
                send_event = False

        if send_event:
            ResourceDownloadAnalyticsSender(id, resource_id).send_to_queue()

        return original_resource_download(self, id, resource_id, filename)

    package_controller.PackageController.resource_download = new_resource_download


class ResourceDownloadAnalyticsSender(AbstractAnalyticsSender):

    def __init__(self, package_id, resource_id):
        super(ResourceDownloadAnalyticsSender, self).__init__()

        log.debug('The user IP address was {}'.format(self.user_addr))

        try:
            context = {'model': model, 'session': model.Session,
                       'user': c.user or c.author, 'auth_user_obj': c.userobj}
            dataset_dict = logic.get_action('package_show')(context, {'id': package_id})
            resource_dict = next(r for r in dataset_dict.get('resources', {}) if r.get('id') == resource_id)
            location_names, location_ids = extract_locations(dataset_dict)

            dataset_title = dataset_dict.get('title', dataset_dict.get('name'))
            dataset_is_cod = is_cod(dataset_dict) == 'true'
            dataset_is_indicator = is_indicator(dataset_dict) == 'true'
            authenticated = True if c.userobj else False

            self.analytics_dict = {
                'event_name': 'resource download',
                'mixpanel_meta': {
                    "resource name": resource_dict.get('name'),
                    "resource id": resource_dict.get('id'),
                    "dataset name": dataset_dict.get('name'),
                    "dataset id": dataset_dict.get('id'),
                    "org name": dataset_dict.get('organization', {}).get('name'),
                    "org id": dataset_dict.get('organization', {}).get('id'),
                    "group names": location_names,
                    "group ids": location_ids,
                    "is cod": dataset_is_cod,
                    "is indicator": dataset_is_indicator,
                    "authenticated": authenticated,
                    'event source': 'direct'
                },
                'ga_meta': {
                    'ec': 'resource',  # event category
                    'ea': 'download',  # event action
                    'el': u'{} ({})'.format(resource_dict.get('name'), dataset_title),  # event label
                    'cd1': dataset_dict.get('organization', {}).get('name'),
                    'cd2': _ga_dataset_type(dataset_is_indicator, dataset_is_cod),  # type
                    'cd3': _ga_location(location_names),  # locations

                }
            }

        except logic.NotFound:
            base.abort(404, _('Resource not found'))
        except logic.NotAuthorized:
            base.abort(403, _('Unauthorized to read resource %s') % id)
        except Exception, e:
            log.error('Unexpected error {}'.format(e))



def analytics_wrapper_4_package_create(original_package_action):

    def package_action(context, package_dict):

        result_dict = original_package_action(context, package_dict)

        # if the package doesn't come from the contribute flow UI form and is a normal dataset (aka not a showcase)
        # then send the even from the server side
        if not context.get('contribute_flow') and (
                package_dict.get('type') == 'dataset' or not package_dict.get('type')):
            DatasetCreatedAnalyticsSender(result_dict).send_to_queue()

        return result_dict

    return package_action

class DatasetCreatedAnalyticsSender(AbstractAnalyticsSender):

    def __init__(self, dataset_dict):
        super(DatasetCreatedAnalyticsSender, self).__init__()

        location_names, location_ids = extract_locations(dataset_dict)
        dataset_is_cod = is_cod(dataset_dict) == 'true'
        dataset_is_indicator = is_indicator(dataset_dict) == 'true'
        dataset_is_private = is_private(dataset_dict) == 'true'
        dataset_availability_level = dataset_availability(dataset_dict) == 'true'



        self.analytics_dict = {
            'event_name': 'dataset create',
            'mixpanel_meta': {
                'event source': 'api',
                'group names': location_names,
                'group ids': location_ids,
                'org_name': (dataset_dict.get('organization') or {}).get('name'),
                'org_id': (dataset_dict.get('organization') or {}).get('id'),
                'is cod': dataset_is_cod,
                'is indicator': dataset_is_indicator,
                'is private': dataset_is_private,
                'dataset availability': dataset_availability_level
            },
            'ga_meta': {
                'ec': 'dataset',  # event category
                'ea': 'create',  # event action
                # There is no event label because that would correspond to the page title and this doesn't exist on the
                # server side
                'cd1': (dataset_dict.get('organization') or {}).get('name'),
                'cd2': _ga_dataset_type(dataset_is_indicator, dataset_is_cod),  # type
                'cd3': _ga_location(location_names),  # locations

            }
        }
