import pytz
from django.apps import apps
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from framework.analytics import increment_user_activity_counters
from osf.models.node_relation import NodeRelation
from osf.models.nodelog import NodeLog
from osf.models.tag import Tag
from website.exceptions import NodeStateError


class Versioned(models.Model):
    """A Model mixin class that saves delta versions."""

    @classmethod
    def _sig_pre_delete(cls, instance, *args, **kwargs):
        """dispatch the pre_delete method to a regular instance method. """
        return instance.sig_pre_delete(*args, **kwargs)

    @classmethod
    def _sig_post_delete(cls, instance, *args, **kwargs):
        """dispatch the post_delete method to a regular instance method. """
        return instance.sig_post_delete(*args, **kwargs)

    @classmethod
    def _sig_pre_save(cls, instance, *args, **kwargs):
        """dispatch the pre_save method to a regular instance method. """
        return instance.sig_pre_save(*args, **kwargs)

    @classmethod
    def _sig_post_save(cls, instance, *args, **kwargs):
        """dispatch the post_save method to a regular instance method. """
        return instance.sig_post_save(*args, **kwargs)

    @classmethod
    def connect(cls, signal):
        """Connect a django signal with this model."""
        # List all signals you want to connect with here:
        from django.db.models.signals import (pre_save, post_save, pre_delete, post_delete)
        sig_handler = {
            pre_save: cls._sig_pre_save,
            post_save: cls._sig_post_save,
            pre_delete: cls._sig_pre_delete,
            post_delete: cls._sig_post_delete,
        }[signal]
        signal.connect(sig_handler, sender=cls)

    class Meta:
        abstract = True


class Loggable(models.Model):
    # TODO: This should be in the NodeLog model

    def add_log(self, action, params, auth, foreign_user=None, log_date=None, save=True, request=None):
        AbstractNode = apps.get_model('osf.AbstractNode')
        user = None
        if auth:
            user = auth.user
        elif request:
            user = request.user

        params['node'] = params.get('node') or params.get('project') or self._id
        original_node = AbstractNode.load(params.get('node'))
        log = NodeLog(
            action=action, user=user, foreign_user=foreign_user,
            params=params, node=self, original_node=original_node
        )

        if log_date:
            log.date = log_date
        log.save()

        if self.logs.count() == 1:
            self.date_modified = log.date.replace(tzinfo=pytz.utc)
        else:
            self.date_modified = self.logs.first().date

        if save:
            self.save()
        if user:
            increment_user_activity_counters(user._primary_key, action, log.date.isoformat())

        return log

    class Meta:
        abstract = True


class Taggable(models.Model):

    tags = models.ManyToManyField('Tag', related_name='tagged')

    def add_tag(self, tag, auth=None, save=True, log=True, system=False):
        if not system and not auth:
            raise ValueError('Must provide auth if adding a non-system tag')

        if not isinstance(tag, Tag):
            tag_instance, created = Tag.objects.get_or_create(name=tag, system=system)
        else:
            tag_instance = tag

        if not self.tags.filter(id=tag_instance.id).exists():
            self.tags.add(tag_instance)
            if log:
                self.add_tag_log(tag_instance, auth)
            if save:
                self.save()
        return tag_instance

    def add_system_tag(self, tag, save=True):
        return self.add_tag(tag=tag, auth=None, save=save, log=False, system=True)

    def add_tag_log(self, *args, **kwargs):
        raise NotImplementedError('Logging requires that add_tag_log method is implemented')

    class Meta:
        abstract = True


# TODO: Implement me
class AddonModelMixin(models.Model):

    # from addons.base.apps import BaseAddonConfig
    settings_type = None
    ADDONS_AVAILABLE = [config for config in apps.get_app_configs() if config.name.startswith('addons.') and
        config.label != 'base']

    class Meta:
        abstract = True

    @classmethod
    def get_addon_key(cls, config):
        return 2 << cls.ADDONS_AVAILABLE.index(config)

    @property
    def addons(self):
        return self.get_addons()

    def get_addons(self):
        return filter(None, [
            self.get_addon(config.label)
            for config in self.ADDONS_AVAILABLE
        ])

    def has_addon(self, name):
        return True

    def get_addon_names(self):
        return [each.short_name for each in self.get_addons()]

    def get_or_add_addon(self, name, *args, **kwargs):
        addon = self.get_addon(name)
        if addon:
            return addon
        return self.add_addon(name, *args, **kwargs)

    def get_addon(self, name, deleted=False):
        try:
            settings_model = self._settings_model(name)
        except LookupError:
            return None
        if not settings_model:
            return None
        try:
            settings_obj = settings_model.objects.get(owner=self)
            if not settings_obj.deleted or deleted:
                return settings_obj
        except ObjectDoesNotExist:
            pass
        return None

    def add_addon(self, name):
        addon = self.get_addon(name, deleted=True)
        if addon:
            if addon.deleted:
                addon.undelete(save=True)
                return addon

        config = apps.get_app_config('addons_{}'.format(name))
        model = self._settings_model(name, config=config)
        ret = model(owner=self)
        ret.on_add()
        ret.save()  # TODO This doesn't feel right
        return ret

    def config_addons(self, config, auth=None, save=True):
        pass

    def delete_addon(self, name, auth=None):
        addon = self.get_addon(name)
        if not addon:
            return False
        # TODO
        # config = apps.get_app_config(name)
        # if self._meta.model_name in config.added_mandatory:
        #     raise ValueError('Cannot delete mandatory add-on.')
        if getattr(addon, 'external_account', None):
            addon.deauthorize(auth=auth)
        addon.delete(save=True)
        return True

    def _settings_model(self, name, config=None):
        if not config:
            config = apps.get_app_config(name)
        return getattr(config, '{}_settings'.format(self.settings_type))


class NodeLinkMixin(models.Model):

    class Meta:
        abstract = True

    def add_node_link(self, node, auth, save=True):
        """Add a node link to a node.

        :param Node node: Node to add
        :param Auth auth: Consolidated authorization
        :param bool save: Save changes
        :return: Created pointer
        """
        # Fail if node already in nodes / pointers. Note: cast node and node
        # to primary keys to test for conflicts with both nodes and pointers
        # contained in `self.nodes`.
        if NodeRelation.objects.filter(parent=self, child=node, is_node_link=True).exists():
            raise ValueError(
                'Link to node {0} already exists'.format(node._id)
            )

        if self.is_registration:
            raise NodeStateError('Cannot add a node link to a registration')

        # If a folder, prevent more than one pointer to that folder.
        # This will prevent infinite loops on the project organizer.
        if node.is_collection and node.linked_from.exists():
            raise ValueError(
                'Node link to folder {0} already exists. '
                'Only one node link to any given folder allowed'.format(node._id)
            )
        if node.is_collection and node.is_bookmark_collection:
            raise ValueError(
                'Node link to bookmark collection ({0}) not allowed.'.format(node._id)
            )

        # Append node link
        node_relation, created = NodeRelation.objects.get_or_create(
            parent=self,
            child=node,
            is_node_link=True
        )

        # Add log
        if hasattr(self, 'add_log'):
            self.add_log(
                action=NodeLog.NODE_LINK_CREATED,
                params={
                    'parent_node': self.parent_id,
                    'node': self._id,
                    'pointer': {
                        'id': node._id,
                        'url': node.url,
                        'title': node.title,
                        'category': node.category,
                    },
                },
                auth=auth,
                save=False,
            )

        # Optionally save changes
        if save:
            self.save()

        return node_relation

    add_pointer = add_node_link  # For v1 compat

    def rm_node_link(self, node_relation, auth):
        """Remove a pointer.

        :param Pointer pointer: Pointer to remove
        :param Auth auth: Consolidated authorization
        """
        try:
            node_rel = self.node_relations.get(is_node_link=True, id=node_relation.id)
        except NodeRelation.DoesNotExist:
            raise ValueError('Node link does not belong to the requested node.')
        else:
            node_rel.delete()

        node = node_relation.child
        # Add log
        if hasattr(self, 'add_log'):
            self.add_log(
                action=NodeLog.POINTER_REMOVED,
                params={
                    'parent_node': self.parent_id,
                    'node': self._primary_key,
                    'pointer': {
                        'id': node._id,
                        'url': node.url,
                        'title': node.title,
                        'category': node.category,
                    },
                },
                auth=auth,
                save=False,
            )

    rm_pointer = rm_node_link  # For v1 compat

    @property
    def nodes_pointer(self):
        """For v1 compat"""
        return self.linked_nodes

    def get_points(self, folders=False, deleted=False):
        query = self.linked_from

        if not folders:
            query = query.exclude(type='osf.collection')

        if not deleted:
            query = query.exclude(is_deleted=True)

        return list(query.all())

    def fork_node_link(self, node_relation, auth, save=True):
        """Replace a linked node with a fork.

        :param NodeRelation node_relation:
        :param Auth auth:
        :param bool save:
        :return: Forked node
        """
        # Fail if pointer not contained in `nodes`
        try:
            node = self.node_relations.get(is_node_link=True, id=node_relation.id).child
        except NodeRelation.DoesNotExist:
            raise ValueError('Node link {0} not in list'.format(node_relation._id))

        # Fork into current node and replace pointer with forked component
        forked = node.fork_node(auth)
        if forked is None:
            raise ValueError('Could not fork node')

        relation = NodeRelation.objects.get(
            parent=self,
            child=node,
            is_node_link=True
        )
        relation.child = forked
        relation.save()

        if hasattr(self, 'add_log'):
            # Add log
            self.add_log(
                NodeLog.NODE_LINK_FORKED,
                params={
                    'parent_node': self.parent_id,
                    'node': self._id,
                    'pointer': {
                        'id': node._id,
                        'url': node.url,
                        'title': node.title,
                        'category': node.category,
                    },
                },
                auth=auth,
                save=False,
            )

        # Optionally save changes
        if save:
            self.save()

        # Return forked content
        return forked

    fork_pointer = fork_node_link  # For v1 compat


class CommentableMixin(object):
    """Abstract class that defines the interface for models that have comments attached to them."""

    @property
    def target_type(self):
        """ The object "type" used in the OSF v2 API. E.g. Comment objects have the type 'comments'."""
        raise NotImplementedError

    @property
    def root_target_page(self):
        """The page type associated with the object/Comment.root_target.
        E.g. For a NodeWikiPage, the page name is 'wiki'."""
        raise NotImplementedError

    is_deleted = False

    def belongs_to_node(self, node_id):
        """Check whether an object (e.g. file, wiki, comment) is attached to the specified node."""
        raise NotImplementedError

    def get_extra_log_params(self, comment):
        """Return extra data to pass as `params` to `Node.add_log` when a new comment is
        created, edited, deleted or restored."""
        return {}
