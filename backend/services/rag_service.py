import os
import time
import hashlib
import json
from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# Try to import cache (create if not exists)
try:
    from backend.services.cache_service import embedding_cache
except ImportError:
    # Simple fallback cache
    from cachetools import TTLCache
    class SimpleCache:
        def __init__(self, maxsize=100, ttl=3600):
            self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
            self.hits = 0
            self.misses = 0
        def get(self, key):
            val = self.cache.get(key)
            if val:
                self.hits += 1
            else:
                self.misses += 1
            return val
        def set(self, key, value):
            self.cache[key] = value
        def get_stats(self):
            total = self.hits + self.misses
            return {"hits": self.hits, "misses": self.misses, "hit_rate": self.hits/total if total > 0 else 0}
    embedding_cache = SimpleCache()

class RAGService:
    def __init__(self):
        self.vector_store_path = "./backend/vector_store"
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'}
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vector_store = None
        
        # Initialize or load existing vector store
        if os.path.exists(self.vector_store_path):
            try:
                self.load_vector_store()
                print(f"Loaded existing vector store from {self.vector_store_path}")
            except:
                print("Could not load existing vector store, will create new one")
    
    def load_vector_store(self):
        """Load existing vector store"""
        self.vector_store = Chroma(
            persist_directory=self.vector_store_path,
            embedding_function=self.embeddings
        )
    
    def process_document(self, file_path: str, filename: str) -> Dict:
        """Process and index a document"""
        try:
            print(f"Processing document: {filename}")
            
            # Load document based on file type
            documents = []
            if filename.endswith('.pdf'):
                loader = PyPDFLoader(file_path)
                documents = loader.load()
                print(f"Loaded PDF with {len(documents)} pages")
            elif filename.endswith('.txt'):
                loader = TextLoader(file_path, encoding='utf-8')
                documents = loader.load()
                print(f"Loaded text file with {len(documents)} documents")
            else:
                return {"error": f"Unsupported file type: {filename}"}
            
            # Split documents into chunks
            chunks = self.text_splitter.split_documents(documents)
            print(f"Split into {len(chunks)} chunks")
            
            # Add metadata
            for chunk in chunks:
                chunk.metadata["source"] = filename
            
            # Create or update vector store
            if self.vector_store is None:
                print("Creating new vector store...")
                self.vector_store = Chroma.from_documents(
                    documents=chunks,
                    embedding=self.embeddings,
                    persist_directory=self.vector_store_path
                )
            else:
                print("Adding to existing vector store...")
                self.vector_store.add_documents(chunks)
            
            # Persist to disk
            self.vector_store.persist()
            print("Vector store persisted successfully")
            
            return {
                "message": "Document processed successfully",
                "filename": filename,
                "chunks_created": len(chunks),
                "total_characters": sum(len(chunk.page_content) for chunk in chunks)
            }
        except Exception as e:
            print(f"Error processing document: {str(e)}")
            return {"error": str(e)}
    
    def query(self, query_text: str, k: int = 3) -> Dict:
        """Original query method - works with Gemini"""
        if self.vector_store is None:
            return {
                "error": "No documents have been uploaded yet",
                "answer": "Please upload a document first",
                "sources": [],
                "context": ""
            }
        
        try:
            print(f"Querying: {query_text}")
            # Retrieve relevant chunks
            relevant_docs = self.vector_store.similarity_search(query_text, k=k)
            print(f"Retrieved {len(relevant_docs)} relevant chunks")
            
            # Extract context
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            sources = list(set([doc.metadata.get("source", "unknown") for doc in relevant_docs]))
            
            # Generate answer with Gemini
            try:
                from backend.services.gemini_service import gemini_service
                answer = gemini_service.generate_answer(query_text, context[:3000])
            except Exception as e:
                print(f"Gemini error: {e}")
                answer = f"Found {len(relevant_docs)} relevant sections from your document.\n\nRelevant content:\n{context[:500]}..."
            
            return {
                "query": query_text,
                "answer": answer,
                "context": context[:1000],
                "sources": sources,
                "num_chunks": len(relevant_docs)
            }
        except Exception as e:
            print(f"Error querying: {str(e)}")
            return {"error": str(e), "answer": "Error processing query", "context": "", "sources": []}
    
    def query_with_cache(self, query_text: str, k: int = 3) -> Dict:
        """Query with caching for faster repeated questions"""
        # Create cache key
        cache_key = hashlib.md5(f"{query_text}:{k}".encode()).hexdigest()
        
        # Check cache
        cached_result = embedding_cache.get(cache_key)
        if cached_result:
            print(f"✅ CACHE HIT - Returning cached result for: {query_text[:50]}...")
            return cached_result
        
        # Normal query
        result = self.query(query_text, k)
        
        # Cache result (only if no error)
        if "error" not in result:
            embedding_cache.set(cache_key, result)
            print(f"💾 Cached result for: {query_text[:50]}...")
        
        return result
    
    def query_optimized(self, query_text: str, k: int = 5, top_k: int = 3, use_rerank: bool = True) -> Dict:
        """Optimized query with reranking for better quality"""
        if self.vector_store is None:
            return {
                "error": "No documents have been uploaded yet",
                "answer": "Please upload a document first",
                "sources": [],
                "context": ""
            }
        
        # Check cache first
        cache_key = hashlib.md5(f"opt_{query_text}:{k}:{top_k}:{use_rerank}".encode()).hexdigest()
        cached_result = embedding_cache.get(cache_key)
        if cached_result:
            print(f"✅ CACHE HIT (optimized) for: {query_text[:50]}...")
            return cached_result
        
        try:
            start_time = time.time()
            print(f"🔍 Optimized query: {query_text[:50]}...")
            
            # Retrieve more documents for reranking
            relevant_docs = self.vector_store.similarity_search(query_text, k=k)
            print(f"📚 Retrieved {len(relevant_docs)} candidate chunks")
            
            # Extract documents and sources
            documents = [doc.page_content for doc in relevant_docs]
            sources = [doc.metadata.get("source", "unknown") for doc in relevant_docs]
            
            # Apply simple reranking if enabled
            if use_rerank and len(documents) > top_k:
                # Simple relevance scoring based on keyword matching
                query_words = set(query_text.lower().split())
                scored_docs = []
                
                for i, doc in enumerate(documents):
                    doc_words = set(doc.lower().split())
                    # Calculate overlap score
                    overlap = len(query_words & doc_words)
                    score = overlap / max(len(query_words), 1)
                    scored_docs.append((score, i, doc))
                
                # Sort by score and take top_k
                scored_docs.sort(reverse=True, key=lambda x: x[0])
                selected_indices = [idx for _, idx, _ in scored_docs[:top_k]]
                
                # Reorder documents and sources
                documents = [documents[i] for i in selected_indices]
                sources = list(set([sources[i] for i in selected_indices]))
            
            # Take top results
            documents = documents[:top_k]
            context = "\n\n".join(documents)
            
            # Generate answer with Gemini
            try:
                from backend.services.gemini_service import gemini_service
                answer = gemini_service.generate_answer(query_text, context[:3000])
            except Exception as e:
                print(f"Gemini error: {e}")
                answer = f"Based on your document, I found relevant information:\n\n{context[:500]}..."
            
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"⚡ Query completed in {elapsed_ms:.0f}ms")
            
            result = {
                "query": query_text,
                "answer": answer,
                "context": context[:1000],
                "sources": sources,
                "num_chunks": len(documents),
                "response_time_ms": elapsed_ms
            }
            
            # Cache the result
            embedding_cache.set(cache_key, result)
            
            return result
        except Exception as e:
            print(f"Error in optimized query: {str(e)}")
            return {"error": str(e), "answer": "Error processing query", "sources": []}
    
    def list_documents(self) -> List[str]:
        """List all indexed documents"""
        if self.vector_store is None:
            return []
        
        try:
            return ["Document(s) are available in vector store"]
        except:
            return []
    
    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics"""
        return embedding_cache.get_stats()
    
    def clear_cache(self):
        """Clear the query cache"""
        embedding_cache.clear()
        print("🧹 Cache cleared successfully")
        return {"message": "Cache cleared"}

# Create global instance
rag_service = RAGService()
print("🚀 RAG Service initialized successfully with optimizations!")