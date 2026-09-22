with open("recall/remote.py", "r") as f:
    text = f.read()

sync_search = """    def search(self, query: str, limit: int = 10, min_salience: float = 0.5) -> List[Dict[str, Any]]:
        \"\"\"Global semantic search across all memories using cosine similarity.\"\"\"
        payload = {"query": query, "limit": limit, "min_salience": min_salience}
        res = self.session.post(f"{self.base_url}/api/v1/search", json=payload)
        return self._handle_response(res)

    def format_for_prompt("""

async_search = """    async def search(self, query: str, limit: int = 10, min_salience: float = 0.5) -> List[Dict[str, Any]]:
        \"\"\"Global semantic search across all memories using cosine similarity.\"\"\"
        payload = {"query": query, "limit": limit, "min_salience": min_salience}
        res = await self.client.post("/api/v1/search", json=payload)
        return self._handle_response(res)

    async def format_for_prompt("""

text = text.replace("    def format_for_prompt(", sync_search)
text = text.replace("    async def format_for_prompt(", async_search)

with open("recall/remote.py", "w") as f:
    f.write(text)
