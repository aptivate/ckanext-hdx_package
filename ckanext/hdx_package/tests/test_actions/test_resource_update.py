'''
Created on Dec 24, 2014

@author: alexandru-m-g
'''

import logging as logging

import ckan.model as model

import ckanext.hdx_theme.tests.hdx_test_base as hdx_test_base
import ckanext.hdx_theme.tests.hdx_test_with_inds_and_orgs as hdx_test_with_inds_and_orgs

log = logging.getLogger(__name__)


class TestHDXUpdateResource(hdx_test_with_inds_and_orgs.HDXWithIndsAndOrgsTest):

    @classmethod
    def _load_plugins(cls):
        hdx_test_base.load_plugin('hdx_package hdx_theme')

    def test_resource_update_metadata(self):

        field = 'last_data_update_date'
        new_field_value = '2014-12-10T23:04:22.596156'

        context = {'ignore_auth': True,
                   'model': model, 'session': model.Session, 'user': 'testsysadmin'}

        package = self._get_action('package_show')(
            context, {'id': 'test_private_dataset_1'})

        resource = self._get_action('resource_show')(
            context, {'id': package['resources'][0]['id']})

        original = resource.get(field, None)

        self._get_action('hdx_resource_update_metadata')(
            context, {'id': resource['id'], field: new_field_value})

        changed_resource = self._get_action('resource_show')(
            context, {'id': package['resources'][0]['id']})
        modified = changed_resource[field]

        assert original != modified, '{} should have been changed by action'.format(
            field)

    def test_resource_delete_metadata(self):
        context = {'ignore_auth': True,
                   'model': model, 'session': model.Session, 'user': 'testsysadmin'}

        package = self._get_action('package_show')(
            context, {'id': 'test_private_dataset_1'})

        resource = self._get_action('resource_show')(
            context, {'id': package['resources'][0]['id']})

        resource_v2 = self._get_action('hdx_resource_update_metadata')(
            context, {'id': resource['id'], 'test_field': 'test_extra_value'})

        # resource_v2 = self._get_action('resource_show')(
        #     context, {'id': package['resources'][0]['id']})

        assert len(resource_v2) - len(resource) == 1, "Test added just one field to the resource"

        resource_v3 = self._get_action('hdx_resource_delete_metadata')(
            context, {'id': resource['id'], 'field_list': ['test_field']})

        assert len(resource_v3) - len(resource) == 0, "Resources should be identical"

        try:
            resource_v4 = self._get_action('hdx_resource_delete_metadata')(
                context, {'id': resource['id'], 'field_list': ['shape']})
            assert True
        except:
            assert False, 'Exception when deleting nonexistent field'
