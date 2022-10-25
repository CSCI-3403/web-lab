from dataclasses import dataclass
from hashlib import md5
import logging
import re
import sys
from typing import Any, Dict, Optional, Tuple, Union
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
    db.session.merge(Item(id=4, name='Tiny Hat', description='Everyone loves small hats', image='hat.png', price=6))
    db.session.merge(Item(id=5, name='Little Jacket', description='It even comes with little pockets!', image='jacket.jpg', price=15))
    db.session.merge(Item(id=6, name='Warm Scarf', description='For those chilly winter evenings', image='scarf.jpg', price=8))
    db.session.commit()

TOP_ITEM = Item(id=4, name='Tiny Hat', description='Everyone loves small hats', image='hat.png', price=15)

def set_level(level: int) -> None:
    session["xss-level"] = level

def get_level() -> int:
    if "x-with-level" in request.headers:
        return int(request.headers["x-with-level"])
    return session.get("xss-level", 0)

def set_flag(id: str, level: int) -> None:
    # A simple way to detect cheating- each flag will be mutated slightly.
    flags = {
        0: ["ezpz", "Ezpz", "EZPZ", "EzPz"],
        1: ["looknoscript", "Looknoscript", "LOOKNOSCRIPT", "LookNoScript"],
        2: ["veryclever", "Veryclever", "VERYCLEVER", "VeryClever"],
        3: ["zerosstars", "Zerosstars", "ZEROSSTARS", "ZerosStars"],
        4: ["tootrusting", "Tootrusting", "TOOTRUSTING", "TooTrusting"],
    }
    flag_options = flags.get(level, [])
    uniquish_flag = flag_options[int(md5((id + str(level)).encode()).hexdigest(), 16) % len(flag_options)]

    flag = f"flag-{level}-{uniquish_flag}"
    session[f"flag-{level}"] = flag

def get_flag(level: int) -> Optional[str]:
    return session.get(f"flag-{level}")

@app.before_request
def set_id() -> None:
    if "x-with-id" in request.headers:
        session["xss-tester"] = "true"
        session["id"] = request.headers["x-with-id"]
    if "id" not in session:
        session["id"] = str(uuid4())

@app.context_processor
def ctx() -> Dict[str, Any]:
    level = get_level()
    return {
        "level": level,
        "flag": get_flag(level)
    }

def xss_test(path: str) -> None:
    if "x-with-id" in request.headers:
        log.info("Skipping test (originated from xss test bot)")
        return

    url = "http://app" + path
    level = get_level()
    log.info(f"Testing {session['id']}, level {level}")
    response = requests.post("http://xss-tester:8080/visit", json={
        "url": url,
        "headers": {
            "x-with-id": session["id"],
            "x-with-level": str(level),
        }
    })
    if response.status_code != 200:
        log.error(f"Testing server error: {response.json().get('error')}")
    elif PURCHASE_SUCCESS_STRING not in response.json().get("source", ""):
        log.error(f"Test failed for url: {url}")
    else:
        log.info("Test passed!")
        set_flag(session["id"], get_level())

def xss_escape(query: str) -> str:
    level = get_level()
    if level == 0:
        return query
    elif level == 1:
        return query.replace("<script>", "")
    elif level == 2:
        return re.sub(r"<[a-zA-Z]+>", "", query)
    else:
        return query.replace("<", "&lt;").replace(">", "&gt;")

@app.route("/")
def index() -> View:
    query = request.args.get("query", "")
    escaped_query = xss_escape(query)

    if not query:
        results = db.session.query(Item).all()
    else:
        if get_level() <= 2:
            xss_test("/?" + request.query_string.decode())
        results = db.session.query(Item).filter(Item.name.like(f"%{query}%")).all()
    

    return render_template(
        "index.html",
        query=query,
        escaped_query=escaped_query,
        results=results,
        top=TOP_ITEM)

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

    if get_level() >= 3:
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

@app.route("/clear", methods=["POST"])
def clear() -> View:
    db.session.query(Review).filter(Review.student == session["id"]).delete()
    db.session.commit()

    if request.referrer and request.host in request.referrer:
        return redirect(request.referrer)
    else:
        return redirect(url_for("index"))

@app.route("/level", methods=["POST"])
def level() -> View:
    level = int(request.form.get("xss-level", 0))
    set_level(level)

    # Remove existing reviews 
    if level == 4:
        clear()

    log.info(f"User {session['id']} switched to level {level}")

    if request.referrer and request.host in request.referrer:
        return redirect(request.referrer)
    else:
        return redirect(url_for("index"))

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
