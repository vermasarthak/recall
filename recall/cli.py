import argparse
import os
import sys
from pprint import pprint


def main():
    parser = argparse.ArgumentParser(description="Recall Temporal Memory Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: server
    parser_server = subparsers.add_parser("server", help="Start the FastAPI server")
    parser_server.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser_server.add_argument("--port", type=int, default=8000, help="Port to bind")

    # Command: ingest
    parser_ingest = subparsers.add_parser("ingest", help="Ingest a fact (requires server)")
    parser_ingest.add_argument("speaker", help="Who is speaking")
    parser_ingest.add_argument("text", help="What they said")
    parser_ingest.add_argument("--tenant", default="default", help="Tenant ID")

    # Command: query
    parser_query = subparsers.add_parser("query", help="Query memory (requires server)")
    parser_search = subparsers.add_parser("search", help="Global semantic search")
    parser_search.add_argument("query", help="Search string")
    parser_search.add_argument("--tenant", default="default", help="Tenant ID")
    parser_query.add_argument("entity", help="Entity to query about")
    parser_query.add_argument("--tenant", default="default", help="Tenant ID")

    args = parser.parse_args()

    if args.command == "server":
        try:
            import uvicorn

            print(f"Starting Recall Server on {args.host}:{args.port}...")
            uvicorn.run("recall.server.app:app", host=args.host, port=args.port, reload=True)
        except ImportError:
            print("Error: uvicorn is not installed. Run `pip install -e .[server]`")
            sys.exit(1)

    elif args.command in ["ingest", "query", "search"]:
        try:
            from recall.remote import RecallRemoteClient
        except ImportError:
            print("Error: requests is not installed. Run `pip install -e .[client]`")
            sys.exit(1)

        api_key = os.environ.get("RECALL_API_KEY", "sk-recall-dev-key")
        client = RecallRemoteClient(base_url="http://localhost:8000", tenant_id=args.tenant, api_key=api_key)

        if args.command == "ingest":
            try:
                res = client.ingest_turn(speaker=args.speaker, text=args.text, conversation_id="cli_1")
                print("Ingestion Success:")
                pprint(res)
            except Exception as e:
                print(f"Failed to ingest: {e}")

        elif args.command == "query":
            try:
                xml = client.format_for_prompt(about_entity=args.entity)
                print("\n--- Memory Context ---")
                print(xml)
                print("----------------------\n")
            except Exception as e:
                print(f"Failed to query: {e}")

        elif args.command == "search":
            try:
                results = client.search(query=args.query)
                print(f"\n--- Global Search Results for '{args.query}' ---")
                for r in results:
                    fact = r["fact"]
                    sub = r["subject"]["canonical_name"]
                    print(
                        f"-> {sub} {fact['predicate']} {fact['object_value']} (Salience: {r['salience']['composite_score']:.2f})"
                    )
                print("----------------------\n")
            except Exception as e:
                print(f"Failed to search: {e}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
