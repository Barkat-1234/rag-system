import os
import time
import hashlib
import json
from typing import List, Dict

# Simple PDF and Text loaders (no LangChain)
from pypdf import PdfReader

# Simple text splitter (replaces LangChain)
class SimpleTextSplitter:
    def __init__(self, chunk_size=1000, chunk_overlap=200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def split_text(self, text: str) -> List[str]:
        """Split text into chunks"""
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - self.chunk_overlap
        
        return chunks
    
    def split_documents(self, documents: List) -> List:
        """Split documents (compatible with LangChain interface)"""
        from types import SimpleNamespace
        
        all_chunks = []
        for doc in documents:
            chunks = self.split_text(doc.page_content)
            for chunk in chunks:
                new_doc = SimpleNamespace()
                new_doc.page_content = chunk
                new_doc.metadata = doc.metadata.copy() if hasattr(doc, 'metadata') else {}
                all_chunks.append(new_doc)
        
        return all_chunks

# Simple PDF Loader (no LangChain)
class SimplePDFLoader:
    def __init__(self, file_path):
        self.file_path = file_path
    
    def load(self):
        from types import SimpleNamespace
        
        documents = []
        reader = PdfReader(self.file_path)
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text.strip():
                doc = SimpleNamespace()
                doc.page_content = text
                doc.metadata = {"source": self.file_path, "page": page_num + 1}
                documents.append(doc)
        
        return documents

# Simple Text Loader (no LangChain)
class SimpleTextLoader:
    def __init__(self, file_path, encoding='utf-8'):
        self.file_path = file_path
        self.encoding = encoding
    
    def load(self):
        from types import SimpleNamespace
        
        documents = []
        with open(self.file_path, 'r', encoding=self.encoding) as f:
            text = f.read()
        
        doc = SimpleNamespace()
        doc.page_content = text
        doc.metadata = {"source": self.file_path}
        documents.append(doc)
        
        return documents

# Try to import cache (create if not exists)
try:
    from backend.services.cache_service import embedding_cache
except ImportError:
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
        def clear(self):
            self.cache.clear()
            self.hits = 0
            self.misses = 0
        def get_stats(self):
            total = self.hits + self.misses
            return {"hits": self.hits, "misses": self.misses, "hit_rate": self.hits/total if total > 0 else 0}
    embedding_cache = SimpleCache()

class RAGService:
    def __init__(self):
        self.vector_store_path = "./backend/vector_store"
        self.embeddings = None
        self.vector_store = None
        self.text_splitter = SimpleTextSplitter(chunk_size=1000, chunk_overlap=200)
        
        # Try to initialize embeddings (optional - fallback if not available)
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embeddings_available = True
            print("✅ Embeddings model loaded")
        except Exception as e:
            print(f"⚠️ Embeddings not available: {e}")
            self.embeddings_available = False
        
        # Initialize or load existing vector store
        if os.path.exists(self.vector_store_path):
            try:
                self.load_vector_store()
                print(f"Loaded existing vector store from {self.vector_store_path}")
            except:
                print("Could not load existing vector store, will create new one")
    
    def load_vector_store(self):
        """Load existing vector store - simplified"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self.chroma_client = chromadb.PersistentClient(
                path=self.vector_store_path,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Try to get existing collection
            try:
                self.chroma_collection = self.chroma_client.get_collection("rag_documents")
                self.vector_store = True
            except:
                self.vector_store = None
        except Exception as e:
            print(f"Error loading vector store: {e}")
            self.vector_store = None
    
    def process_document(self, file_path: str, filename: str) -> Dict:
        """Process and index a document"""
        try:
            print(f"Processing document: {filename}")
            
            # Load document based on file type
            documents = []
            if filename.endswith('.pdf'):
                loader = SimplePDFLoader(file_path)
                documents = loader.load()
                print(f"Loaded PDF with {len(documents)} pages")
            elif filename.endswith('.txt'):
                loader = SimpleTextLoader(file_path, encoding='utf-8')
                documents = loader.load()
                print(f"Loaded text file with {len(documents)} documents")
            else:
                return {"error": f"Unsupported file type: {filename}"}
            
            # Split documents into chunks
            chunks = self.text_splitter.split_documents(documents)
            print(f"Split into {len(chunks)} chunks")
            
            # Generate embeddings and store
            if self.embeddings_available:
                # Create or update vector store
                import chromadb
                from chromadb.config import Settings
                
                if not hasattr(self, 'chroma_client'):
                    self.chroma_client = chromadb.PersistentClient(
                        path=self.vector_store_path,
                        settings=Settings(anonymized_telemetry=False)
                    )
                
                # Create or get collection
                try:
                    self.chroma_collection = self.chroma_client.get_collection("rag_documents")
                except:
                    self.chroma_collection = self.chroma_client.create_collection("rag_documents")
                
                # Generate embeddings and add to collection
                for i, chunk in enumerate(chunks):
                    embedding = self.embedding_model.encode(chunk.page_content).tolist()
                    
                    self.chroma_collection.add(
                        embeddings=[embedding],
                        documents=[chunk.page_content],
                        metadatas=[{"source": filename, "chunk_id": i}],
                        ids=[f"{filename}_{i}"]
                    )
                
                self.vector_store = True
                print("Vector store persisted successfully")
            else:
                print("⚠️ No embeddings available - skipping vector storage")
            
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
        if not hasattr(self, 'vector_store') or self.vector_store is None:
            return {
                "error": "No documents have been uploaded yet",
                "answer": "Please upload a document first",
                "sources": [],
                "context": ""
            }
        
        try:
            print(f"Querying: {query_text}")
            
            # Generate query embedding and search
            if self.embeddings_available and hasattr(self, 'chroma_collection'):
                query_embedding = self.embedding_model.encode(query_text).tolist()
                results = self.chroma_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=k
                )
                
                documents = results['documents'][0] if results['documents'] else []
                metadatas = results['metadatas'][0] if results['metadatas'] else []
                sources = list(set([m.get('source', 'unknown') for m in metadatas]))
                context = "\n\n".join(documents)
            else:
                return {
                    "error": "Search not available",
                    "answer": "Please upload a document first",
                    "sources": [],
                    "context": ""
                }
            
            # Generate answer with Gemini
            try:
                from backend.services.gemini_service import gemini_service
                answer = gemini_service.generate_answer(query_text, context[:3000])
            except Exception as e:
                print(f"Gemini error: {e}")
                answer = f"Found {len(documents)} relevant sections from your document.\n\nRelevant content:\n{context[:500]}..."
            
            return {
                "query": query_text,
                "answer": answer,
                "context": context[:1000],
                "sources": sources,
                "num_chunks": len(documents)
            }
        except Exception as e:
            print(f"Error querying: {str(e)}")
            return {"error": str(e), "answer": "Error processing query", "context": "", "sources": []}
    
    def list_documents(self) -> List[str]:
        """List all indexed documents"""
        if not hasattr(self, 'vector_store') or self.vector_store is None:
            return []
        return ["Document(s) are available in vector store"]

# Create global instance
rag_service = RAGService()
print("🚀 RAG Service initialized successfully (LangChain-free)!")