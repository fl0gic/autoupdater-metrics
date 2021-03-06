# metrics/resources/plugins.py
"""Holds the API's for plugins and plugin updates."""
import datetime
import uuid
from collections import Iterable
from uuid import UUID

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource

from metrics.database.models import Plugin, SpigotPlugin, PluginUpdate

EPOCH = datetime.datetime.utcfromtimestamp(0)


# noinspection PyUnusedLocal
def _cleanup(obj):
    """Properly formats DB response for JSON output."""
    if isinstance(obj, Iterable) and sum(1 for e in obj) == 0:
        return None

    if isinstance(obj, dict):
        plugin_dict = {}
        for (key, val) in obj.items():
            val = _cleanup(val)
            if val is None:
                continue
            if key == "_cls":
                key = "type"
            if key.startswith('_'):
                key = key[1:]
            plugin_dict[key] = val
        return plugin_dict
    elif isinstance(obj, list):
        return [_cleanup(i) for i in obj]
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime.datetime):
        return int((obj - EPOCH).total_seconds())
    else:
        return obj


class PluginsAPI(Resource):
    """API for groups of plugins"""

    @staticmethod
    def get():
        """
        Gets the ids of all plugins in the database, or if a request body is provided,
        a specific query can be sent.

        Default query limit is 20, can be specified with limit arg, max 300.

        :return: The list of plugins from the database, and all their info.
        """
        args = request.args

        limit = 20

        if 'limit' in args:
            limit = int(args['limit'])
            if limit > 300:
                limit = 300

        plugin_query = {k: v for (k, v) in args.items() if k != 'limit' and k != 'type'}

        # Map values to be proper booleans.
        plugin_query.update({k: (v.lower() == 'true') for (k, v) in plugin_query.items()
                             if v.lower() == 'true' or v.lower() == 'false'})

        if 'type' in args and 'spigot' in args['type']:
            plugins = SpigotPlugin.objects(**plugin_query).only('id', 'name').limit(limit)
        else:
            plugins = Plugin.objects(**plugin_query).only('id', 'name').limit(limit)

        if len(plugins) == 0:
            return {'error': 'Query returned no response.'}, 404

        plugins = _cleanup([pl.to_mongo() for pl in plugins])

        return plugins, 200

    @jwt_required
    def post(self):
        """
        Add a plugin to the database.
        :return: The id of the plugin in the database.
        """
        body = request.get_json()
        args = request.args

        if ('type' in args and 'spigot' in args['type']) or 'spigot_name' in body:
            plugin = SpigotPlugin(**body)
        else:
            plugin = Plugin(**body)

        plugin.id = uuid.uuid4()

        for update in plugin.updates:
            if update.server_id is None or len(update.server_id) == 0:
                update.server_id = get_jwt_identity()

        duplicates = Plugin.objects(name=plugin.name,
                                    description=plugin.description,
                                    download_url=plugin.download_url)

        if len(duplicates) > 0:
            return {'msg': 'Document already exists.'}, 400

        plugin.save()
        return {'id': str(plugin.id)}, 200


class PluginAPI(Resource):
    """API for individual plugins, specified in the request."""

    # FORMAT FOR DATES IS Y-m-D H:M:S
    @jwt_required
    def put(self, plugin_id):
        """
        Updates info for a specific plugin in the database.
        :param plugin_id: The id of the plugin being updated.
        :return: The plugin information from the db.
        """
        body = request.get_json()
        try:
            updated_doc_count = Plugin.objects.filter(id=plugin_id).update(**body)
        except ValueError:
            updated_doc_count = 0

        if updated_doc_count > 0:
            return '', 200
        else:
            return {'msg': 'No documents found under that id.'}, 404

    @jwt_required
    def delete(self, plugin_id):
        """
        Delete a specific plugin from the database.
        :param plugin_id: The id of the plugin to delete.
        :return: A http response code.
        """
        deleted_doc_count = Plugin.objects.filter(id=plugin_id).delete()

        if deleted_doc_count > 0:
            return '', 200
        else:
            return {'msg': 'No documents found under that id.'}, 404

    @staticmethod
    def get(plugin_id):
        """
        Get info for a specific plugin from the database.
        :param plugin_id: The id of the plugin to retrieve the info of.
        :return: The plugin information from the db.
        """
        update = _cleanup(Plugin.objects(id=plugin_id).first_or_404().to_mongo())
        return update, 200


class UpdatesAPI(Resource):
    """API for adding and getting specific plugins from the database."""

    @staticmethod
    def get(plugin_id):
        """
        Gets all updates from a specific plugin.
        :param plugin_id: The name of the plugin to retrieve the updates of.
        :return: The updates of the given plugin.
        """
        updates = Plugin.objects.only('updates').get_or_404(id=plugin_id)
        return _cleanup(updates.to_mongo()['updates']), 200

    @jwt_required
    def post(self, plugin_id):
        """
        Add an update to a specific plugin.
        :param plugin_id: The name of the plugin to add an update entry for.
        :return: A http response code.
        """
        body = request.get_json()
        plugin = Plugin.objects.get(id=plugin_id)
        plugin_update = PluginUpdate(**body)
        plugin_update.server_id = get_jwt_identity()
        plugin.updates.append(plugin_update)
        plugin.save()
        return '', 200
