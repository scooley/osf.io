import pytest

import datetime as dt

from modularodm import StoredObject
import pytz

from framework.exceptions import PermissionsError
from framework.auth import Auth
from website.util import permissions
from website.project import model as project_model
from framework.guid import model as guid_model
from website.project import taxonomies

from osf_models.models import Preprint

from .factories import PreprintFactory, PreprintProviderFactory, UserFactory, SubjectFactory
from .utils import set_up_ephemeral_storage

pytestmark = pytest.mark.django_db

@pytest.fixture()
def user():
    return UserFactory()

@pytest.fixture()
def auth(user):
    return Auth(user)

@pytest.fixture()
def preprint(user):
    return PreprintFactory(creator=user)

def test_factory(user):
    preprint = PreprintFactory(creator=user)
    assert preprint.is_preprint is True
    assert preprint.is_public


class TestMigrateFromModm:

    def test_migrate_from_modm(self, fake):
        # Ensure that we are dealing with the unpatched StoredObject models
        reload(project_model)
        reload(guid_model)
        reload(taxonomies)
        assert issubclass(project_model.Node, StoredObject)
        assert issubclass(guid_model.Guid, StoredObject)
        assert issubclass(taxonomies.Subject, StoredObject)
        set_up_ephemeral_storage([project_model.Node, guid_model.Guid, taxonomies.Subject])

        subject1, subject2 = taxonomies.Subject(text=fake.word()), taxonomies.Subject(text=fake.word())
        subject1.save()
        subject2.save()

        preprint_created = dt.datetime.utcnow()

        node = project_model.Node(
            preprint_subjects=[subject1, subject2],
            preprint_created=preprint_created,
            is_public=True,
            preprint_doi='10.123/42',
            _is_preprint_orphan=True
        )
        node._id = 'abcde'

        django_obj = Preprint.migrate_from_modm(node)

        assert django_obj._id == 'abcde'
        assert django_obj.preprint_created == node.preprint_created.replace(tzinfo=pytz.utc)
        assert django_obj.doi == node.preprint_doi
        assert django_obj._is_orphan == node._is_preprint_orphan

class TestPreprintProviders:

    @pytest.fixture()
    def provider(self):
        return PreprintProviderFactory()

    def test_add_provider(self, preprint, provider):
        assert preprint.providers.count() == 0  # sanity check

        preprint.add_preprint_provider(provider, user=preprint.creator, save=True)
        assert list(preprint.providers.all()) == [provider]

    def test_add_provider_errors_if_not_admin(self, preprint, provider):
        non_admin = UserFactory()
        preprint.add_contributor(non_admin, auth=Auth(preprint.creator), permissions=[permissions.READ, permissions.WRITE])
        with pytest.raises(PermissionsError):
            preprint.add_preprint_provider(provider, user=non_admin)

    def test_remove_provider(self, preprint, provider):
        preprint.add_preprint_provider(provider, user=preprint.creator, save=True)
        preprint.remove_preprint_provider(provider, user=preprint.creator, save=True)
        assert provider not in list(preprint.providers.all())

    def test_remove_provider_errors_if_not_admin(self, preprint, provider):
        non_admin = UserFactory()
        preprint.add_contributor(non_admin, auth=Auth(preprint.creator), permissions=[permissions.READ, permissions.WRITE])
        with pytest.raises(PermissionsError):
            preprint.remove_preprint_provider(provider, user=non_admin)

class TestPreprintSubjects:

    def test_set_preprint_subjects_basic(self, preprint, auth):
        subject1, subject2 = SubjectFactory(), SubjectFactory()
        preprint.set_preprint_subjects([subject1._id, subject2._id], auth=auth)

        assert subject1 in preprint.subjects.all()
        assert subject2 in preprint.subjects.all()

    def test_set_preprint_subjects_clears_previous_subjects(self, preprint, auth):
        subject1, subject2 = SubjectFactory(), SubjectFactory()
        preprint.set_preprint_subjects([subject1._id], auth=auth)
        assert subject1 in preprint.subjects.all()
        assert subject2 not in preprint.subjects.all()

        preprint.set_preprint_subjects([subject2._id], auth=auth)
        assert subject1 not in preprint.subjects.all()
        assert subject2 in preprint.subjects.all()

    def test_set_preprint_subjects_raises_an_error_if_user_not_admin(self, preprint):
        subject = SubjectFactory()
        non_admin = UserFactory()
        preprint.add_contributor(non_admin, auth=Auth(preprint.creator), permissions=[permissions.READ, permissions.WRITE])
        with pytest.raises(PermissionsError):
            preprint.set_preprint_subjects([subject._id], auth=Auth(non_admin))


class TestPreprintFiles:

    @pytest.mark.skip('StoredFileNode not yet implemented')
    def test_set_preprint_file(self, preprint, auth, fake):
        filename = fake.file_name()
        file = OsfStorageFile.create(
            is_file=True,
            node=preprint,
            path='/{}'.format(filename),
            name=filename,
            materialized_path='/{}'.format(filename))
        file.save()
        preprint.set_preprint_file(file, auth=auth)
        preprint.save()
        assert preprint.file == file

    def test_set_preprint_file_errors_if_user_not_admin(self, preprint):
        subject = SubjectFactory()
        non_admin = UserFactory()
        preprint.add_contributor(non_admin, auth=Auth(preprint.creator), permissions=[permissions.READ, permissions.WRITE])
        with pytest.raises(PermissionsError):
            preprint.set_preprint_file([subject._id], auth=Auth(non_admin))
