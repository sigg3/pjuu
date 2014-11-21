# -*- coding: utf8 -*-

"""
Description:
    Forms used in the posts package

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

# 3rd party imports
from flask import current_app as app
from flask_wtf import Form
from wtforms import TextAreaField
from wtforms.validators import Required, Length


class PostForm(Form):
    """Handle the input from the web for posts and replies.

    """
    body = TextAreaField('Post', [
        Required(),
        Length(max=app.config['MAX_POST_LENGTH'],
               message='Posts can not be larger than '
                       '{} characters'.format(app.config['MAX_POST_LENGTH']))
    ])
