from dataclasses import dataclass, field
import logging
import re
from typing import List, Tuple, Union
from uuid import uuid4

import click
from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response
from flask_sqlalchemy import SQLAlchemy

View = Union[Response, str, Tuple[str, int]]

app = Flask(__name__)
db = SQLAlchemy()

@dataclass
class Item(db.Model):
    id: str = db.Column(db.Integer, autoincrement=True, primary_key=True)
    student: str = db.Column(db.Text)
    name: str = db.Column(db.Text)
    description: str = db.Column(db.Text)
    image: str = db.Column(db.Text)
    price: int = db.Column(db.Integer)

class Review(db.Model):
    id: str = db.Column(db.Integer, autoincrement=True, primary_key=True)
    student: str = db.Column(db.Text)

items = [
    Item("bluemitten", "Blue Mitten", "For the coolest of cats", "blue_mitten.jpg", 10),
    Item("redmitten", "Red Mitten", "Stylish, and affordable!", "red_mitten.jpg", 3),
    Item("blanket", "Kitten Blanket", "Staying warm in style!", "blanket.jpg", 4),
    Item("boots", "Tiny Lil' Boots", "Everyone loves boots", "boots.jpg", 15),
    Item("scarf", "Warm Scarf", "For those chilly winter evenings", "scarf.jpg", 8),
]

@app.before_request
def set_id():
    if "id" not in session:
        session["id"] = uuid4()

def get_item(id: str) -> Item:
    return [i for i in items if i.id == id][0]

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
        results = items
    else:
        results = [
            item for item in items
            if query.lower() in item.name.lower()
            or query.lower() in item.description.lower()]

    return render_template(
        "index.html",
        query=escaped_query,
        results=results,
        top=items[0])

@app.route("/item/<id>")
def item(id: str) -> View:
    item = get_item(id)

    return render_template(
        "item.html",
        item=item,
    )

@app.route("/review", methods=["POST"])
def review() -> View:
    id = request.form["item"]
    review = request.form["review"]

    get_item(id).reviews.append(review)

    return redirect(url_for("item", id=id))

@app.route("/purchase", methods=["POST"])
def purchase() -> View:
    item = get_item(request.form["item"])
    quantity = int(request.form["quantity"])

    return render_template(
        "purchase.html",
        item=item,
        quantity=quantity,
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