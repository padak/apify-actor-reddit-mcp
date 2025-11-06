"""
Unit tests for Reddit response normalizer.

Tests the ResponseNormalizer class and normalization functions.
"""

import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime

from src.reddit.normalizer import (
    ResponseNormalizer,
    normalizer,
    normalize_post,
    normalize_comment,
    normalize_user,
    normalize_subreddit,
)


class TestResponseNormalizer:
    """Test ResponseNormalizer class."""

    def test_singleton_instance(self):
        """Test that normalizer singleton exists."""
        assert normalizer is not None
        assert isinstance(normalizer, ResponseNormalizer)


class TestNormalizePost:
    """Test post normalization."""

    def create_mock_submission(self, **kwargs):
        """Create a mock PRAW submission."""
        defaults = {
            'id': 'test123',
            'title': 'Test Post',
            'author': MagicMock(name='testuser'),
            'subreddit': MagicMock(display_name='python'),
            'created_utc': 1699200000.0,
            'score': 100,
            'upvote_ratio': 0.95,
            'num_comments': 50,
            'url': 'https://reddit.com/r/python/test',
            'permalink': '/r/python/comments/test123/test_post/',
            'selftext': 'This is a test post',
            'link_flair_text': 'Discussion',
            'is_self': True,
            'is_video': False,
            'over_18': False,
            'spoiler': False,
            'stickied': False,
            'locked': False,
            'archived': False,
        }
        defaults.update(kwargs)

        mock_submission = MagicMock()
        for key, value in defaults.items():
            setattr(mock_submission, key, value)

        return mock_submission

    def test_normalize_basic_post(self):
        """Test normalizing a basic post."""
        submission = self.create_mock_submission()
        result = normalize_post(submission)

        assert result['id'] == 'test123'
        assert result['type'] == 'post'
        assert result['title'] == 'Test Post'
        assert result['author'] == 'testuser'
        assert result['subreddit'] == 'python'
        assert result['score'] == 100
        assert result['upvote_ratio'] == 0.95
        assert result['num_comments'] == 50

    def test_normalize_post_with_deleted_author(self):
        """Test normalizing post with deleted author."""
        submission = self.create_mock_submission(author=None)
        result = normalize_post(submission)

        assert result['author'] == '[deleted]'

    def test_normalize_post_with_long_selftext(self):
        """Test that long selftext is truncated."""
        long_text = 'a' * 2000
        submission = self.create_mock_submission(selftext=long_text)
        result = normalize_post(submission)

        assert len(result['selftext']) == 1000
        assert result['selftext'] == 'a' * 1000

    def test_normalize_post_with_empty_selftext(self):
        """Test normalizing post with no selftext."""
        submission = self.create_mock_submission(selftext='')
        result = normalize_post(submission)

        assert result['selftext'] == ''

    def test_normalize_post_permalink_format(self):
        """Test that permalink is properly formatted."""
        submission = self.create_mock_submission(
            permalink='/r/test/comments/123/title/'
        )
        result = normalize_post(submission)

        assert result['permalink'].startswith('https://reddit.com')
        assert '/r/test/comments/123/' in result['permalink']

    def test_normalize_video_post(self):
        """Test normalizing video post."""
        submission = self.create_mock_submission(
            is_video=True,
            is_self=False
        )
        result = normalize_post(submission)

        assert result['is_video'] is True
        assert result['is_self'] is False

    def test_normalize_nsfw_post(self):
        """Test normalizing NSFW post."""
        submission = self.create_mock_submission(over_18=True)
        result = normalize_post(submission)

        assert result['over_18'] is True

    def test_normalize_stickied_post(self):
        """Test normalizing stickied post."""
        submission = self.create_mock_submission(stickied=True)
        result = normalize_post(submission)

        assert result['stickied'] is True

    def test_normalize_post_batch(self):
        """Test normalizing multiple posts."""
        submissions = [
            self.create_mock_submission(id='post1', title='Post 1'),
            self.create_mock_submission(id='post2', title='Post 2'),
            self.create_mock_submission(id='post3', title='Post 3'),
        ]

        results = ResponseNormalizer.normalize_post_batch(submissions)

        assert len(results) == 3
        assert results[0]['id'] == 'post1'
        assert results[1]['id'] == 'post2'
        assert results[2]['id'] == 'post3'


class TestNormalizeComment:
    """Test comment normalization."""

    def create_mock_comment(self, **kwargs):
        """Create a mock PRAW comment."""
        defaults = {
            'id': 'comment123',
            'author': MagicMock(name='commenter'),
            'body': 'This is a comment',
            'score': 10,
            'created_utc': 1699200000.0,
            'depth': 0,
            'parent_id': 't3_post123',
            'is_submitter': False,
            'stickied': False,
            'distinguished': None,
            'edited': False,
            'controversiality': 0,
        }
        defaults.update(kwargs)

        mock_comment = MagicMock()
        for key, value in defaults.items():
            setattr(mock_comment, key, value)

        return mock_comment

    def test_normalize_basic_comment(self):
        """Test normalizing a basic comment."""
        comment = self.create_mock_comment()
        result = normalize_comment(comment)

        assert result['id'] == 'comment123'
        assert result['type'] == 'comment'
        assert result['author'] == 'commenter'
        assert result['body'] == 'This is a comment'
        assert result['score'] == 10
        assert result['depth'] == 0
        assert result['parent_id'] == 't3_post123'

    def test_normalize_deleted_comment(self):
        """Test normalizing deleted comment."""
        comment = self.create_mock_comment(author=None)
        result = normalize_comment(comment)

        assert result['author'] == '[deleted]'

    def test_normalize_removed_comment(self):
        """Test normalizing removed comment."""
        comment = self.create_mock_comment(body='')
        result = normalize_comment(comment)

        assert result['body'] == '[removed]'

    def test_normalize_edited_comment(self):
        """Test normalizing edited comment."""
        edit_timestamp = 1699210000.0
        comment = self.create_mock_comment(edited=edit_timestamp)
        result = normalize_comment(comment)

        assert result['edited'] == int(edit_timestamp)

    def test_normalize_unedited_comment(self):
        """Test normalizing unedited comment."""
        comment = self.create_mock_comment(edited=False)
        result = normalize_comment(comment)

        assert result['edited'] is False

    def test_normalize_submitter_comment(self):
        """Test normalizing comment by post author."""
        comment = self.create_mock_comment(is_submitter=True)
        result = normalize_comment(comment)

        assert result['is_submitter'] is True

    def test_normalize_distinguished_comment(self):
        """Test normalizing distinguished comment."""
        comment = self.create_mock_comment(distinguished='moderator')
        result = normalize_comment(comment)

        assert result['distinguished'] == 'moderator'

    def test_normalize_nested_comment(self):
        """Test normalizing nested comment."""
        comment = self.create_mock_comment(
            depth=2,
            parent_id='t1_parent_comment'
        )
        result = normalize_comment(comment)

        assert result['depth'] == 2
        assert result['parent_id'] == 't1_parent_comment'

    def test_normalize_comment_without_depth(self):
        """Test normalizing comment without depth attribute."""
        comment = MagicMock()
        comment.id = 'test'
        comment.author = MagicMock(name='user')
        comment.body = 'test'
        comment.score = 1
        comment.created_utc = 1699200000.0
        comment.parent_id = 't3_post'
        comment.is_submitter = False
        comment.stickied = False
        comment.distinguished = None
        comment.edited = False
        # No depth attribute
        delattr(comment, 'depth')

        result = normalize_comment(comment)

        assert result['depth'] == 0  # Default value

    def test_normalize_comment_batch(self):
        """Test normalizing multiple comments."""
        comments = [
            self.create_mock_comment(id='c1', body='Comment 1'),
            self.create_mock_comment(id='c2', body='Comment 2'),
        ]

        results = ResponseNormalizer.normalize_comment_batch(comments)

        assert len(results) == 2
        assert results[0]['id'] == 'c1'
        assert results[1]['id'] == 'c2'


class TestNormalizeUser:
    """Test user normalization."""

    def create_mock_redditor(self, **kwargs):
        """Create a mock PRAW redditor."""
        defaults = {
            'name': 'testuser',
            'id': 'user123',
            'created_utc': 1699200000.0,
            'link_karma': 1000,
            'comment_karma': 5000,
            'is_gold': False,
            'is_mod': False,
            'has_verified_email': True,
            'icon_img': 'https://reddit.com/icon.png',
        }
        defaults.update(kwargs)

        mock_redditor = MagicMock()
        for key, value in defaults.items():
            setattr(mock_redditor, key, value)

        return mock_redditor

    def test_normalize_basic_user(self):
        """Test normalizing a basic user."""
        redditor = self.create_mock_redditor()
        result = normalize_user(redditor)

        assert result['username'] == 'testuser'
        assert result['id'] == 'user123'
        assert result['link_karma'] == 1000
        assert result['comment_karma'] == 5000
        assert result['is_gold'] is False
        assert result['is_mod'] is False

    def test_normalize_gold_user(self):
        """Test normalizing Reddit Gold user."""
        redditor = self.create_mock_redditor(is_gold=True)
        result = normalize_user(redditor)

        assert result['is_gold'] is True

    def test_normalize_moderator_user(self):
        """Test normalizing moderator user."""
        redditor = self.create_mock_redditor(is_mod=True)
        result = normalize_user(redditor)

        assert result['is_mod'] is True

    def test_normalize_user_without_optional_fields(self):
        """Test normalizing user without optional fields."""
        redditor = MagicMock()
        redditor.name = 'user'
        redditor.created_utc = 1699200000.0
        redditor.link_karma = 100
        redditor.comment_karma = 200
        # Remove optional attributes
        for attr in ['id', 'is_gold', 'is_mod', 'has_verified_email', 'icon_img']:
            if hasattr(redditor, attr):
                delattr(redditor, attr)

        result = normalize_user(redditor)

        assert result['username'] == 'user'
        assert result['id'] is None
        assert result['is_gold'] is False
        assert result['is_mod'] is False


class TestNormalizeSubreddit:
    """Test subreddit normalization."""

    def create_mock_subreddit(self, **kwargs):
        """Create a mock PRAW subreddit."""
        defaults = {
            'display_name': 'python',
            'id': 'sub123',
            'title': 'Python Programming',
            'public_description': 'Learn Python',
            'subscribers': 1000000,
            'active_user_count': 5000,
            'created_utc': 1699200000.0,
            'over18': False,
            'url': '/r/python/',
            'icon_img': 'https://reddit.com/icon.png',
            'community_icon': 'https://reddit.com/community.png',
            'submission_type': 'any',
        }
        defaults.update(kwargs)

        mock_subreddit = MagicMock()
        for key, value in defaults.items():
            setattr(mock_subreddit, key, value)

        return mock_subreddit

    def test_normalize_basic_subreddit(self):
        """Test normalizing a basic subreddit."""
        subreddit = self.create_mock_subreddit()
        result = normalize_subreddit(subreddit)

        assert result['name'] == 'python'
        assert result['id'] == 'sub123'
        assert result['title'] == 'Python Programming'
        assert result['description'] == 'Learn Python'
        assert result['subscribers'] == 1000000
        assert result['active_users'] == 5000
        assert result['over18'] is False

    def test_normalize_nsfw_subreddit(self):
        """Test normalizing NSFW subreddit."""
        subreddit = self.create_mock_subreddit(over18=True)
        result = normalize_subreddit(subreddit)

        assert result['over18'] is True

    def test_normalize_subreddit_url_format(self):
        """Test that subreddit URL is properly formatted."""
        subreddit = self.create_mock_subreddit(url='/r/python/')
        result = normalize_subreddit(subreddit)

        assert result['url'].startswith('https://reddit.com')
        assert '/r/python/' in result['url']


class TestAddMetadata:
    """Test metadata addition to responses."""

    def test_add_basic_metadata(self):
        """Test adding basic metadata."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(data)

        assert 'data' in result
        assert 'metadata' in result
        assert result['data'] == data
        assert 'timestamp' in result['metadata']

    def test_add_cache_metadata(self):
        """Test adding cache-related metadata."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(
            data,
            cached=True,
            cache_age_seconds=120
        )

        assert result['metadata']['cached'] is True
        assert result['metadata']['cache_age_seconds'] == 120

    def test_add_rate_limit_metadata(self):
        """Test adding rate limit metadata."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(
            data,
            rate_limit_remaining=85
        )

        assert result['metadata']['rate_limit_remaining'] == 85

    def test_add_performance_metadata(self):
        """Test adding performance metadata."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(
            data,
            execution_time_ms=123.45,
            reddit_api_calls=2
        )

        assert result['metadata']['execution_time_ms'] == 123.45
        assert result['metadata']['reddit_api_calls'] == 2

    def test_add_all_metadata(self):
        """Test adding all metadata fields."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(
            data,
            cached=True,
            cache_age_seconds=300,
            rate_limit_remaining=95,
            execution_time_ms=50.0,
            reddit_api_calls=1
        )

        metadata = result['metadata']
        assert metadata['cached'] is True
        assert metadata['cache_age_seconds'] == 300
        assert metadata['rate_limit_remaining'] == 95
        assert metadata['execution_time_ms'] == 50.0
        assert metadata['reddit_api_calls'] == 1
        assert 'timestamp' in metadata

    def test_metadata_timestamp_format(self):
        """Test that timestamp is in ISO format."""
        data = {"test": "data"}
        result = ResponseNormalizer.add_metadata(data)

        timestamp = result['metadata']['timestamp']
        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(timestamp)
        assert isinstance(parsed, datetime)


class TestConvenienceFunctions:
    """Test convenience normalization functions."""

    def test_normalize_post_function(self):
        """Test normalize_post convenience function."""
        mock_submission = MagicMock()
        mock_submission.id = 'test'
        mock_submission.title = 'Test'
        mock_submission.author = MagicMock(name='user')
        mock_submission.subreddit = MagicMock(display_name='test')
        mock_submission.created_utc = 1699200000.0
        mock_submission.score = 10
        mock_submission.upvote_ratio = 0.9
        mock_submission.num_comments = 5
        mock_submission.url = 'https://reddit.com'
        mock_submission.permalink = '/r/test/test'
        mock_submission.selftext = 'text'
        mock_submission.link_flair_text = None
        mock_submission.is_self = True
        mock_submission.is_video = False
        mock_submission.over_18 = False
        mock_submission.spoiler = False
        mock_submission.stickied = False
        mock_submission.locked = False
        mock_submission.archived = False

        result = normalize_post(mock_submission)

        assert result['id'] == 'test'
        assert result['type'] == 'post'

    def test_normalize_comment_function(self):
        """Test normalize_comment convenience function."""
        mock_comment = MagicMock()
        mock_comment.id = 'test'
        mock_comment.author = MagicMock(name='user')
        mock_comment.body = 'comment'
        mock_comment.score = 5
        mock_comment.created_utc = 1699200000.0
        mock_comment.depth = 0
        mock_comment.parent_id = 't3_post'
        mock_comment.is_submitter = False
        mock_comment.stickied = False
        mock_comment.distinguished = None
        mock_comment.edited = False
        mock_comment.controversiality = 0

        result = normalize_comment(mock_comment)

        assert result['id'] == 'test'
        assert result['type'] == 'comment'

    def test_normalize_user_function(self):
        """Test normalize_user convenience function."""
        mock_redditor = MagicMock()
        mock_redditor.name = 'testuser'
        mock_redditor.id = 'user123'
        mock_redditor.created_utc = 1699200000.0
        mock_redditor.link_karma = 100
        mock_redditor.comment_karma = 200
        mock_redditor.is_gold = False
        mock_redditor.is_mod = False
        mock_redditor.has_verified_email = True
        mock_redditor.icon_img = None

        result = normalize_user(mock_redditor)

        assert result['username'] == 'testuser'

    def test_normalize_subreddit_function(self):
        """Test normalize_subreddit convenience function."""
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = 'python'
        mock_subreddit.id = 'sub123'
        mock_subreddit.title = 'Python'
        mock_subreddit.public_description = 'Python programming'
        mock_subreddit.subscribers = 1000
        mock_subreddit.active_user_count = 100
        mock_subreddit.created_utc = 1699200000.0
        mock_subreddit.over18 = False
        mock_subreddit.url = '/r/python/'
        mock_subreddit.icon_img = None
        mock_subreddit.community_icon = None
        mock_subreddit.submission_type = 'any'

        result = normalize_subreddit(mock_subreddit)

        assert result['name'] == 'python'
