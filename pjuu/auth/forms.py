# -*- coding: utf8 -*-

##############################################################################
# Copyright 2014 Joe Doherty <joe@pjuu.com>
#
# Pjuu is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pjuu is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################

# 3rd party imports
from flask.ext.wtf import Form, RecaptchaField
from wtforms import PasswordField, TextField, ValidationError
from wtforms.validators import Email, EqualTo, Length, Regexp, Required

# Pjuu imports
from . import current_user
from .backend import check_email, check_username, authenticate


class ForgotForm(Form):
    username = TextField('User name or E-Mail')


class SignInForm(Form):
    username = TextField('User name or E-Mail')
    password = PasswordField('Password')


class ResetForm(Form):
    password = PasswordField('Password', [
        EqualTo('password2', message='Passwords must match'),
        Length(min=6,
               message='Password must be at least 6 characters long'),
        Required()])
    password2 = PasswordField('Confirm password')


class PasswordChangeForm(Form):
    password = PasswordField('Current password')
    new_password = PasswordField('New password', [
        EqualTo('new_password2', message='Passwords must match'),
        Length(min=6,
               message='Password must be at least 6 characters long'),
        Required()])
    new_password2 = PasswordField('Confirm new password')

    def validate_password(form, field):
        if not authenticate(current_user['username'], field.data):
            raise ValidationError('Invalid password')


class ChangeEmailForm(Form):
    new_email = TextField('New e-mail address', [Email(),
                                                 Length(max=254), Required()])
    password = PasswordField('Current password')

    def validate_new_email(form, field):
        if not check_email(field.data):
            raise ValidationError('E-mail address already in use')

    def validate_password(form, field):
        if not authenticate(current_user['username'], field.data):
            raise ValidationError('Invalid password')


class SignUpForm(Form):
    username = TextField('User name', [
        Regexp(r'^[a-zA-Z0-9_]{3,16}$',
               message=('Username must be between 3 and 16 characters and can'
                        ' only contain letters, numbers and \'_\' characters.')),
        Required()])
    email = TextField('E-mail address', [Email(), Length(max=254), Required()])
    password = PasswordField('Password', [
        EqualTo('password2', message='Passwords must match'),
        Length(min=6,
               message='Password must be at least 6 characters long'),
        Required()])
    password2 = PasswordField('Confirm password')
    recaptcha = RecaptchaField()

    def validate_username(form, field):
        if not check_username(field.data):
            raise ValidationError('User name already in use')

    def validate_email(form, field):
        if not check_email(field.data):
            raise ValidationError('E-mail address already in use')


class DeleteAccountForm(Form):
    password = PasswordField('Current password')
