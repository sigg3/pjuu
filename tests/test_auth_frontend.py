# -*- coding: utf8 -*-

"""Auth frontend tests.

:license: AGPL v3, see LICENSE for more details
:copyright: 2014-2015 Joe Doherty

"""

# Stdlib import
import json
# 3rd party imports
from flask import url_for
from werkzeug.http import parse_cookie
# Pjuu imports
from pjuu import redis_sessions as rs
from pjuu.auth.backend import *
# Test imports
from tests import FrontendTestCase


class AuthFrontendTests(FrontendTestCase):
    """
    This test case will test all the auth subpackages views, decorators
    and forms
    """

    def test_signin_signout(self):
        """
        These functions will test the signin and signout endpoints. We will use
        url_for so that we can change the URIs in the future.
        """
        # Test that we can GET the signin page
        resp = self.client.get(url_for('auth.signin'))
        # We should get a 200 with an error message if we were not successful
        self.assertEqual(resp.status_code, 200)

        # There is no user in the system check that we can't authenticate
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        })
        # We should get a 200 with an error message if we were not successful
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid user name or password', resp.data)

        # Why we are here we will just check that logging in doesn't raise an
        # issue if not logged in
        resp = self.client.get(url_for('auth.signout'))
        # We should be 302 redirected to /signin
        self.assertEqual(resp.status_code, 302)
        # There is nothing we can really check as we do not flash() as message

        # Create a test user and try loggin in, should fail as the user isn't
        # activated
        user1 = create_account('user1', 'user1@pjuu.com', 'Password')
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        })
        # We should get a 200 with an information message
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Please activate your account', resp.data)

        # Activate account
        self.assertTrue(activate(user1))

        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password',
            'keep_signed_in': True
        })
        # Check we are redirected
        self.assertEqual(resp.status_code, 302)

        # Log back out
        self.client.get(url_for('auth.signout'))

        # Test that the correct warning is shown if the user is banned
        self.assertTrue(ban(user1))
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        })
        # We should get a 200 with an information message
        self.assertEqual(resp.status_code, 200)
        self.assertIn('You\'re a very naughty boy!', resp.data)
        # Lets unban the user now so we can carry on
        self.assertTrue(ban(user1, False))

        # Now the user is active and not banned actualy log in
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<h1>Feed</h1>', resp.data)

        # Attempt to try and get back to login when we are already logged in
        resp = self.client.get(url_for('auth.signin'))
        self.assertEqual(resp.status_code, 302)

        # Now we are logged in lets just ensure logout doesn't do anything daft
        # We should be redirected back to /
        resp = self.client.get(url_for('auth.signout'), follow_redirects=True)
        # We should have been 302 redirected to /signin
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Successfully signed out', resp.data)

        # Lets try and cheat the system
        # Attempt invalid Password
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password1'
        }, follow_redirects=True)
        # We should get a 200 with an error message if we were not successful
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid user name or password', resp.data)

        # Attempt user does not exist
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'bob',
            'password': 'Password'
        })
        # We should get a 200 with an error message if we were not successful
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid user name or password', resp.data)

        # Log the user in and ensure they are logged out if there account
        # is banned during using the site and not just at login
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<h1>Feed</h1>', resp.data)
        # Lets go to another view, we will check out profile and look for our
        # username
        resp = self.client.get(url_for('users.settings_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('user1@pjuu.com', resp.data)
        # Let's ban the user now
        self.assertTrue(ban(user1))
        # Attempt to get to the feed
        resp = self.client.get(url_for('users.feed'), follow_redirects=True)
        # We should be redirected to signin with the standard message
        self.assertEqual(resp.status_code, 200)
        self.assertIn('You\'re a very naughty boy!', resp.data)

        # Adding test from form.validate() == False in signup
        # Coverage
        resp = self.client.post(url_for('auth.signin'), data={
            'username': '',
            'password': ''
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid user name or password', resp.data)

        # Log in with user1 and remove the session part way through
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Find the Set-Cookie header so we can parse then delete it
        session_id = None
        for header in resp.headers:
            if header[0] == 'Set-Cookie':
                session_id = parse_cookie(header[1])['session']
                rs.delete(session_id)

        resp = self.client.get(url_for('users.profile', username='user3'),
                               follow_redirects=True)
        self.assertIn('You need to be logged in to view that', resp.data)

        # Find the Set-Cookie header so we can parse it and check the session
        # identifier has been updated
        for header in resp.headers:
            if header[0] == 'Set-Cookie':
                self.assertNotEqual(session_id,
                                    parse_cookie(header[1])['session'])

    def test_signup_activate(self):
        """
        Tests the signup and activate endpoint inside Pjuu.

        There are some limitations to this! We can not test e-mail sending as
        this will not be available on Travis.
        """
        # Test that we can GET the signup page
        resp = self.client.get(url_for('auth.signup'))
        # We should get a 200 with an error message if we were not successful
        self.assertEqual(resp.status_code, 200)

        # Lets attempt to create a new account. This should return a 302 to
        # /signin with a little message displayed to activate your account
        resp = self.client.post(url_for('auth.signup'), data={
            'username': 'user1',
            'email': 'user1@pjuu.com',
            'password': 'Password',
            'password2': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Yay! You\'ve signed up', resp.data)

        # We are in testing mode so we can get the auth token from the response
        # this is in the headers as X-Pjuu-Token
        token = resp.headers.get('X-Pjuu-Token')
        self.assertIsNotNone(token)
        # Try and actiavte our account
        resp = self.client.get(url_for('auth.activate', token=token),
                               follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Your account has now been activated', resp.data)

        # Try and activate the account again. We should get a 302 to /signin
        # and a flash message informing up that the account is already active
        resp = self.client.get(url_for('auth.activate', token=token),
                               follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid token', resp.data)

        # Try and signup with the same user and ensure we get the correct resp
        # and error codes. We will also put mismatch passwords in just to test
        # that all forms throw the correct error
        resp = self.client.post(url_for('auth.signup'), data={
            'username': 'user1',
            'email': 'user1@pjuu.com',
            'password': 'Password',
            'password2': 'PasswordPassword'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # Ensure there is an overall form error
        self.assertIn('Oh no! There are errors in your form', resp.data)
        # Ensure the form elements actually throw there own errors
        self.assertIn('User name already in use', resp.data)
        self.assertIn('E-mail address already in use', resp.data)
        self.assertIn('Passwords must match', resp.data)

        # Try a few scenarios with email addresses we are not happy about.
        resp = self.client.post(url_for('auth.signup'), data={
            'username': 'user1',
            'email': 'user1#user1@pjuu.com',
            'password': 'Password',
            'password2': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # Ensure there is an overall form error
        self.assertIn('Oh no! There are errors in your form', resp.data)
        self.assertIn('Invalid email address', resp.data)

        # Ensure that we CAN signup with a + in the name. This is a hate of
        # mine. Not being able to namespace my e-mail addresses
        resp = self.client.post(url_for('auth.signup'), data={
            'username': 'user2',
            'email': 'user2+user2@pjuu.com',
            'password': 'Password',
            'password2': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Yay! You\'ve signed up', resp.data)

        # Log in to Pjuu so that we can make sure we can not get back to signup
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # We are now logged in lets try and go to signup and ensure we get
        # redirected back to feed
        resp = self.client.get(url_for('auth.signup'))
        self.assertEqual(resp.status_code, 302)
        # Why we are logged in lets ensure we can't get to activate
        resp = self.client.get(url_for('auth.activate', token=token))
        self.assertEqual(resp.status_code, 302)

        # Lets delete the account and then try and reactivate
        delete_account(get_uid_username('user1'))
        resp = self.client.get(url_for('auth.activate', token=token),
                               follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid token', resp.data)

    def test_forgot_reset(self):
        """
        Test forgotten password and the password reset form.
        """
        # Test that we can GET the forgot page
        resp = self.client.get(url_for('auth.forgot'))
        self.assertEqual(resp.status_code, 200)

        # Try and post data to the form even though we don't have a user.
        # This will work as the form will always return the same response
        # this is to stop users trying to recover random details
        resp = self.client.post(url_for('auth.forgot'), data={
            'username': 'user1'
        }, follow_redirects=True)
        # We should be redirect to login and a message flashed
        self.assertEqual(resp.status_code, 200)
        self.assertIn('If we\'ve found your account we\'ve', resp.data)
        # Let's make sure there is no X-Pjuu-Token header added as one should
        # not be generated for a non existant user
        self.assertIsNone(resp.headers.get('X-Pjuu-Token'))

        # Lets do this again but with a user (this is the only way to test
        # password resetting)
        create_account('user1', 'user1@pjuu.com', 'Password')
        # Lets do the above test again but with this new user
        resp = self.client.post(url_for('auth.forgot'), data={
            'username': 'user1'
        }, follow_redirects=True)
        # We should be redirect to login and a message flashed
        self.assertEqual(resp.status_code, 200)
        self.assertIn('If we\'ve found your account we\'ve', resp.data)
        # This time we should have a token
        token = resp.headers.get('X-Pjuu-Token')
        self.assertIsNotNone(token)

        # Now we will try and change the password on our account
        # Lets just make sure we can get to the reset view with our token
        resp = self.client.get(url_for('auth.reset', token=token))
        self.assertEqual(resp.status_code, 200)

        # Lets make sure the form tells us when we have filled it in wrong
        # Attempt to set a mis matching password
        resp = self.client.post(url_for('auth.reset', token=token), data={
            'password': 'PasswordOne',
            'password2': 'PasswordTwo'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Oh no! There are errors in your form', resp.data)
        # Attempt to not even fill the form in
        resp = self.client.post(url_for('auth.reset', token=token), data={},
                                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Oh no! There are errors in your form', resp.data)

        # Test reset with an invalid token
        resp = self.client.post(url_for('auth.reset', token='token'), data={},
                                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid token', resp.data)

        # Lets post to the view and change the password.
        # This also confirms the preservation of the auth tokens
        resp = self.client.post(url_for('auth.reset', token=token), data={
            'password': 'NewPassword',
            'password2': 'NewPassword'
        }, follow_redirects=True)
        # This should redirect us back to the signin view as well as have
        # changed out password
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Your password has now been reset', resp.data)
        # We will just check we can log in with the new Password not password
        self.assertTrue(authenticate('user1', 'NewPassword'))
        # I know, I know this is tested in the backend buts let's make sure
        # we can't auth with the old password
        self.assertFalse(authenticate('test', 'Password'))

    def test_change_confirm_email(self):
        """
        Test changing your e-mail address from the frontend. This is the last
        function which uses Tokens.

        Note: We need to be logged in for this view to work.
        """
        # Try going to the view without being logged in
        resp = self.client.get(url_for('auth.change_email'), follow_redirects=True)
        # We will just ensure we have been redirected to /signin
        self.assertEqual(resp.status_code, 200)
        # We should see a message saying we need to signin
        self.assertIn('You need to be logged in to view that', resp.data)

        # Let's create a user an login
        user1 = create_account('user1', 'user1@pjuu.com', 'Password')
        # Activate the account
        self.assertTrue(activate(user1))

        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # Lets check to see that our current email is listed on the inital
        # settings page
        resp = self.client.get(url_for('users.settings_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('user1@pjuu.com', resp.data)

        # Lets double check we can get the change_email page and attempt to
        # change our password.
        resp = self.client.get(url_for('auth.change_email'))
        self.assertEqual(resp.status_code, 200)

        # Try and change the e-mail address with an invalid password
        resp = self.client.post(url_for('auth.change_email'), data={
            'password': '',
            'new_email': 'user1_new@pjuu.com'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Oh no! There are errors in your form', resp.data)

        # Attempt to change our e-mail
        resp = self.client.post(url_for('auth.change_email'), data={
            'password': 'Password',
            'new_email': 'user1_new@pjuu.com'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('We\'ve sent you an email, please confirm', resp.data)
        # Get the auth token
        token = resp.headers.get('X-Pjuu-Token')
        self.assertIsNotNone(token)

        # Confirm the email change
        resp = self.client.get(url_for('auth.confirm_email', token=token),
                               follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('We\'ve updated your e-mail address', resp.data)

        # Let's ensure that our new e-mail appears on our profile page
        resp = self.client.get(url_for('users.settings_profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('user1_new@pjuu.com', resp.data)
        # Yey our email was updated

        # Lets just make sure we can't change our e-mail without a password
        resp = self.client.post(url_for('auth.change_email'), data={
            'password': '',
            'new_email': 'user1_newer@pjuu.com'
        }, follow_redirects=True)
        self.assertIn('Oh no! There are errors in your form', resp.data)

        # Lets make sure the email doesn't change until the confirmation is
        # checked
        resp = self.client.post(url_for('auth.change_email'), data={
            'password': 'Password',
            'new_email': 'user1_newer@pjuu.com'
        }, follow_redirects=True)
        self.assertIn('We\'ve sent you an email, please confirm', resp.data)
        resp = self.client.get(url_for('users.settings_profile'))
        self.assertNotIn('user1_newer@pjuu.com', resp.data)

        # Try and change the e-mail address to one which is already in use
        resp = self.client.post(url_for('auth.change_email'), data={
            'password': 'Password',
            'new_email': 'user1_new@pjuu.com'
        }, follow_redirects=True)
        self.assertIn('E-mail address already in use', resp.data)

        # Check invalid token for confirm_email
        # Coverage
        resp = self.client.get(url_for('auth.confirm_email', token='token'),
                               follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid token', resp.data)

    def test_change_password(self):
        """
        Test that users can change their own passwords when they are logged in
        """
        # Try going to the view without being logged in
        resp = self.client.get(url_for('auth.change_password'),
                               follow_redirects=True)
        # We will just ensure we have been redirected to /signin
        self.assertEqual(resp.status_code, 200)
        # We should see a message saying we need to signin
        self.assertIn('You need to be logged in to view that', resp.data)

        # Let's create a user an login
        user1 = create_account('user1', 'user1@pjuu.com', 'Password')
        # Activate the account
        self.assertTrue(activate(user1))
        # Log the user in
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Go to the change password page
        resp = self.client.get(url_for('auth.change_password'))
        self.assertEqual(resp.status_code, 200)

        # Attempt to change our password
        resp = self.client.post(url_for('auth.change_password'), data={
            'password': 'Password',
            'new_password': 'NewPassword',
            'new_password2': 'NewPassword'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('We\'ve updated your password', resp.data)
        # Password was successfully changed

        # Lets try an change our password to one which is not a valid password
        resp = self.client.post(url_for('auth.change_password'), data={
            'password': 'NewPassword',
            'new_password': 'Pass',
            'new_password2': 'Pass'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Password must be at least 6 characters long', resp.data)

        # Lets try an change our password but make them not match
        resp = self.client.post(url_for('auth.change_password'), data={
            'password': 'NewPassword',
            'new_password': 'Password',
            'new_password2': 'OddPassword'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Passwords must match', resp.data)

        # Lets try and change our pasword but provide a wrong current password
        resp = self.client.post(url_for('auth.change_password'), data={
            'password': 'WrongPassword',
            'new_password': 'Password',
            'new_password2': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid password', resp.data)

    def test_delete_account(self):
        """
        Test deleting an account from the frontend
        """
        # Attempt to get to the delete_account view when not logged in
        resp = self.client.get(url_for('auth.delete_account'),
                               follow_redirects=True)
        # We will just ensure we have been redirected to /signin
        self.assertEqual(resp.status_code, 200)
        # We should see a message saying we need to signin
        self.assertIn('You need to be logged in to view that', resp.data)

        # Let's create a user an login
        user1 = create_account('user1', 'user1@pjuu.com', 'Password')
        # Activate the account
        self.assertTrue(activate(user1))
        # Log the user in
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Check that we can get to the delete_account page
        resp = self.client.get(url_for('auth.delete_account'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('This action is irreversible', resp.data)

        # Attempy to delete account. We are going to do this the other way
        # round. We will try and do it with an invalid password etc first.
        resp = self.client.post(url_for('auth.delete_account'), data={
            'password': 'WrongPassword'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Oops! wrong password', resp.data)

        # That's all we can do to try and brake this. Let's delete our account
        resp = self.client.post(url_for('auth.delete_account'), data={
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Your account is being deleted', resp.data)

        # We are now back at signin. Let's check we can't login
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Invalid user name or password', resp.data)
        # Done

    def test_dump_account(self):
        """
        Simple check to make sure dump_account works in the views.

        Will simply check that a JSON response comes back. Don't worry this
        is pretty much a direct interface to the backend function of the same
        name. See BackendTestCase for more details.
        """
        # Let's create a user an login
        user1 = create_account('user1', 'user1@pjuu.com', 'Password')
        # Activate the account
        self.assertTrue(activate(user1))

        # Attempt to acess the URL without being logged in
        resp = self.client.get(url_for('auth.dump_account'))
        self.assertEqual(resp.status_code, 302)

        # Log the user in
        resp = self.client.post(url_for('auth.signin'), data={
            'username': 'user1',
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Check that a password confirmation is now required
        resp = self.client.get(url_for('auth.dump_account'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('This action will dump all of your data', resp.data)

        # Send password to the view
        resp = self.client.post(url_for('auth.dump_account'), data={
            'password': 'Password'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        json_resp = json.loads(resp.data)
        self.assertEqual(json_resp['user']['username'], 'user1')

        # Test inputting the wrong password
        # Send password to the view
        resp = self.client.post(url_for('auth.dump_account'), data={
            'password': 'WrongPassword'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Oops! wrong password', resp.data)
