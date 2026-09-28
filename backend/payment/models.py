from datetime import datetime

from . import db


# Password columns hold werkzeug hashes, not plaintext. The default scrypt
# format ("scrypt:32768:8:1$salt$hash") is 162 chars, so the original
# String(40) silently rejected every registration once hashing landed.
# 255 leaves room for future algorithm changes.
_PASSWORD_LEN = 255


class User(db.Model):
    __tablename__ = 'user'
    u_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    u_name = db.Column(db.String(20), unique=True, nullable=False)
    u_password = db.Column(db.String(_PASSWORD_LEN), nullable=False)
    # (8,2) not (5,2): a balance has to hold more than 999.99.
    u_money = db.Column(db.DECIMAL(8, 2), default=0)


class Admin(db.Model):
    __tablename__ = 'admin'
    a_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    a_name = db.Column(db.String(20), unique=True, nullable=False)
    a_password = db.Column(db.String(_PASSWORD_LEN), nullable=False)
    a_store_name = db.Column(db.String(40), nullable=False)
    a_address = db.Column(db.String(100))


class Cuisine(db.Model):
    __tablename__ = 'cuisine'
    c_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    c_name = db.Column(db.String(20), unique=True, nullable=False)
    # (6,2) not (2,2): DECIMAL(2,2) only spans 0.00-0.99, which cannot hold
    # any real price.
    c_price = db.Column(db.DECIMAL(6, 2), nullable=False)
    # `datetime.now` — the function, NOT `datetime.now()`. Calling it here
    # would freeze every row's default at the moment the process started.
    c_create_time = db.Column(db.DateTime, default=datetime.now)


class Record(db.Model):
    __tablename__ = 'record'
    r_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    u_id = db.Column(db.Integer, db.ForeignKey('user.u_id'))
    c_id = db.Column(db.Integer, db.ForeignKey('cuisine.c_id'))
    a_id = db.Column(db.Integer, db.ForeignKey('admin.a_id'))
    r_create_time = db.Column(db.DateTime, default=datetime.now)


class Possess(db.Model):
    __tablename__ = 'possess'
    p_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    a_id = db.Column(db.Integer, db.ForeignKey('admin.a_id'))
    c_id = db.Column(db.Integer, db.ForeignKey('cuisine.c_id'))
    p_create_time = db.Column(db.DateTime, default=datetime.now)
