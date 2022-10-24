import requests

response = requests.post('http://localhost:8003/visit', json={
    "url": "http://localhost/test",
    "headers": {
        "custom": "test",
        "x-custom": "x-testasdfasdfasdf",
    }
})

response.raise_for_status()
print(response.text)