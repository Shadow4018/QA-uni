import requests


def stub_coupon_response(wiremock_url, status=200, body=None):
    mapping = {
        "request": {"method": "POST", "urlPath": "/coupon-validation"},
        "response": {"status": status, "jsonBody": body,
                      "headers": {"Content-Type": "application/json"}},
    }
    requests.post(f"{wiremock_url}/__admin/mappings", json=mapping)


def wiremock_request_count(wiremock_url):
    resp = requests.post(f"{wiremock_url}/__admin/requests/count",
                          json={"urlPath": "/coupon-validation", "method": "POST"})
    return resp.json()["count"]