# -*- coding: utf-8 -*-
import httplib as http
import logging

from framework import request
from framework.exceptions import HTTPError
from framework.auth.decorators import must_be_logged_in
from ..decorators import must_not_be_registration, must_be_valid_project, \
    must_be_contributor, must_be_contributor_or_public

from framework.forms.utils import sanitize
from website.models import Guid, Comment


logger = logging.getLogger(__name__)

def resolve_target(node, guid):

    if not guid:
        return node
    target = Guid.load(guid)
    if target is None:
        raise HTTPError(http.BAD_REQUEST)
    return target.referent


def serialize_comment(comment, node, auth):

    return {
        'id': comment._id,
        'author': {
            'id': comment.user._id,
            'name': comment.user.fullname,
        },
        'dateCreated': comment.date_created.strftime('%c'),
        'dateModified': comment.date_modified.strftime('%c'),
        'content': comment.content,
        'isPublic': comment.is_public,
        'hasChildren': bool(getattr(comment, 'commented', [])),
        'canEdit': comment.user == auth.user,
        'canDelete': node.can_edit(auth),
        'modified': comment.modified,
        'isSpam': auth.user and
            comment.reports.get(auth.user._id) == {'type': 'spam'},
    }


def can_view_comment(comment, node, auth):

    if comment.is_public:
        return True

    return node.can_edit(auth)


def serialize_comments(record, node, auth):

    return [
        serialize_comment(comment, node, auth)
        for comment in getattr(record, 'commented', [])
        if can_view_comment(comment, node, auth)
            and not comment.is_deleted
    ]


@must_be_logged_in
@must_be_contributor_or_public
def add_comment(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if not node.can_comment(auth):
        raise HTTPError(http.BAD_REQUEST)

    guid = request.json.get('target')
    target = resolve_target(node, guid)

    content = request.json.get('content')
    if content is None:
        raise HTTPError(http.BAD_REQUEST)
    content = sanitize(content)

    is_public = request.json.get('isPublic')
    if is_public is None:
        raise HTTPError(http.BAD_REQUEST)

    comment = Comment(
        target=target,
        user=auth.user,
        is_public=is_public,
        content=content,
    )
    comment.save()

    return {
        'comment': serialize_comment(comment, node, auth)
   }, http.CREATED


@must_be_contributor_or_public
def list_comments(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if not node.can_comment(auth):
        return

    guid = request.args.get('target')
    target = resolve_target(node, guid)

    return {
        'comments': serialize_comments(target, node, auth),
    }


@must_be_logged_in
@must_be_contributor_or_public
def edit_comment(**kwargs):

    auth = kwargs['auth']

    comment = Comment.load(request.json.get('cid'))
    if comment is None:
        raise HTTPError(http.BAD_REQUEST)

    if auth.user != comment.user:
        raise HTTPError(http.FORBIDDEN)

    content = request.json.get('content')
    if content is None:
        raise HTTPError(http.BAD_REQUEST)

    is_public = request.json.get('isPublic')
    if is_public is None:
        raise HTTPError(http.BAD_REQUEST)

    comment.content = sanitize(content)
    comment.is_public = is_public
    comment.modified = True

    comment.save()

    return {
        'content': content,
    }


@must_be_logged_in
@must_be_contributor_or_public
def delete_comment(**kwargs):

    auth = kwargs['auth']

    comment = Comment.load(kwargs.get('cid'))
    if comment is None:
        raise HTTPError(http.BAD_REQUEST)

    if auth.user != comment.user:
        raise HTTPError(http.FORBIDDEN)

    comment.delete(save=True)


@must_be_logged_in
@must_be_contributor_or_public
def report_spam(**kwargs):

    auth = kwargs['auth']
    user = auth.user

    comment = Comment.load(kwargs.get('cid'))
    if comment is None:
        raise HTTPError(http.BAD_REQUEST)

    is_spam = request.json.get('isSpam')
    if is_spam is None:
        raise HTTPError(http.BAD_REQUEST)

    if is_spam:
        comment.report_spam(user, save=True)
    else:
        try:
            comment.unreport_spam(user, save=True)
        except ValueError:
            raise HTTPError(http.BAD_REQUEST)
