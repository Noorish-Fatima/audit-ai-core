#!/usr/bin/env python3
"""
System verification script for Audit-AI.
Checks that all services are running and healthy.
"""

import sys
import time
import argparse
from typing import Dict, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SERVICES = {
    "api": {
        "url": "http://localhost:8000/health",
        "expected_status": 200,
        "timeout": 10,
    },
    "api_ready": {
        "url": "http://localhost:8000/health/ready",
        "expected_status": 200,
        "timeout": 10,
    },
    "api_live": {
        "url": "http://localhost:8000/health/live",
        "expected_status": 200,
        "timeout": 10,
    },
    "frontend": {
        "url": "http://localhost:3000/api/health",
        "expected_status": 200,
        "timeout": 10,
    },
    "api_docs": {
        "url": "http://localhost:8000/docs",
        "expected_status": 200,
        "timeout": 10,
    },
}


def create_session() -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def check_service(name: str, config: Dict, session: requests.Session) -> Tuple[bool, str]:
    """Check a single service health endpoint."""
    url = config["url"]
    expected_status = config["expected_status"]
    timeout = config["timeout"]
    
    try:
        response = session.get(url, timeout=timeout)
        if response.status_code == expected_status:
            try:
                data = response.json()
                return True, f"OK - {data}"
            except ValueError:
                return True, f"OK - Status {response.status_code}"
        else:
            return False, f"FAIL - Status {response.status_code}, expected {expected_status}"
    except requests.exceptions.ConnectionError:
        return False, "FAIL - Connection refused"
    except requests.exceptions.Timeout:
        return False, f"FAIL - Timeout after {timeout}s"
    except Exception as e:
        return False, f"FAIL - {type(e).__name__}: {e}"


def check_worker() -> Tuple[bool, str]:
    """Check Celery worker via ping."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "exec", "audit-ai-worker", "celery", "-A", "worker.celery_app", "inspect", "ping"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and "pong" in result.stdout.lower():
            return True, f"OK - Worker responded: {result.stdout.strip()}"
        else:
            return False, f"FAIL - Worker ping failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "FAIL - Worker ping timeout"
    except FileNotFoundError:
        return False, "FAIL - Docker not available"
    except Exception as e:
        return False, f"FAIL - {type(e).__name__}: {e}"


def wait_for_services(max_wait: int = 120, interval: int = 5) -> bool:
    """Wait for all services to become healthy."""
    print(f"Waiting for services to become healthy (max {max_wait}s)...")
    session = create_session()
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        all_healthy = True
        for name, config in SERVICES.items():
            healthy, msg = check_service(name, config, session)
            if not healthy:
                all_healthy = False
                break
        
        if all_healthy:
            # Also check worker
            worker_healthy, worker_msg = check_worker()
            if worker_healthy:
                print("All services are healthy!")
                return True
            else:
                all_healthy = False
        
        if not all_healthy:
            elapsed = int(time.time() - start_time)
            print(f"  [{elapsed}s] Waiting... ({interval}s)")
            time.sleep(interval)
    
    return False


def main():
    parser = argparse.ArgumentParser(description="Verify Audit-AI system health")
    parser.add_argument("--wait", type=int, default=120, help="Max wait time for services (seconds)")
    parser.add_argument("--interval", type=int, default=5, help="Check interval (seconds)")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait, just check once")
    args = parser.parse_args()
    
    session = create_session()
    
    print("=" * 60)
    print("Audit-AI System Verification")
    print("=" * 60)
    
    if not args.no_wait:
        if wait_for_services(args.wait, args.interval):
            print("\n✓ All services verified successfully!")
            return 0
        else:
            print(f"\n✗ Services did not become healthy within {args.wait}s")
            # Fall through to show final status
    
    print("\nFinal Service Status:")
    print("-" * 60)
    
    all_ok = True
    for name, config in SERVICES.items():
        healthy, msg = check_service(name, config, session)
        status = "✓" if healthy else "✗"
        print(f"  {status} {name:20s} - {msg}")
        if not healthy:
            all_ok = False
    
    # Check worker
    worker_healthy, worker_msg = check_worker()
    status = "✓" if worker_healthy else "✗"
    print(f"  {status} {'worker':20s} - {worker_msg}")
    if not worker_healthy:
        all_ok = False
    
    print("-" * 60)
    
    if all_ok:
        print("\n✓ All services are healthy!")
        return 0
    else:
        print("\n✗ Some services are unhealthy!")
        return 1


if __name__ == "__main__":
    sys.exit(main())