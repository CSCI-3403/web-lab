from dataclasses import dataclass, field
import logging
import re
from typing import Tuple, Union
from uuid import uuid4

import click
from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response
from flask_sqlalchemy import SQLAlchemy # type: ignore
from sqlalchemy.sql import func

View = Union[Response, str, Tuple[str, int]]

app = Flask(__name__)
db = SQLAlchemy()
app.config["SECRET_KEY"] = "asdfasdfasdfasdfasdf"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data/database.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

@dataclass
class Item(db.Model): # type: ignore
    __tablename__ = "items"

    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    name = db.Column(db.Text)
    description = db.Column(db.Text)
    image = db.Column(db.Text)
    price = db.Column(db.Integer)

@dataclass
class Review(db.Model): # type: ignore
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    student = db.Column(db.Text)
    item = db.Column(db.Text, db.ForeignKey('items.id'))
    review = db.Column(db.Text)

@dataclass
class Purchase(db.Model): # type: ignore
    __tablename__ = "purchases"

    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    item = db.Column(db.Text, db.ForeignKey('items.id'))
    quantity = db.Column(db.Integer)
    student = db.Column(db.Text)
    time = db.Column(db.DateTime, server_default=func.now())

with app.app_context():
    db.create_all()

@app.before_request
def set_id():
    if "id" not in session:
        session["id"] = str(uuid4())
    
def xss_escape(query: str, level: int) -> str:
    if level == 0:
        return query
    elif level == 1:
        return query.replace("<script>", "")
    elif level == 2:
        return re.sub(r"<[a-zA-Z]+>", "", query)
    else:
        raise NotImplementedError(f"No XSS escape level #{level}")

@app.route("/")
def index() -> View:
    query = request.args.get("query", "")
    escaped_query = xss_escape(query, session.get("xss-level", 0))

    if not query:
        results = db.session.query(Item).all()
    else:
        results = db.session.query(Item).filter(Item.name.like(f"%{query}%")).all()
    
    purchases = db.session.query(Purchase, Item) \
        .filter(Purchase.student == session["id"]) \
        .outerjoin(Item, Purchase.item == Item.id) \
        .all()


    return render_template(
        "index.html",
        query=escaped_query,
        results=results,
        purchases=purchases,
        top=db.session.query(Item).first())

@app.route("/item/<int:item_id>")
def item(item_id: int) -> View:
    item = db.session.query(Item).filter(Item.id == item_id).first()

    return render_template(
        "item.html",
        item=item,
    )

@app.route("/review", methods=["POST"])
def review() -> View:
    item_id = request.form["item"]
    review = request.form["review"]

    db.session.add(Review(
        student=session["id"],
        item=item_id,
        review=review,
    ))
    db.session.commit()

    return redirect(url_for("item", item_id=item_id))

@app.route("/purchase", methods=["POST"])
def purchase() -> View:
    item_id = request.form["item"]
    quantity = int(request.form["quantity"])

    purchase = Purchase(
        item=item_id,
        quantity=quantity,
        student=session["id"],
    )
    item = db.session.query(Item).filter(Item.id == item_id).first()

    db.session.add(purchase)
    db.session.commit()

    return render_template(
        "purchase.html",
        purchase=purchase,
        item=item,
    )

@click.command()
@click.option("--debug", is_flag=True)
@click.option("--port", default=80)
def main(debug: bool, port: int) -> None:
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    app.run("0.0.0.0", debug=debug, port=port)

if __name__ == "__main__":
    main()