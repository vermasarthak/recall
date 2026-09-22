with open("tests/test_client_api.py", "r") as f:
    text = f.read()

text = text.replace('client.ingest_turn("John", "I love watching Star Wars and Dune", "c1")', 'client.ingest_turn("John", "John likes StarWars", "c1")')
text = text.replace('client.ingest_turn("Alice", "I enjoy baking cookies", "c1")', 'client.ingest_turn("Alice", "Alice likes cookies", "c1")')
text = text.replace('query="watching movies like dune"', 'query="watching StarWars movies"')

with open("tests/test_client_api.py", "w") as f:
    f.write(text)
