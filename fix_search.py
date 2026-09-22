import re

with open("recall/client.py", "r") as f:
    content = f.read()

search_method = """
    def search(self, query: str, limit: int = 10, min_score: float = 0.5) -> List[QueryResult]:
        \"\"\"Global semantic search across all facts using vector similarity and salience decay.\"\"\"
        now_time = self.clock.now()
        
        # 1. Fetch all active facts globally
        active_facts = self.store.query_facts(valid_at=now_time, known_at=now_time)
        
        results: List[QueryResult] = []
        for fact in active_facts:
            # 2. Score fact contextually against the global query
            n_reinf = self.store.get_reinforcements_count(fact.logical_id, max_reinforced_at=now_time, max_tx_time=now_time)
            salience = self.salience_scorer.score_fact(
                fact=fact,
                context_query=query,
                valid_at=now_time,
                reinforcements_count=n_reinf,
                similarity_provider=self.similarity_provider
            )
            
            if salience.composite_score >= min_score:
                sub_ent = self.store.get_entity_by_id(fact.subject_id)
                obj_ent = self.store.get_entity_by_id(fact.object_entity_id) if fact.object_entity_id else None
                if sub_ent:
                    results.append(
                        QueryResult(
                            fact=fact,
                            salience=salience,
                            subject_entity=sub_ent,
                            object_entity=obj_ent
                        )
                    )
                    
        results.sort(key=lambda r: r.salience.composite_score, reverse=True)
        return results[:limit]

    def format_for_prompt(
"""

content = content.replace("    def format_for_prompt(", search_method)

with open("recall/client.py", "w") as f:
    f.write(content)
