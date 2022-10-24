from contextlib import contextmanager
import logging
import sys
from threading import Lock
from time import sleep
from typing import Any, Dict, Iterator, Optional, Tuple, Union

import click
from flask import Flask, jsonify, request
from seleniumwire import webdriver # type: ignore
from selenium.common.exceptions import TimeoutException, InvalidArgumentException
from selenium.webdriver.firefox.options import Options
from werkzeug.wrappers import Response

View = Union[Response, str, Tuple[str, int]]

log = logging.getLogger(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(message)s')
logging.getLogger("werkzeug").disabled = True
logging.getLogger("seleniumwire.storage").disabled = True
logging.getLogger("seleniumwire.backend").disabled = True
logging.getLogger("seleniumwire.handler").disabled = True
logging.getLogger("seleniumwire.server").disabled = True

# Set up app
app = Flask(__name__)

class DriverPool:
    lock = Lock()
    retries = 4
    retry_wait = .5

    def __init__(self, n_drivers: int, headless: bool = True) -> None:
        options = Options()
        options.headless = headless
        options.set_preference("dom.webnotifications.enabled", False)
        self.drivers = [webdriver.Firefox(options=options) for _ in range(n_drivers)]

    @contextmanager
    def _get_free_driver(self) -> Iterator[Optional[webdriver.Firefox]]:
        for _ in range(self.retries):
            try:
                driver = self.drivers.pop()
                break
            except IndexError:
                sleep(self.retry_wait)
        else:
            driver = None

        try:
            yield driver
        finally:
            if driver is not None:
                self.drivers.append(driver)

    def get(self, url: str, headers: Dict[str, str]) -> str:
        with self._get_free_driver() as driver:
            if driver is None:
                raise RuntimeError("No driver available")

            log.info("Got free driver")
            driver.set_page_load_timeout(10)
            try:
                def interceptor(request: Any) -> None:
                    log.info(f"Requesting {request}")
                    for k, v in headers.items():
                        request.headers[k] = str(v)

                driver.request_interceptor = interceptor
                log.info("Sending URL to driver")
                driver.get(url)
                return driver.page_source
            except InvalidArgumentException:
                raise ValueError("URL was invalid")
            except TimeoutException as e:
                raise e

drivers: DriverPool = None # type: ignore

@app.route("/")
def index() -> View:
    return "ok"

@app.route("/visit", methods=["POST"])
def visit() -> View:
    url = request.json.get("url") # type: ignore
    headers = request.json.get("headers", {}) # type: ignore
    if not url:
        log.error("Did not get URL")
        return (jsonify({ "error": "No URL" }), 400)

    log.info("Requesting URL: {} with headers: {}".format(url, headers))

    try:
        source = drivers.get(url, headers)
        return (jsonify({ "source": source }), 200)
    except Exception as e:
        log.exception(f"Error on URL: {url}")
        return (jsonify({ "error": str(e) }), 500)

@click.command()
@click.option("--debug", is_flag=True)
@click.option("--port", type=int, default=8080)
def main(debug: bool, port: int) -> None:
    global drivers

    log.info("Starting drivers...")
    if debug:
        log.setLevel(logging.DEBUG)
        drivers = DriverPool(1, headless=False)
    else:
        drivers = DriverPool(5)

    log.info("Listening on port {}".format(port))

    app.run("0.0.0.0", threaded=True, port=port)

if __name__ == "__main__":
    main()