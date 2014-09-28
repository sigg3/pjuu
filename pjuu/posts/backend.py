# -*- coding: utf-8 -*-

"""
Description:
    The backend function for the post system.

    If in the future we decice to replace Redis we can simply change all these
    funtions to use a new backend

Licence:
    Copyright 2014 Joe Doherty <joe@pjuu.com>

    Pjuu is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Pjuu is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Stdlib
import re
# 3rd party imports
from flask import current_app as app, url_for
from jinja2.filters import do_capitalize
# Pjuu imports
from pjuu import redis as r
from pjuu.lib.alerts import BaseAlert, AlertManager
from pjuu.lib import keys as K, lua as L, timestamp
from pjuu.auth.backend import get_uid_username


# Regular expressions
# Used to match '@' tags in a post
tag_re = re.compile('(?:^|(?<=[^\w]))@'
                    '(\w{3,16})(?:$|(?=[\.\;\,\:\ \t]))')


# Subscription reasons
# You are the original poster
POSTER = 1

# You commented on the pose
COMMENTER = 2

# You have been tagged in the post
TAGEE = 3


class PostingAlert(BaseAlert):
    """
    Base form for all alerts used within the posts package.

    These are ALL related to posts and require additional information.
    """

    def __init__(self, uid, pid):
        # Call the BaseAlert __init__ method
        super(PostingAlert, self).__init__(uid)
        # Assign pid and ensure it is an int
        self.pid = int(pid)
        # Call Redis to get some additional information
        self.author_uid = int(r.hget(K.POST % pid, 'uid'))
        self.author_username = r.hget(K.USER % self.author_uid, 'username')

    def verify(self):
        """
        Overwrite the verify of BaseAlert to add checking the post exists
        """
        return r.exists(K.USER % self.uid) and r.exists(K.POST % self.pid)


class TaggingAlert(PostingAlert):

    def prettify(self, for_uid=None):
        return '<a href="{0}">{1}</a> tagged you in a <a href="{2}">post</a>' \
               .format(url_for('profile', username=self.get_username()),
                       do_capitalize(self.get_username()),
                       url_for('view_post', username=self.author_username,
                               pid=self.pid))


class CommentingAlert(PostingAlert):

    def prettify(self, for_uid):
        # Let's try and work out why this user is being notified of a comment
        reason = subscription_reason(for_uid, self.pid)

        if reason == POSTER:
            sr = 'posted'
        elif reason == COMMENTER:
            sr = 'commented on'
        elif reason == TAGEE:
            sr = 'were tagged in'
        else:
            # This should never really happen but let's play ball eh?
            sr = 'are subscribed too'

        return '<a href="{0}">{1}</a> ' \
               'commented on a <a href="{2}">post</a> you {3}' \
               .format(url_for('profile', username=self.get_username()),
                       do_capitalize(self.get_username()),
                       url_for('view_post', username=self.author_username,
                               pid=self.pid),
                       sr)


def parse_tags(body, send_all=False):
    """
    This function looks for '@' tags inside a post that match the regex.

    This is used by create_post and create_comment to alert users
    that they have been tagged in a post.

    The 'nameify' template_filter also uses this to identify tags before it
    inserts the links. See nameify_filter() in posts/views.py

    This returns a list of tuples (uid, username, tag, span)

    'send_all' allows the tag highlighting in nameify() to highlight
    all tags. This is not needed for alerts as someone can only subscribe
    once
    """
    tags = tag_re.finditer(body)

    results = []
    seen = []

    for tag in tags:
        # Check the tag is of an actual user
        uid = get_uid_username(tag.group(1))
        if uid is not None:
            # There is two versions one sends all tag locations and the other
            # deduplicates the list.
            if send_all:
                results.append((uid, tag.group(1), tag.group(0), tag.span()))
            elif uid not in seen:
                results.append((uid, tag.group(1), tag.group(0), tag.span()))
                seen.append(uid)

    return results


def populate_feeds(uid, pid):
    """
    This will cycle through all a users followers and append the pid to the
    left of their list.

    This will take care of getting the followers from Redis also.
    """
    # TODO This needs putting in to Celery->RabbitMQ at some point
    # as this could take a long long while.
    # This has been seperated in to tasks.py ready for this action.

    # Get a list of ALL users who are following a user
    followers = r.zrange(K.USER_FOLLOWERS % uid, 0, -1)
    # This is not transactional as to not hold Redis up.
    for fid in followers:
        fid = int(fid)
        # Add the pid to the list
        r.lpush(K.USER_FEED % fid, pid)
        # Stop followers feeds from growing to large, doesn't matter if it
        # doesn't exist
        r.ltrim(K.USER_FEED % fid, 0, 999)


def create_post(uid, body):
    """
    Creates a new post. Does all the other stuff to like prepend to feeds,
    post list, etc...
    """
    uid = int(uid)
    pid = int(r.incr(K.GLOBAL_PID))
    # Hash form for posts
    # TODO this needs expanding to include some form of image upload hook
    post = {
        'pid': pid,
        'uid': uid,
        'body': body,
        'created': timestamp(),
        'score': 0
    }
    # Transactional
    pipe = r.pipeline()
    # Add post
    pipe.hmset(K.POST % pid, post)
    # Add post to users post list
    pipe.lpush(K.USER_POSTS % uid, pid)
    # Add post to authors feed
    pipe.lpush(K.USER_FEED % uid, pid)
    # Ensure the feed does not grow to large
    pipe.ltrim(K.USER_FEED % uid, 0, 999)
    pipe.execute()
    # Append to all followers feeds
    populate_feeds(uid, pid)

    # Subscribe the poster to there post
    subscribe(uid, pid, POSTER)

    # Create alert manager and alert
    alert = TaggingAlert(uid, pid)
    # Alert tagees
    tagees = parse_tags(body)
    # Store a list of uids which need to alerted to the tagging
    tagees_to_alert = []
    for tagee in tagees:
        # Don't allow tagging yourself
        if tagee[0] != uid:
            # Subscribe the tagee to the alert
            subscribe(tagee[0], pid, TAGEE)
            # Add the tagee's uid to the list to alert them
            tagees_to_alert.append(tagee[0])

    # Alert the required tagees
    AlertManager().alert(alert, tagees_to_alert)

    return pid


def create_comment(uid, pid, body):
    """
    Create a new comment.
    """
    uid = int(uid)
    # Reserve the ID now. If the transaction fails we lost this ID
    cid = int(r.incr(K.GLOBAL_CID))
    pid = int(pid)
    # Form for comment hash
    comment = {
        'cid': cid,
        'uid': uid,
        'pid': pid,
        'body': body,
        'created': timestamp(),
        'score': 0
    }
    # Transactional
    pipe = r.pipeline()
    # Add comment
    pipe.hmset(K.COMMENT % cid, comment)
    # Add comment to posts comment list
    pipe.lpush(K.POST_COMMENTS % pid, cid)
    # Add comment to users comment list
    # This may seem redundant but it allows for perfect account deletion
    # Please see Issue #3 on Github
    pipe.lpush(K.USER_COMMENTS % uid, cid)
    pipe.execute()

    # COMMENT ALERTING

    # Alert all subscribers to the post that a new comment has been added.
    # We do this before subscribing anyone new
    # Create alert manager and alert
    alert = CommentingAlert(uid, pid)

    subscribers = []
    # Iterate through subscribers and let them know about the comment
    for subscriber in get_subscribers(pid):
        # ENsure subscriber is an int
        subscriber = int(subscriber)
        # Ensure we don't get alerted for our own comments
        if subscriber != uid:
            subscribers.append(subscriber)

    # Push the comment alert out to all subscribers
    AlertManager().alert(alert, subscribers)

    # Subscribe the user to the post, will not change anything if they are
    # already subscribed
    subscribe(uid, pid, COMMENTER)

    # TAGGING

    # Create alert
    alert = TaggingAlert(uid, pid)

    # Subscribe tagees
    tagees = parse_tags(body)
    tagees_to_alert = []
    for tagee in tagees:
        # Don't allow tagging yourself
        if tagee[0] != uid:
            subscribe(tagee[0], pid, TAGEE)
            tagees_to_alert.append(tagee[0])

    # Get an alert manager to notify all tagees
    AlertManager().alert(alert, tagees_to_alert)

    return cid


def check_post(uid, pid, cid=None):
    """
    This function will ensure that cid belongs to pid and pid belongs to uid.

    This function would not really be needed if we used a RDBMS but we have
    to manually check this.

    Warning: Think before testing. UID is the person wrote PID, CID if assigned
             has to be a comment of PID. This for checking the urls not for
             checking who wrote CID
    """
    try:
        uid = int(uid)
        pid = int(pid)

        # Check if cid is a comment of post pid
        if cid:
            cid = int(cid)
            pid_check = int(r.hget(K.COMMENT % cid, 'pid'))

            if int(pid_check) != pid:
                # No it isn't
                return False

        # Check that post was written by uid
        uid_check = int(r.hget(K.POST % pid, 'uid'))
        if uid_check != uid:
            return False

        # All was good
        return True

    except (TypeError, ValueError):
        # Something went wrong
        return False


def get_post(pid):
    """
    Returns a representation of a post along with data on the user
    """
    pid = int(pid)
    post = r.hgetall(K.POST % pid)

    if post:
        try:
            # Look up user and add data to the repr
            uid = int(post['uid'])
            user_dict = r.hgetall(K.USER % uid)

            post['user_username'] = user_dict['username']
            post['user_email'] = user_dict['email']
            post['user_score'] = user_dict['score']
            post['comment_count'] = r.llen(K.POST_COMMENTS % pid)
        except (KeyError, ValueError):
            return None
        else:
            return post
    # We never got a post
    return None


def get_comment(cid):
    """
    Returns a representation of a comment along with data on the user
    """
    cid = int(cid)
    comment = r.hgetall(K.COMMENT % cid)

    if comment:
        try:
            # Look up user and add data to the repr
            uid = int(comment['uid'])
            user_dict = r.hgetall(K.USER % uid)

            comment['user_username'] = user_dict['username']
            comment['user_email'] = user_dict['email']
            comment['user_score'] = user_dict['score']

            # We need the username from the parent pid to construct a URL
            pid = int(comment['pid'])
            author_uid = int(r.hget(K.POST % pid, 'uid'))
            # Although this key is called post_autor it is actually a username
            # and not a uid. get_post_author returns the authors uid.
            comment['post_author'] = r.hget(K.USER % author_uid, 'username')
        except (KeyError, ValueError):
            return None
        else:
            return comment
    # We never got a comment
    return None


def get_post_author(pid):
    """
    Returns UID of posts author
    """
    pid = int(pid)
    return int(r.hget(K.POST % pid, 'uid'))


def get_comment_author(cid):
    """
    Returns UID of comments author
    """
    cid = int(cid)
    return int(r.hget(K.COMMENT % cid, 'uid'))


def has_voted(uid, pid, cid=None):
    """
    Checks to see if uid has voted on a post.

    With return -1 if user downvoted, 1 if user upvoted and None if not voted
    """
    uid = int(uid)
    pid = int(pid)
    if cid is not None:
        cid = int(cid)
        result = r.zscore(K.COMMENT_VOTES % cid, uid)
    else:
        result = r.zscore(K.POST_VOTES % pid, uid)
    return result


def vote(uid, pid, cid=None, amount=1):
    """
    Handles all voting in Pjuu
    """
    uid = int(uid)
    pid = int(pid)
    # Ensure user has not voted before
    if not has_voted(uid, pid, cid):
        # Voting on a comment
        if cid is not None:
            cid = int(cid)
            author_uid = int(r.hget(K.COMMENT % cid, 'uid'))
            if author_uid != uid:
                r.zadd(K.COMMENT_VOTES % cid, amount, uid)
                # Comment scores can be negative
                r.hincrby(K.COMMENT % cid, 'score', amount=amount)

                # Get the score of the author
                current_user_score = r.hget(K.USER % author_uid, 'score')
                try:
                    current_user_score = int(current_user_score)
                    if current_user_score <= 0 and amount < 0:
                        amount = 0
                except (ValueError, TypeError):
                    # If we can not convert the score to an Int ignore it.
                    pass

                # The above code will stop the user going in to negative score
                r.hincrby(K.USER % author_uid, 'score', amount=amount)
                return True
        else:
            author_uid = int(r.hget(K.POST % pid, 'uid'))
            if author_uid != uid:
                r.zadd(K.POST_VOTES % pid, amount, uid)
                # Post scores can be negative
                r.hincrby(K.POST % pid, 'score', amount=amount)

                # Get the score of the author
                current_user_score = r.hget(K.USER % author_uid, 'score')
                try:
                    current_user_score = int(current_user_score)
                    if current_user_score <= 0 and amount < 0:
                        amount = 0
                except (ValueError, TypeError):
                    # If we can not convert the score to an Int ignore it.
                    pass

                # The above code will stop the user going in to negative score
                r.hincrby(K.USER % author_uid, 'score', amount=amount)
                return True

    return False


def delete_comments(uid, pid):
    """
    HUNGRY OTTER-ABLE

    This will cycle through a posts comments and remove each comment
    in turn. It will also remove the comment from the users comment list.

    It will then delete the list at the end.
    """
    uid = int(uid)
    pid = int(pid)

    cids = r.lrange(K.POST_COMMENTS % pid, 0, -1)
    for cid in cids:
        # Delete comment and votes
        cid = int(cid)
        # We need to get the comment authors uid so that we can remove the
        # comment from there user:$uid:comments list
        author_id = int(r.hget('comment:%d' % cid, 'uid'))
        # Delete the comment and remove from the posts list
        r.delete(K.COMMENT % cid)
        r.delete(K.COMMENT_VOTES % cid)
        # Delete the comment from the users comment list
        # This makes these lists self cleaning
        r.lrem(K.USER_COMMENTS % author_id, 0, cid)
    # Finally delete the comment list
    r.delete(K.POST_COMMENTS % pid)


def delete(uid, pid, cid=None):
    """
    Deletes a post/comment
    If this is a post it will delete all comments, all votes, etc...
    If this is a comment it will delete just this comment and its votes.
    This should not cause users to lose or gain points!

    Please ensure the user has permission to delete the item before
    passing to this, it will not check!
    """
    uid = int(uid)
    pid = int(pid)
    if cid:
        # Delete comment and votes
        cid = int(cid)
        # We need to get the comment authors uid so that we can remove the
        # comment from there user:$uid:comments list
        author_id = int(r.hget(K.COMMENT % cid, 'uid'))
        # Delete the comment and remove from the posts list
        r.delete(K.COMMENT % cid)
        r.delete(K.COMMENT_VOTES % cid)
        r.lrem(K.POST_COMMENTS % pid, 0, cid)
        # Delete the comment from the users comment list
        r.lrem(K.USER_COMMENTS % author_id, 0, cid)
        return True
    else:
        # Get the post authors ID
        author_id = int(r.hget(K.POST % pid, 'uid'))
        # Delete post, comments and votes
        r.delete(K.POST % pid)
        r.delete(K.POST_VOTES % pid)
        # Delete posts subscribers list
        r.delete(K.POST_SUBSCRIBERS % pid)
        # Delete the post from the users post list
        r.lrem(K.USER_POSTS % author_id, 0, pid)
        # Delete all comments on the post
        delete_comments(uid, pid)
        return True
    return False


def subscribe(uid, pid, reason):
    """
    Subscribes a user (uid) to post (pid) for reason.

    This is a helper function to make subscriptions easier. It will also ensure
    that post authors are not subscribed to there own posts.
    """
    # Esnure pid, uid and reason are all int's
    pid = int(pid)
    uid = int(uid)
    reason = int(reason)

    # Check that pid exsits if not do nothing
    if not r.exists(K.POST % pid):
        return False

    # Only subscribe the user if the user is not already subscribed
    # this will mean the original reason is kept
    return L.zadd_member_nx(keys=[K.POST_SUBSCRIBERS % pid],
                            args=[reason, uid])


def unsubscribe(uid, pid):
    """
    Unsubscribe a user from a post.

    This function always returns true if the user was unsubscribed
    """
    uid = int(uid)
    pid = int(pid)

    # Actually remove the uid from the subscribers list
    return bool(r.zrem(K.POST_SUBSCRIBERS % pid, uid))


def get_subscribers(pid):
    """
    Return a list of subscribers for a given post (pid)
    """
    pid = int(pid)

    return r.zrange(K.POST_SUBSCRIBERS % pid, 0, -1)


def is_subscribed(uid, pid):
    """
    Returns a boolean to denote if a user is subscribed or not
    """
    uid = int(uid)
    pid = int(pid)

    # Check that the uid to the pid
    return r.zrank(K.POST_SUBSCRIBERS % pid, uid) is not None


def subscription_reason(uid, pid):
    """
    Returns the reason a user is subscribed to a post. Very simple function
    which will return the score in the zset or None if the user is not
    subscribed.
    """
    uid = int(uid)
    pid = int(pid)

    # Simply get the score for the uid, Redis will return the None if it isn't
    # there
    return r.zscore(K.POST_SUBSCRIBERS % pid, uid)
