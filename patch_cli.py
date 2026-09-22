with open("recall/cli.py", "r") as f:
    text = f.read()

text = text.replace(
    'parser_query = subparsers.add_parser("query", help="Query memory (requires server)")',
    'parser_query = subparsers.add_parser("query", help="Query memory (requires server)")\n    parser_search = subparsers.add_parser("search", help="Global semantic search")\n    parser_search.add_argument("query", help="Search string")\n    parser_search.add_argument("--tenant", default="default", help="Tenant ID")'
)

text = text.replace(
    'elif args.command in ["ingest", "query"]:',
    'elif args.command in ["ingest", "query", "search"]:'
)

search_cmd = """        elif args.command == "query":
            try:
                xml = client.format_for_prompt(about_entity=args.entity)
                print("\\n--- Memory Context ---")
                print(xml)
                print("----------------------\\n")
            except Exception as e:
                print(f"Failed to query: {e}")
                
        elif args.command == "search":
            try:
                results = client.search(query=args.query)
                print(f"\\n--- Global Search Results for '{args.query}' ---")
                for r in results:
                    fact = r['fact']
                    sub = r['subject']['canonical_name']
                    print(f"-> {sub} {fact['predicate']} {fact['object_value']} (Salience: {r['salience']['composite_score']:.2f})")
                print("----------------------\\n")
            except Exception as e:
                print(f"Failed to search: {e}")"""

text = text.replace(
"""        elif args.command == "query":
            try:
                xml = client.format_for_prompt(about_entity=args.entity)
                print("\\n--- Memory Context ---")
                print(xml)
                print("----------------------\\n")
            except Exception as e:
                print(f"Failed to query: {e}")""", search_cmd
)

with open("recall/cli.py", "w") as f:
    f.write(text)
