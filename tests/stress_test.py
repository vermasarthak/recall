import asyncio
import httpx
import time
import random

API_KEY = "sk-test"
BASE_URL = "http://127.0.0.1:8000"
TENANT_ID = "stresstenant1"

async def worker(client, worker_id, num_requests):
    success = 0
    errors = 0
    latencies = []
    
    for i in range(num_requests):
        start = time.time()
        
        # Randomly choose between Ingest and Query
        is_ingest = random.choice([True, False])
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "x-tenant-id": TENANT_ID
        }
        
        try:
            if is_ingest:
                payload = {
                    "speaker": f"User_{worker_id}",
                    "text": f"User_{worker_id} works at Company_{i}",
                    "conversation_id": f"conv_{worker_id}"
                }
                res = await client.post(f"{BASE_URL}/api/v1/ingest", headers=headers, json=payload)
            else:
                payload = {
                    "about_entity": f"User_{worker_id}",
                    "context": "Where do they work?"
                }
                res = await client.post(f"{BASE_URL}/api/v1/query", headers=headers, json=payload)
            
            if res.status_code == 200:
                success += 1
            else:
                print(f"Error {res.status_code}: {res.text}")
                errors += 1
        except Exception as e:
            print(f"Request Exception: {e}")
            errors += 1
            
        latencies.append(time.time() - start)
        
    return success, errors, latencies

async def main():
    NUM_WORKERS = 50
    REQUESTS_PER_WORKER = 20
    
    print(f"Starting Stress Test: {NUM_WORKERS} workers, {REQUESTS_PER_WORKER} requests each...")
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [worker(client, i, REQUESTS_PER_WORKER) for i in range(NUM_WORKERS)]
        results = await asyncio.gather(*tasks)
        
    total_time = time.time() - start_time
    
    total_success = sum(r[0] for r in results)
    total_errors = sum(r[1] for r in results)
    all_latencies = []
    for r in results:
        all_latencies.extend(r[2])
        
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0
    
    print("=== STRESS TEST RESULTS ===")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Total Requests: {total_success + total_errors}")
    print(f"Success: {total_success}")
    print(f"Errors: {total_errors}")
    print(f"Req/Sec: {(total_success + total_errors) / total_time:.2f}")
    print(f"Avg Latency: {avg_latency*1000:.2f}ms")
    print(f"Max Latency: {max_latency*1000:.2f}ms")

if __name__ == "__main__":
    asyncio.run(main())
