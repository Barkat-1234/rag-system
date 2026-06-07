from typing import List, Tuple
import numpy as np

class SimpleReranker:
    """Simple reranker using keyword matching and diversity (MMR-like)"""
    
    def __init__(self):
        self.enabled = True
        print("✅ Simple Reranker initialized")
    
    def mmr_rerank(self, query: str, documents: List[str], similarity_scores: List[float], lambda_param: float = 0.7, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        Maximal Marginal Relevance (MMR) reranking
        lambda_param: 0 = max diversity, 1 = max relevance
        """
        if not documents:
            return []
        
        # Simple keyword overlap for diversity calculation
        query_words = set(query.lower().split())
        
        selected_indices = []
        remaining_indices = list(range(len(documents)))
        
        while len(selected_indices) < min(top_k, len(documents)):
            best_score = -1
            best_idx = -1
            
            for idx in remaining_indices:
                # Relevance score (similarity from vector search)
                relevance = similarity_scores[idx] if idx < len(similarity_scores) else 0.5
                
                # Diversity score (negative of similarity to selected docs)
                diversity = 1.0
                if selected_indices:
                    doc_words = set(documents[idx].lower().split())
                    overlap = len(query_words & doc_words) / max(len(query_words), 1)
                    diversity = 1.0 - overlap
                
                # MMR score
                mmr_score = lambda_param * relevance - (1 - lambda_param) * diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
            
            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)
        
        # Return selected documents with their scores
        return [(documents[i], similarity_scores[i] if i < len(similarity_scores) else 0.5) 
                for i in selected_indices]
    
    def cross_encoder_rerank(self, query: str, documents: List[str]) -> List[Tuple[str, float]]:
        """Simplified cross-encoder reranking using text similarity"""
        query_words = set(query.lower().split())
        scores = []
        
        for doc in documents:
            doc_words = set(doc.lower().split())
            # Jaccard similarity
            intersection = len(query_words & doc_words)
            union = len(query_words | doc_words)
            score = intersection / union if union > 0 else 0
            scores.append(score)
        
        # Sort by score
        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return ranked

# Global reranker instance
reranker = SimpleReranker()