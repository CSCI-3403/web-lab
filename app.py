from dataclasses import dataclass
import logging
import re
import sys
from typing import Optional, Tuple, Union
from uuid import uuid4

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
import requests
from werkzeug.wrappers import Response
from flask_sqlalchemy import SQLAlchemy # type: ignore
from sqlalchemy.sql import func

View = Union[Response, str, Tuple[str, int]]
PURCHASE_SUCCESS_STRING = "Purchase successful!"

log = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(message)s')

app = Flask(__name__)
db = SQLAlchemy()
app.config["SECRET_KEY"] = "asdfasdfasdfasdfasdf"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

@dataclass
class Item(db.Model): # type: ignore
    __tablename__ = "items"

    id: int = db.Column(db.Integer, autoincrement=True, primary_key=True)
    name: str = db.Column(db.Text)
    description: str = db.Column(db.Text)
    image: str = db.Column(db.Text)
    price: int = db.Column(db.Integer)

@dataclass
class Review(db.Model): # type: ignore
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    student = db.Column(db.Text)
    item = db.Column(db.Text, db.ForeignKey('items.id'))
    review = db.Column(db.Text)
    time = db.Column(db.DateTime, server_default=func.now())

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
    db.session.merge(Item(id=1, name='Blue Mitten', description='For the coolest of cats', image='blue_mitten.jpg', price=10))
    db.session.merge(Item(id=2, name='Red Mitten', description='Stylish, and affordable!', image='red_mitten.jpg', price=3))
    db.session.merge(Item(id=3, name='Kitten Blanket', description='Staying warm in style!', image='blanket.jpg', price=4))
    db.session.merge(Item(id=4, name='Tiny Boots', description='Everyone loves small boots', image='boots.jpg', price=15))
    db.session.merge(Item(id=5, name='Warm Scarf', description='For those chilly winter evenings', image='scarf.jpg', price=8))
    db.session.commit()

@app.before_request
def set_id() -> None:
    if "flags" not in session:
        session["flags"] = {}
    if "x-with-id" in request.headers:
        session["id"] = request.headers["x-with-id"]
    if "id" not in session:
        session["id"] = str(uuid4())

def xss_test(url: str) -> None:
    if "x-with-id" in request.headers:
        log.info("Skipping test (originated from xss test bot)")
        return

    level = session.get("xss-level", 0)
    log.info("Starting test")
    response = requests.post("http://localhost:8080/visit", json={
        "url": url,
        "headers": {
            "x-with-id": session["id"],
            "x-with-level": str(level),
        }
    })
    log.info("Got test response")
    if (response.status_code != 200
        and PURCHASE_SUCCESS_STRING in response.json().get("source", "")):
        session["flags"][level] = "You did an XSS!"

def get_xss_status() -> Optional[str]:
    level = session.get("xss-level", 0)
    return session["flags"].get(level)

def xss_escape(query: str) -> str:
    level = session.get("xss-level", 0)
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
    escaped_query = xss_escape(query)

    if not query:
        results = db.session.query(Item).all()
    else:
        xss_test(request.url)
        results = db.session.query(Item).filter(Item.name.like(f"%{query}%")).all()
    
    purchases = db.session.query(Purchase, Item) \
        .filter(Purchase.student == session["id"]) \
        .outerjoin(Item, Purchase.item == Item.id) \
        .limit(5) \
        .all()

    return render_template(
        "index.html",
        query=escaped_query,
        results=results,
        purchases=purchases,
        top=db.session.query(Item).first(),
        success=get_xss_status())

@app.route("/item/<int:item_id>")
def item(item_id: int) -> View:
    item = db.session.query(Item).filter(Item.id == item_id).first()
    reviews = db.session.query(Review) \
        .filter(Review.item == item_id, Review.student == session["id"]) \
        .all()

    return render_template(
        "item.html",
        item=item,
        reviews=reviews,
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

    if "x-with-id" not in request.headers:
        xss_test(url_for("item", item_id=item_id))

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
        success_string=PURCHASE_SUCCESS_STRING,
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