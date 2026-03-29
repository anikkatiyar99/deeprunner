#!/usr/bin/env python3
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def request(method: str, path: str, *, data: dict | None = None, headers: dict | None = None) -> tuple[int, dict, str]:
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=payload,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


def parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def run_smoke_test(stamp: str) -> dict:
    tenant = f"tenant-smoke-{stamp}"
    doc_id = f"doc-smoke-{stamp}"

    results = []
    status, _, body = request("GET", "/health")
    results.append(("GET /health", status, parse_json(body)))

    payload = {
        "id": doc_id,
        "title": "Smoke Test Document",
        "content": "adapter smoke verification for live api testing",
        "tags": ["smoke", "verification"],
        "metadata": {"source": "live-api-check"},
    }
    status, _, body = request(
        "POST",
        "/documents",
        data=payload,
        headers={"X-Tenant-ID": tenant, "Content-Type": "application/json"},
    )
    results.append(("POST /documents", status, parse_json(body)))

    status, _, body = request("GET", f"/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
    results.append(("GET /documents/{id}", status, parse_json(body)))

    query = urllib.parse.quote("adapter smoke")
    status, _, body = request("GET", f"/search?q={query}", headers={"X-Tenant-ID": tenant})
    results.append(("GET /search", status, parse_json(body)))

    status, _, body = request("DELETE", f"/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
    results.append(("DELETE /documents/{id}", status, parse_json(body)))

    status, _, body = request("GET", f"/documents/{doc_id}", headers={"X-Tenant-ID": tenant})
    results.append(("GET /documents/{id} after delete", status, parse_json(body)))

    passed = (
        results[0][1] == 200
        and results[1][1] == 201
        and results[2][1] == 200
        and results[3][1] == 200
        and results[4][1] == 200
        and results[5][1] == 404
    )
    return {"test": "smoke", "passed": passed, "results": results}


def run_rate_limit_test(stamp: str) -> dict:
    tenant = f"tenant-rate-{stamp}"
    first_429 = None
    for i in range(1, 140):
        status, headers, body = request("GET", "/search?q=rate-check", headers={"X-Tenant-ID": tenant})
        if status == 429:
            first_429 = {
                "request_number": i,
                "headers": headers,
                "body": parse_json(body),
            }
            break

    passed = first_429 is not None and first_429["request_number"] == 121 and "retry-after" in {
        key.lower() for key in first_429["headers"]
    }
    return {"test": "rate_limit", "tenant": tenant, "passed": passed, "first_429": first_429}


def run_tenant_isolation_test(stamp: str) -> dict:
    tenant_a = f"tenant-a-{stamp}"
    tenant_b = f"tenant-b-{stamp}"
    doc_a = f"doc-a-{stamp}"
    doc_b = f"doc-b-{stamp}"

    payload_a = {
        "id": doc_a,
        "title": "Tenant Alpha Document",
        "content": "shared-term alpha-only-content",
        "tags": ["alpha"],
        "metadata": {"owner": "alpha"},
    }
    payload_b = {
        "id": doc_b,
        "title": "Tenant Beta Document",
        "content": "shared-term beta-only-content",
        "tags": ["beta"],
        "metadata": {"owner": "beta"},
    }

    create_a = request(
        "POST",
        "/documents",
        data=payload_a,
        headers={"X-Tenant-ID": tenant_a, "Content-Type": "application/json"},
    )
    create_b = request(
        "POST",
        "/documents",
        data=payload_b,
        headers={"X-Tenant-ID": tenant_b, "Content-Type": "application/json"},
    )

    search_a = request("GET", "/search?q=shared-term", headers={"X-Tenant-ID": tenant_a})
    search_b = request("GET", "/search?q=shared-term", headers={"X-Tenant-ID": tenant_b})
    cross_a_from_b = request("GET", f"/documents/{doc_a}", headers={"X-Tenant-ID": tenant_b})
    cross_b_from_a = request("GET", f"/documents/{doc_b}", headers={"X-Tenant-ID": tenant_a})

    request("DELETE", f"/documents/{doc_a}", headers={"X-Tenant-ID": tenant_a})
    request("DELETE", f"/documents/{doc_b}", headers={"X-Tenant-ID": tenant_b})

    search_a_body = parse_json(search_a[2])
    search_b_body = parse_json(search_b[2])
    tenant_a_ids = [item["id"] for item in search_a_body.get("results", [])] if isinstance(search_a_body, dict) else []
    tenant_b_ids = [item["id"] for item in search_b_body.get("results", [])] if isinstance(search_b_body, dict) else []

    passed = (
        create_a[0] == 201
        and create_b[0] == 201
        and search_a[0] == 200
        and search_b[0] == 200
        and tenant_a_ids == [doc_a]
        and tenant_b_ids == [doc_b]
        and cross_a_from_b[0] == 404
        and cross_b_from_a[0] == 404
    )
    return {
        "test": "tenant_isolation",
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "passed": passed,
        "tenant_a_result_ids": tenant_a_ids,
        "tenant_b_result_ids": tenant_b_ids,
        "cross_get_statuses": {
            "tenant_b_fetches_tenant_a_doc": cross_a_from_b[0],
            "tenant_a_fetches_tenant_b_doc": cross_b_from_a[0],
        },
    }


def main() -> int:
    stamp = str(int(time.time()))
    report = [
        run_smoke_test(stamp),
        run_rate_limit_test(stamp),
        run_tenant_isolation_test(stamp),
    ]
    print(json.dumps({"base_url": BASE_URL, "results": report}, indent=2))
    return 0 if all(item["passed"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
